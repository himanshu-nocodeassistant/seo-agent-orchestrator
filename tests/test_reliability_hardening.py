"""Regression tests for the second reliability review."""

import asyncio
import json
import threading
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from agent.api.helpers import (
    RUN_LEASE_SECONDS,
    _claim_campaign_resume,
    _comment_action_is_stale,
    _create_run,
    _heartbeat_run,
    _reclaim_stale_comment_actions,
    _run_agent_prompt,
    _utcnow_iso,
    recover_stale_runs,
)
from agent.api.main import (
    AgentRunModel,
    CommentModel,
    CommentActionModel,
    OrchestrationStateModel,
    TaskModel,
    get_db_session,
)
from agent.config import AgentConfig
from agent.dataforseo.client import (
    DataForSEOClient,
    DataForSEOError,
    DataForSEORecoveryError,
    TaskNotReadyError,
)
from scripts.pipelines._cli import run_pipeline


def _old_timestamp(minutes=16):
    return (datetime.utcnow() - timedelta(minutes=minutes)).isoformat()


def _campaign_task(db, *, approved=True):
    now = _utcnow_iso()
    task = TaskModel(
        title="Reliability campaign",
        description="Test campaign",
        execution_type="orchestrate_seo_campaign",
        status="in_progress",
        approved_at=now if approved else None,
        created_at=now,
        updated_at=now,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    run = _create_run(db, task, "manual_execute", "orchestrate_seo_campaign")
    state = OrchestrationStateModel(
        orchestrator_run_id=run.run_id,
        campaign_goal="Test campaign",
        plan_json=json.dumps({"phases": []}),
        status="awaiting_approval",
        created_at=now,
        updated_at=now,
    )
    db.add(state)
    db.commit()
    return task, run


@pytest.mark.asyncio
async def test_concurrent_campaign_resume_claim_has_one_winner(client):
    """Two concurrent resume requests must dispatch the campaign once."""
    from httpx import ASGITransport, AsyncClient
    from agent.api.main import app

    db = get_db_session()
    try:
        task, run = _campaign_task(db)
        task_id = task.id
    finally:
        db.close()

    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def fake_campaign(*args, **kwargs):
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()

    with patch(
        "agent.api.routers.tasks._execute_campaign_with_timeout",
        new=fake_campaign,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as async_client:
            requests = [
                asyncio.create_task(
                    async_client.post(f"/tasks/{task_id}/execute?resume=true")
                )
                for _ in range(2)
            ]
            await asyncio.wait_for(started.wait(), timeout=1)
            await asyncio.sleep(0)
            release.set()
            responses = await asyncio.gather(*requests)

    assert calls == 1
    assert all(response.status_code == 200 for response in responses)


def test_stale_campaign_with_incomplete_publisher_child_requires_review(client):
    db = get_db_session()
    try:
        task, parent_run = _campaign_task(db)
        parent_run.heartbeat_at = _old_timestamp()
        parent_run.lease_expires_at = _old_timestamp()
        child = TaskModel(
            title="Campaign: publish",
            execution_type="campaign_publisher",
            parent_task_id=task.id,
            status="in_progress",
            created_at=_utcnow_iso(),
            updated_at=_utcnow_iso(),
        )
        db.add(child)
        db.commit()
        db.refresh(child)
        child_run = AgentRunModel(
            run_id="stale-publisher-child",
            task_id=child.id,
            parent_run_id=parent_run.run_id,
            status="running",
            execution_type="campaign_publisher",
            write_capable=True,
            heartbeat_at=_old_timestamp(),
            lease_expires_at=_old_timestamp(),
            started_at=_old_timestamp(),
        )
        db.add(child_run)
        db.commit()

        recovered = recover_stale_runs(db)

        assert parent_run.run_id in {run.run_id for run in recovered}
        db.refresh(parent_run)
        assert parent_run.recovery_state == "review_required"
        assert parent_run.status == "review_required"
    finally:
        db.close()


def test_dataforseo_recovery_error_preserves_ready_results(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("DATAFORSEO_LOGIN", "login")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "password")
    monkeypatch.setattr("agent.dataforseo.client.MANIFEST_DIR", str(tmp_path))
    client = DataForSEOClient()
    manifest = client._write_manifest(
        "post", [{"keyword": "one"}, {"keyword": "two"}], ["ready", "slow"]
    )
    client._last_manifest_path = manifest
    responses = iter(["ready", "slow", "slow"])
    def fake_task_get(endpoint, task_id):
        if next(responses) == "ready":
            return {"tasks": [{"result": [{"keyword": "one"}]}]}
        raise TaskNotReadyError(40601, "queued")
    clock = iter([0.0, 1.0, 1.0, 11.0])

    with patch.object(client, "_task_post", return_value=["ready", "slow"]), \
        patch.object(client, "_task_get", side_effect=fake_task_get), \
        patch("agent.dataforseo.client.time.sleep"), \
        patch("agent.dataforseo.client.time.monotonic", side_effect=lambda: next(clock)):
        with pytest.raises(DataForSEORecoveryError) as exc_info:
            client._task_post_and_poll("post", "get", [{"keyword": "x"}], max_wait=10)

    assert exc_info.value.task_ids == ["slow"]
    assert exc_info.value.results == [{"keyword": "one"}]
    saved = json.loads(tmp_path.joinpath(manifest.split("/")[-1]).read_text())
    assert saved["completed_results"] == [{"keyword": "one"}]


@pytest.mark.asyncio
async def test_long_agent_wait_refreshes_run_lease(client, monkeypatch):
    monkeypatch.setattr("agent.api.helpers.RUN_HEARTBEAT_INTERVAL_SECONDS", 0.005)
    db = get_db_session()
    try:
        task_data = client.post(
            "/tasks", json={"title": "Long wait", "execution_type": "research"}
        ).json()
        task = db.query(TaskModel).filter_by(id=task_data["id"]).one()
        run = _create_run(db, task, "manual_execute", "research")
        config = AgentConfig()
        config._heartbeat_db = db
        config._heartbeat_run_id = run.run_id

        async def slow_result(*args, **kwargs):
            await asyncio.sleep(0.03)
            return SimpleNamespace(result_text="done", session_id=None)

        with patch("agent.api.helpers.SEOAgent.create_and_run_result", new=slow_result):
            await _run_agent_prompt("wait", config, {})

        db.refresh(run)
        assert run.heartbeat_at > run.started_at
    finally:
        db.close()


@pytest.mark.asyncio
async def test_comment_action_lease_refresh_prevents_reclaim(client, monkeypatch):
    monkeypatch.setattr("agent.api.helpers.RUN_HEARTBEAT_INTERVAL_SECONDS", 0.005)
    task = client.post(
        "/tasks", json={"title": "Comment lease", "execution_type": "research"}
    ).json()
    db = get_db_session()
    try:
        action = CommentActionModel(
            task_id=task["id"], comment_id=999, status="running", attempts=1,
            max_attempts=2, heartbeat_at=_utcnow_iso(),
            lease_expires_at=_utcnow_iso(), recovery_state="running",
        )
        db.add(action)
        db.commit()
        config = AgentConfig()
        config._heartbeat_db = db
        config._comment_action = action

        async def slow_result(*args, **kwargs):
            await asyncio.sleep(0.03)
            return SimpleNamespace(result_text="done", session_id=None)

        with patch("agent.api.helpers.SEOAgent.create_and_run_result", new=slow_result):
            work = asyncio.create_task(_run_agent_prompt("wait", config, {}))
            await asyncio.sleep(0.015)
            _reclaim_stale_comment_actions(db)
            assert db.get(CommentActionModel, action.id).status == "running"
            await work
    finally:
        db.close()


def test_child_run_creation_rolls_back_task_pointer_on_commit_failure(client):
    from agent.orchestrator import _create_child_run, _create_child_task

    db = get_db_session()
    try:
        task = client.post(
            "/tasks", json={"title": "Atomic campaign", "execution_type": "orchestrate_seo_campaign"}
        ).json()
        parent = db.query(TaskModel).filter_by(id=task["id"]).one()
        child = _create_child_task(
            db, parent, {"phase": "researcher", "execution_type": "campaign_researcher"}
        )
        parent_run = _create_run(db, parent, "manual_execute", "orchestrate_seo_campaign")

        with patch.object(db, "commit", side_effect=RuntimeError("simulated crash")):
            with pytest.raises(RuntimeError, match="simulated crash"):
                _create_child_run(db, child, parent_run.run_id, "campaign_researcher")

        db.expire_all()
        assert db.query(AgentRunModel).filter_by(task_id=child.id).count() == 0
        assert db.query(TaskModel).filter_by(id=child.id).one().active_run_id is None
    finally:
        db.close()


class _RecoveryClient(DataForSEOClient):
    def keyword_method(self, tasks):
        raise DataForSEORecoveryError(
            ["slow"], "/tmp/recovery.json", "polling stopped",
            results=[{"keyword": "ready"}],
            errors=[{"task_id": "failed", "error": "bad task"}],
        )


def test_pipeline_cli_writes_partial_results_on_recovery(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DATAFORSEO_LOGIN", "login")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "password")
    output = tmp_path / "partial.json"
    monkeypatch.setattr(
        "sys.argv",
        ["pipeline.py", "keyword_method", "--task", "{}", "--output", str(output)],
    )

    run_pipeline(_RecoveryClient, "recovery-pipeline")

    assert json.loads(output.read_text()) == [{"keyword": "ready"}]
    captured = capsys.readouterr().out
    assert "Recovery required" in captured
    assert "failed" in captured


@pytest.mark.asyncio
async def test_comment_autopilot_defers_while_campaign_is_resuming(client):
    from agent.api.helpers import process_one_comment_action

    task_data = client.post(
        "/tasks", json={
            "title": "Resuming campaign",
            "execution_type": "orchestrate_seo_campaign",
        }
    ).json()
    db = get_db_session()
    try:
        task = db.query(TaskModel).filter_by(id=task_data["id"]).one()
        run = _create_run(db, task, "manual_execute", task.execution_type)
        run.status = "resuming"
        comment = CommentModel(
            task_id=task.id, author="user", body="@agent revise this"
        )
        db.add(comment)
        db.commit()
        db.refresh(comment)
        comment_id = comment.id
        action = CommentActionModel(
            task_id=task.id, comment_id=comment.id, status="pending",
            attempts=0, max_attempts=2,
        )
        db.add(action)
        db.commit()
    finally:
        db.close()

    with patch("agent.api.helpers._run_agent_prompt", new=AsyncMock()) as run_agent:
        result = await process_one_comment_action()

    assert result["status"] == "pending"
    run_agent.assert_not_awaited()
    cleanup_db = get_db_session()
    try:
        cleanup_action = cleanup_db.query(CommentActionModel).filter_by(
            comment_id=comment_id
        ).one()
        cleanup_action.status = "retry_exhausted"
        cleanup_db.commit()
    finally:
        cleanup_db.close()


@pytest.mark.asyncio
async def test_resumed_campaign_refreshes_parent_lease_during_child_wait(
    client, monkeypatch
):
    from agent.orchestrator import run_campaign_orchestration

    monkeypatch.setattr("agent.api.helpers.RUN_HEARTBEAT_INTERVAL_SECONDS", 0.005)
    db = get_db_session()
    try:
        task, run = _campaign_task(db)
        state = db.query(OrchestrationStateModel).filter_by(
            orchestrator_run_id=run.run_id
        ).one()
        state.plan_json = "```json\n" + json.dumps({
            "phases": [{
                "phase": "researcher",
                "task_title": "Campaign: researcher",
                "execution_type": "campaign_researcher",
                "depends_on": [],
            }]
        }) + "\n```"
        db.commit()
        assert _claim_campaign_resume(db, run.run_id)
        db.refresh(run)
        claimed_heartbeat = run.heartbeat_at

        async def slow_phase(*args, **kwargs):
            await asyncio.sleep(0.03)
            return "researcher", "done", False

        with patch("agent.orchestrator._dispatch_phase", new=slow_phase), \
            patch("agent.api.helpers._heartbeat_run", wraps=_heartbeat_run) as parent_heartbeat:
            await run_campaign_orchestration(db, task, run, resume=True)

        db.refresh(run)
        assert parent_heartbeat.call_count >= 1
        assert run.heartbeat_at > claimed_heartbeat
    finally:
        db.close()


def test_stale_approval_run_can_resume_without_new_run(client):
    db = get_db_session()
    try:
        task, run = _campaign_task(db)
        run.heartbeat_at = _old_timestamp()
        run.lease_expires_at = _old_timestamp()
        db.commit()

        recovered = recover_stale_runs(db)
        assert run.run_id in {item.run_id for item in recovered}
        db.refresh(run)
        assert run.status == "recoverable"
        assert task.active_run_id is None

        assert _claim_campaign_resume(db, run.run_id)
        db.refresh(run)
        assert run.status == "resuming"
        assert run.recovery_state == "none"
        assert db.query(AgentRunModel).filter_by(task_id=task.id).count() == 1
    finally:
        db.close()


def test_dataforseo_preserves_partial_results_after_task_error(tmp_path, monkeypatch):
    monkeypatch.setenv("DATAFORSEO_LOGIN", "login")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "password")
    monkeypatch.setattr("agent.dataforseo.client.MANIFEST_DIR", str(tmp_path))
    client = DataForSEOClient()
    manifest = client._write_manifest(
        "post", [{"keyword": "one"}, {"keyword": "two"}, {"keyword": "three"}],
        ["ready", "failed", "slow"],
    )
    client._last_manifest_path = manifest
    responses = iter(["ready", "failed", "slow", "slow"])

    def fake_task_get(endpoint, task_id):
        result = next(responses)
        if result == "ready":
            return {"tasks": [{"result": [{"keyword": "one"}]}]}
        if result == "failed":
            raise DataForSEOError(40000, "bad task")
        raise TaskNotReadyError(40601, "queued")

    clock = iter([0.0, 1.0, 1.0, 11.0])
    with patch.object(client, "_task_post", return_value=["ready", "failed", "slow"]), \
        patch.object(client, "_task_get", side_effect=fake_task_get), \
        patch("agent.dataforseo.client.time.sleep"), \
        patch("agent.dataforseo.client.time.monotonic", side_effect=lambda: next(clock)):
        with pytest.raises(DataForSEORecoveryError) as exc_info:
            client._task_post_and_poll("post", "get", [{"keyword": "x"}], max_wait=10)

    assert exc_info.value.task_ids == ["slow"]
    assert exc_info.value.results == [{"keyword": "one"}]
    assert exc_info.value.errors[0]["task_id"] == "failed"
    saved = json.loads(tmp_path.joinpath(manifest.split("/")[-1]).read_text())
    assert saved["completed_results"] == [{"keyword": "one"}]
    assert saved["recovery_errors"][0]["task_id"] == "failed"
