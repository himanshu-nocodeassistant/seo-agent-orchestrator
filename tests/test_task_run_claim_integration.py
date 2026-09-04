"""API integration tests for task execution claims.

The claim service has its own concurrency tests.  These tests cover the
router boundary: request keys are required, replays do not invoke the agent,
and a live claim is reported as a conflict before side effects occur.
"""

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from agent.api.main import (
    AgentRunModel,
    OrchestrationStateModel,
    TaskModel,
    get_db_session,
)
from agent.db import ExecuteRequestModel
from agent.run_claims import RunClaimService


def _headers(key: str) -> dict[str, str]:
    return {"Idempotency-Key": key}


def _agent_result():
    return SimpleNamespace(result_text="completed", session_id=None)


class TestTaskExecuteClaims:
    def test_missing_key_is_rejected_before_agent_work(self, client, monkeypatch):
        monkeypatch.setenv("ALLOW_MISSING_IDEMPOTENCY_KEY", "false")
        task = client.post(
            "/tasks", json={"title": "Key required", "execution_type": "manual"}
        ).json()
        with patch("agent.api.helpers._run_agent_prompt", new=AsyncMock()) as run_agent:
            response = client.post(f"/tasks/{task['id']}/execute")

        assert response.status_code == 422
        run_agent.assert_not_awaited()

    def test_same_key_replays_without_new_run_or_comments(self, client):
        task = client.post(
            "/tasks", json={"title": "Replay me", "execution_type": "manual"}
        ).json()
        with patch(
            "agent.api.helpers._run_agent_prompt", new=AsyncMock(return_value=_agent_result())
        ) as run_agent:
            first = client.post(
                f"/tasks/{task['id']}/execute", headers=_headers("replay-key")
            )
            second = client.post(
                f"/tasks/{task['id']}/execute", headers=_headers("replay-key")
            )

        assert first.status_code == 200
        assert second.status_code == 200
        assert second.json()["run_id"] == first.json()["run_id"]
        assert run_agent.await_count == 1

        db = get_db_session()
        try:
            assert db.query(AgentRunModel).filter_by(task_id=task["id"]).count() == 1
            assert db.query(ExecuteRequestModel).filter_by(
                idempotency_key="replay-key"
            ).count() == 1
        finally:
            db.close()

    def test_different_key_reports_live_claim_without_agent_work(self, client):
        task = client.post(
            "/tasks", json={"title": "Already running", "execution_type": "manual"}
        ).json()
        db = get_db_session()
        try:
            now = datetime.now(timezone.utc)
            claim = RunClaimService(db, clock=lambda: now).acquire(
                task["id"],
                idempotency_key="owner-key",
                fingerprint="seeded",
                execution_type="manual",
            )
        finally:
            db.close()

        with patch("agent.api.helpers._run_agent_prompt", new=AsyncMock()) as run_agent:
            response = client.post(
                f"/tasks/{task['id']}/execute", headers=_headers("loser-key")
            )

        assert response.status_code == 409
        detail = response.json()["detail"]
        assert detail["active_run_id"] == claim.run_id
        assert detail["status"] == "running"
        run_agent.assert_not_awaited()

    def test_overlapping_execute_requests_call_agent_once(self, client):
        task = client.post(
            "/tasks", json={"title": "Concurrent", "execution_type": "manual"}
        ).json()
        entered = threading.Event()
        release = threading.Event()

        async def blocked_agent(*_args, **_kwargs):
            entered.set()
            await asyncio.to_thread(release.wait, 5)
            return _agent_result()

        with patch("agent.api.helpers._run_agent_prompt", new=AsyncMock(side_effect=blocked_agent)) as agent:
            with ThreadPoolExecutor(max_workers=2) as pool:
                first_future = pool.submit(
                    client.post,
                    f"/tasks/{task['id']}/execute",
                    headers=_headers("concurrent-a"),
                )
                assert entered.wait(5)
                second = client.post(
                    f"/tasks/{task['id']}/execute",
                    headers=_headers("concurrent-b"),
                )
                release.set()
                first = first_future.result(timeout=5)

        assert first.status_code == 200
        assert second.status_code == 409
        assert agent.await_count == 1


class TestCampaignExecuteClaims:
    def test_campaign_same_key_replays_without_second_orchestration(self, client):
        task = client.post(
            "/tasks",
            json={"title": "Campaign", "execution_type": "orchestrate_seo_campaign"},
        ).json()
        with patch(
            "agent.api.routers.tasks._execute_campaign_with_timeout",
            new=AsyncMock(return_value=None),
        ) as orchestrate:
            first = client.post(
                f"/tasks/{task['id']}/execute", headers=_headers("campaign-key")
            )
            second = client.post(
                f"/tasks/{task['id']}/execute", headers=_headers("campaign-key")
            )

        assert first.status_code == 200
        assert second.status_code == 200
        assert second.json()["run_id"] == first.json()["run_id"]
        orchestrate.assert_awaited_once()

    def test_resume_reuses_paused_run_and_key(self, client):
        task = client.post(
            "/tasks",
            json={"title": "Resume campaign", "execution_type": "orchestrate_seo_campaign"},
        ).json()
        db = get_db_session()
        try:
            task_row = db.query(TaskModel).filter_by(id=task["id"]).one()
            now = datetime(2026, 1, 1, tzinfo=timezone.utc)
            claim = RunClaimService(db, clock=lambda: now).acquire(
                task_row.id,
                idempotency_key="start-key",
                fingerprint="start",
                execution_type="orchestrate_seo_campaign",
            )
            task_row.approved_at = now.replace(tzinfo=None).isoformat()
            db.commit()
            db.add(
                OrchestrationStateModel(
                    orchestrator_run_id=claim.run_id,
                    campaign_goal="resume",
                    plan_json='{"phases": [{"phase": "research"}]}',
                    phase_outputs_json="{}",
                    child_run_ids_json="[]",
                    status="awaiting_approval",
                    created_at=now.replace(tzinfo=None).isoformat(),
                    updated_at=now.replace(tzinfo=None).isoformat(),
                )
            )
            db.commit()
            RunClaimService(db, clock=lambda: now).pause(
                claim.task_id, claim.run_id, claim.owner_token, claim.fence_version
            )
        finally:
            db.close()

        with patch(
            "agent.api.routers.tasks._execute_campaign_with_timeout",
            new=AsyncMock(return_value=None),
        ) as orchestrate:
            first = client.post(
                f"/tasks/{task['id']}/execute?resume=true",
                headers=_headers("resume-key"),
            )
            second = client.post(
                f"/tasks/{task['id']}/execute?resume=true",
                headers=_headers("resume-key"),
            )

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["run_id"] == claim.run_id
        assert second.json()["run_id"] == claim.run_id
        orchestrate.assert_awaited_once()
