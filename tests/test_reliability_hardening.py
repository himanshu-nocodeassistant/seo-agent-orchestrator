"""Regression tests for the second reliability review."""

import asyncio
import json
import threading
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import requests

from agent.api.helpers import (
    RUN_LEASE_SECONDS,
    _claim_campaign_resume,
    _comment_action_is_stale,
    _create_run,
    _finalize_run_failure,
    _heartbeat_comment_action,
    _heartbeat_run,
    _reclaim_stale_comment_actions,
    _run_agent_prompt,
    RunOwnershipLost,
    _utcnow_iso,
    recover_stale_runs,
    _finalize_run_success,
)
from agent.api.main import (
    AgentRunModel,
    CommentModel,
    CommentActionModel,
    OrchestrationStateModel,
    RunEventModel,
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
from agent.runtime_profiles import ValidationResult
import agent.orchestrator as orchestrator_module
from agent.orchestrator import _run_with_retry
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

    assert exc_info.value.task_ids == ["failed", "slow"]
    assert exc_info.value.results == [{"keyword": "one"}]
    assert exc_info.value.errors[0]["task_id"] == "failed"
    saved = json.loads(tmp_path.joinpath(manifest.split("/")[-1]).read_text())
    assert saved["completed_results"] == [{"keyword": "one"}]
    assert saved["recovery_errors"][0]["task_id"] == "failed"


def test_completed_publisher_without_durable_phase_state_requires_review(client):
    db = get_db_session()
    try:
        task, parent_run = _campaign_task(db)
        state = db.query(OrchestrationStateModel).filter_by(
            orchestrator_run_id=parent_run.run_id
        ).one()
        state.plan_json = "```json\n" + json.dumps({
            "phases": [{
                "phase": "publisher",
                "task_title": "Campaign: publisher",
                "execution_type": "campaign_publisher",
                "depends_on": [],
            }]
        }) + "\n```"
        state.phase_outputs_json = json.dumps({})
        state.child_run_ids_json = json.dumps([])
        child = TaskModel(
            title="Campaign: publisher",
            execution_type="campaign_publisher",
            parent_task_id=task.id,
            status="completed",
            created_at=_utcnow_iso(),
            updated_at=_utcnow_iso(),
        )
        db.add(child)
        db.commit()
        db.refresh(child)
        child_run = AgentRunModel(
            run_id="completed-publisher",
            task_id=child.id,
            parent_run_id=parent_run.run_id,
            status="completed",
            execution_type="campaign_publisher",
            write_capable=True,
            started_at=_old_timestamp(),
            finished_at=_utcnow_iso(),
        )
        db.add(child_run)
        parent_run.heartbeat_at = _old_timestamp()
        parent_run.lease_expires_at = _old_timestamp()
        db.commit()

        recover_stale_runs(db)

        db.refresh(parent_run)
        assert parent_run.status == "review_required"
        assert parent_run.recovery_state == "review_required"
        assert task.status == "blocked"
    finally:
        db.close()


def test_stale_worker_cannot_heartbeat_or_finalize_newer_run(client):
    db = get_db_session()
    try:
        task_data = client.post(
            "/tasks", json={"title": "Run ownership", "execution_type": "research"}
        ).json()
        task = db.query(TaskModel).filter_by(id=task_data["id"]).one()
        old_run = _create_run(db, task, "manual_execute", "research")
        task.active_run_id = None
        old_run.status = "review_required"
        db.commit()
        new_run = _create_run(db, task, "manual_execute", "research")
        old_heartbeat = old_run.heartbeat_at

        assert _heartbeat_run(db, old_run, record_event=False) is False
        db.refresh(old_run)
        assert old_run.heartbeat_at == old_heartbeat

        _finalize_run_failure(db, old_run, task, "late failure")

        db.refresh(task)
        db.refresh(new_run)
        assert task.active_run_id == new_run.run_id
        assert task.last_run_id == new_run.run_id
        assert task.status == "in_progress"
        assert new_run.status == "queued"
    finally:
        db.close()


def test_write_capable_failure_requires_review_and_blocks_retry(client):
    task_data = client.post(
        "/tasks", json={"title": "Unsafe write retry", "execution_type": "webflow_publish"}
    ).json()
    with patch(
        "agent.api.helpers._run_agent_prompt",
        new=AsyncMock(side_effect=TimeoutError("timed out")),
    ):
        response = client.post(f"/tasks/{task_data['id']}/execute")

    assert response.status_code == 200
    assert response.json()["status"] == "review_required"
    db = get_db_session()
    try:
        task = db.query(TaskModel).filter_by(id=task_data["id"]).one()
        assert task.status == "blocked"
        assert task.active_run_id is None
        latest = db.query(AgentRunModel).filter_by(task_id=task.id).one()
        assert latest.status == "review_required"
        retry = _create_run(db, task, "manual_execute", "webflow_publish")
        assert retry.run_id == latest.run_id
        assert retry._claim_created is False
    finally:
        db.close()


@pytest.mark.asyncio
async def test_comment_race_defers_when_manual_run_wins(client):
    from agent.api.helpers import process_one_comment_action

    task_data = client.post(
        "/tasks", json={"title": "Comment race", "execution_type": "research"}
    ).json()
    comment = client.post(
        f"/tasks/{task_data['id']}/comments", json={"body": "@agent revise this"}
    ).json()
    db = get_db_session()
    try:
        action = CommentActionModel(
            task_id=task_data["id"], comment_id=comment["id"], status="pending",
            attempts=0, max_attempts=2,
        )
        db.add(action)
        db.commit()
    finally:
        db.close()

    from agent.api import helpers as helpers_module
    original_create_run = helpers_module._create_run

    def manual_wins(db, task, *args, **kwargs):
        manual_run = original_create_run(db, task, "manual_execute", "research")
        manual_run._claim_created = False
        return manual_run

    with patch.object(helpers_module, "_create_run", side_effect=manual_wins), \
        patch("agent.api.helpers._run_agent_prompt", new=AsyncMock()) as run_agent:
        result = await process_one_comment_action(request_id="req-comment-race")

    assert result["status"] == "pending"
    run_agent.assert_not_awaited()
    db = get_db_session()
    try:
        run = db.query(AgentRunModel).filter_by(task_id=task_data["id"]).one()
        assert run.trigger_source == "manual_execute"
        assert run.request_id is None
        action = db.query(CommentActionModel).filter_by(comment_id=comment["id"]).one()
        action.status = "retry_exhausted"
        db.commit()
    finally:
        db.close()


@pytest.mark.asyncio
async def test_comment_autopilot_preserves_review_gate_for_write_task(client):
    from agent.api.helpers import process_one_comment_action

    task_data = client.post(
        "/tasks", json={"title": "Blocked comment write", "execution_type": "webflow_publish"}
    ).json()
    comment = client.post(
        f"/tasks/{task_data['id']}/comments", json={"body": "@agent publish this"}
    ).json()
    db = get_db_session()
    try:
        task = db.query(TaskModel).filter_by(id=task_data["id"]).one()
        run = _create_run(db, task, "manual_execute", "webflow_publish")
        _finalize_run_failure(db, run, task, "write failed")
        action = CommentActionModel(
            task_id=task.id, comment_id=comment["id"], status="pending",
            attempts=0, max_attempts=2,
        )
        db.add(action)
        db.commit()
    finally:
        db.close()

    with patch("agent.api.helpers._run_agent_prompt", new=AsyncMock()) as run_agent:
        result = await process_one_comment_action(request_id="req-blocked-comment")

    assert result["status"] == "review_required"
    run_agent.assert_not_awaited()


def test_dataforseo_empty_task_data_is_recoverable(tmp_path, monkeypatch):
    monkeypatch.setenv("DATAFORSEO_LOGIN", "login")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "password")
    monkeypatch.setattr("agent.dataforseo.client.MANIFEST_DIR", str(tmp_path))
    client = DataForSEOClient()
    manifest = client._write_manifest(
        "post", [{"keyword": "x"}], ["submitted-1"]
    )
    client._last_manifest_path = manifest
    with patch.object(client, "_task_post", return_value=["submitted-1"]), \
        patch.object(client, "_get", return_value={"status_code": 20000, "tasks": []}), \
        patch("agent.dataforseo.client.time.sleep"):
        with pytest.raises(DataForSEORecoveryError) as exc_info:
            client._task_post_and_poll("post", "get", [{"keyword": "x"}], max_wait=10)

    assert exc_info.value.errors[0]["task_id"] == "submitted-1"
    saved = json.loads(next(tmp_path.glob("*.json")).read_text())
    assert saved["recovery_errors"][0]["task_id"] == "submitted-1"


def test_dataforseo_partial_submission_is_reported_as_recovery(tmp_path, monkeypatch):
    monkeypatch.setenv("DATAFORSEO_LOGIN", "login")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "password")
    monkeypatch.setenv("DATAFORSEO_MAX_TASKS_PER_REQUEST", "1")
    monkeypatch.setattr("agent.dataforseo.client.MANIFEST_DIR", str(tmp_path))
    client = DataForSEOClient()
    responses = iter([
        {"status_code": 20000, "tasks": [{"id": "first", "status_code": 20100}]},
        {"status_code": 20000, "tasks": [{"status_code": 40000, "status_message": "bad"}]},
    ])
    with patch.object(client, "_post", side_effect=lambda *args: next(responses)):
        with pytest.raises(DataForSEORecoveryError) as exc_info:
            client._task_post("post", [{"keyword": "one"}, {"keyword": "two"}])

    assert exc_info.value.task_ids == ["first"]
    assert exc_info.value.manifest_path
    saved = json.loads(next(tmp_path.glob("*.json")).read_text())
    assert saved["tasks"][0]["task_id"] == "first"
    assert saved["submission_errors"]


def test_campaign_retry_reuses_saved_state_and_skips_completed_publisher(client):
    db = get_db_session()
    try:
        task, run = _campaign_task(db)
        state = db.query(OrchestrationStateModel).filter_by(
            orchestrator_run_id=run.run_id
        ).one()
        state.plan_json = "```json\n" + json.dumps({
            "phases": [
                {"phase": "publisher", "execution_type": "campaign_publisher", "depends_on": []},
                {"phase": "analyst", "execution_type": "campaign_analyst", "depends_on": ["publisher"]},
            ]
        }) + "\n```"
        state.phase_outputs_json = json.dumps({"publisher": "published"})
        state.child_run_ids_json = json.dumps([])
        state.status = "error"
        run.status = "failed"
        run.finished_at = _utcnow_iso()
        task.status = "blocked"
        task.active_run_id = None
        db.commit()
        task_id = task.id
        original_run_id = run.run_id
    finally:
        db.close()

    with patch(
        "agent.api.routers.tasks._execute_campaign_with_timeout",
        new=AsyncMock(return_value=None),
    ) as execute:
        response = client.post(f"/tasks/{task_id}/execute")

    assert response.status_code == 200
    assert response.json()["run_id"] == original_run_id
    execute.assert_awaited_once()
    assert execute.call_args.kwargs["resume"] is True


@pytest.mark.asyncio
async def test_stale_campaign_worker_stops_before_child_dispatch():
    with pytest.raises(orchestrator_module.LostRunOwnership):
        await orchestrator_module._dispatch_phase(
            None,
            {"phase": "researcher", "execution_type": "campaign_researcher"},
            1,
            "stale-parent",
            {},
            "goal",
            {},
            False,
            ownership_check=lambda: False,
        )


def test_finalizer_uses_atomic_ownership_condition(client):
    db = get_db_session()
    try:
        task_data = client.post(
            "/tasks", json={"title": "Atomic finalizer", "execution_type": "research"}
        ).json()
        task = db.query(TaskModel).filter_by(id=task_data["id"]).one()
        old_run = _create_run(db, task, "manual_execute", "research")
        task.active_run_id = None
        old_run.status = "review_required"
        db.commit()
        new_run = _create_run(db, task, "manual_execute", "research")

        with patch("agent.api.helpers._run_owns_task", return_value=True):
            _finalize_run_failure(db, old_run, task, "late worker")

        db.refresh(task)
        db.refresh(new_run)
        assert task.active_run_id == new_run.run_id
        assert task.last_run_id == new_run.run_id
        assert task.status == "in_progress"
        assert new_run.status == "queued"
    finally:
        db.close()


def test_partial_submission_network_error_is_recovery(tmp_path, monkeypatch):
    monkeypatch.setenv("DATAFORSEO_LOGIN", "login")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "password")
    monkeypatch.setenv("DATAFORSEO_MAX_TASKS_PER_REQUEST", "1")
    monkeypatch.setattr("agent.dataforseo.client.MANIFEST_DIR", str(tmp_path))
    client = DataForSEOClient()
    with patch.object(client, "_post", side_effect=[
        {"status_code": 20000, "tasks": [{"id": "paid-1", "status_code": 20100}]},
        DataForSEOError(503, "service unavailable"),
    ]):
        with pytest.raises(DataForSEORecoveryError) as exc_info:
            client._task_post("post", [{"keyword": "one"}, {"keyword": "two"}])

    assert exc_info.value.task_ids == ["paid-1"]
    assert "service unavailable" in exc_info.value.errors[0]["error"]
    manifest = json.loads(exc_info.value.manifest_path and open(exc_info.value.manifest_path).read())
    assert manifest["tasks"][0]["task_id"] == "paid-1"
    assert manifest["submission_errors"]


def test_direct_campaign_publisher_execution_requires_approval(client):
    task = client.post(
        "/tasks", json={"title": "Direct publisher", "execution_type": "campaign_publisher"}
    ).json()
    with patch("agent.api.helpers._run_agent_prompt", new=AsyncMock()) as run_agent:
        response = client.post(f"/tasks/{task['id']}/execute")

    assert response.status_code == 400
    run_agent.assert_not_awaited()
    db = get_db_session()
    try:
        assert db.query(AgentRunModel).filter_by(task_id=task["id"]).count() == 0
    finally:
        db.close()


def test_reclaimed_comment_action_ignores_old_worker(client):
    db = get_db_session()
    try:
        task_data = client.post(
            "/tasks", json={"title": "Comment lease owner", "execution_type": "research"}
        ).json()
        action = CommentActionModel(
            task_id=task_data["id"], comment_id=999991, status="running",
            attempts=1, max_attempts=2, run_id="new-worker", heartbeat_at=_utcnow_iso(),
            lease_expires_at=_utcnow_iso(), recovery_state="running",
        )
        db.add(action)
        db.commit()
        old_heartbeat = action.heartbeat_at
        assert _heartbeat_comment_action(db, action, expected_run_id="old-worker") is False
        db.refresh(action)
        assert action.heartbeat_at == old_heartbeat
    finally:
        db.close()


def test_pipeline_cli_reports_submitted_ids_and_partial_results(tmp_path, monkeypatch, capsys):
    class PartialClient(DataForSEOClient):
        def keyword_method(self, tasks):
            raise DataForSEORecoveryError(
                ["paid-1", "failed-2"], "/tmp/partial-manifest.json", "recover",
                results=[{"keyword": "ready"}],
                errors=[{"task_id": "failed-2", "error": "bad task"}],
            )

    monkeypatch.setenv("DATAFORSEO_LOGIN", "login")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "password")
    output = tmp_path / "partial.json"
    monkeypatch.setattr(
        "sys.argv", ["pipeline.py", "keyword_method", "--task", "{}", "--output", str(output)]
    )
    run_pipeline(PartialClient, "partial-pipeline")
    captured = capsys.readouterr().out
    assert "Submitted task IDs: paid-1, failed-2" in captured
    assert "Partial results: 1" in captured
    assert "2 submitted task(s)" in captured


@pytest.mark.asyncio
async def test_comment_autopilot_generates_request_id_when_missing(client):
    from agent.api.helpers import process_one_comment_action

    task = client.post(
        "/tasks", json={"title": "Background trace", "execution_type": "research"}
    ).json()
    cleanup_db = get_db_session()
    try:
        cleanup_db.query(CommentActionModel).delete()
        cleanup_db.query(CommentModel).delete()
        cleanup_db.commit()
    finally:
        cleanup_db.close()
    comment = client.post(
        f"/tasks/{task['id']}/comments", json={"body": "@agent revise"}
    ).json()
    db = get_db_session()
    try:
        db.add(CommentActionModel(task_id=task["id"], comment_id=comment["id"], status="pending"))
        db.commit()
    finally:
        db.close()
    with patch(
        "agent.api.helpers._run_agent_prompt",
        new=AsyncMock(return_value=SimpleNamespace(result_text="done", session_id=None)),
    ):
        result = await process_one_comment_action()
    assert result["status"] == "succeeded"
    db = get_db_session()
    try:
        run = db.query(AgentRunModel).filter_by(source_comment_id=comment["id"]).one()
        event = db.query(RunEventModel).filter_by(run_id=run.run_id, event_type="run_created").one()
        assert run.request_id
        assert event.request_id == run.request_id
    finally:
        db.close()


@pytest.mark.asyncio
async def test_retry_trace_records_final_exhausted_attempt(client):
    db = get_db_session()
    try:
        task_data = client.post(
            "/tasks", json={"title": "Retry exhausted trace", "execution_type": "research"}
        ).json()
        task = db.query(TaskModel).filter_by(id=task_data["id"]).one()
        run = _create_run(db, task, "manual_execute", "research")

        async def always_fails():
            raise RuntimeError("timed out")

        with patch("agent.orchestrator.asyncio.sleep", new=AsyncMock()):
            with pytest.raises(RuntimeError, match="timed out"):
                await _run_with_retry(
                    always_fails, max_retries=2, base_delay=0,
                    trace_db=db, trace_run_id=run.run_id,
                )
        events = db.query(RunEventModel).filter_by(
            run_id=run.run_id, event_type="retry"
        ).order_by(RunEventModel.id).all()
        assert [json.loads(event.payload)["attempt"] for event in events] == [1, 2]
        assert [event.outcome for event in events] == ["retrying", "exhausted"]
    finally:
        db.close()


def test_child_task_and_run_are_atomic(client):
    db = get_db_session()
    try:
        task_data = client.post(
            "/tasks", json={"title": "Atomic child parent", "execution_type": "orchestrate_seo_campaign"}
        ).json()
        parent = db.query(TaskModel).filter_by(id=task_data["id"]).one()
        parent_run = _create_run(db, parent, "manual_execute", parent.execution_type)
        with patch.object(db, "commit", side_effect=RuntimeError("simulated crash")):
            with pytest.raises(RuntimeError, match="simulated crash"):
                orchestrator_module._ensure_child_task_and_run(
                    db, parent,
                    {"phase": "researcher", "execution_type": "campaign_researcher"},
                    parent_run.run_id,
                )
        db.expire_all()
        assert db.query(TaskModel).filter(TaskModel.parent_task_id == parent.id).count() == 0
        assert db.query(AgentRunModel).filter(AgentRunModel.parent_run_id == parent_run.run_id).count() == 0
    finally:
        db.close()


@pytest.mark.asyncio
async def test_retry_persists_trace_event(client):
    db = get_db_session()
    try:
        task_data = client.post(
            "/tasks", json={"title": "Retry trace", "execution_type": "research"}
        ).json()
        task = db.query(TaskModel).filter_by(id=task_data["id"]).one()
        run = _create_run(db, task, "manual_execute", "research")
        attempts = 0

        async def flaky():
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("timed out")
            return "ok"

        result = await _run_with_retry(
            flaky, max_retries=2, base_delay=0, trace_db=db, trace_run_id=run.run_id
        )
        assert result == "ok"
        events = db.query(RunEventModel).filter_by(
            run_id=run.run_id, event_type="retry"
        ).all()
        assert len(events) == 1
        payload = json.loads(events[0].payload)
        assert payload["attempt"] == 1
        assert events[0].outcome == "retrying"
    finally:
        db.close()


def test_automation_route_propagates_request_id_to_comment_worker(client):
    with patch(
        "agent.api.routers.automation.process_one_comment_action",
        new=AsyncMock(return_value={"processed": False}),
    ) as process:
        response = client.post(
            "/automation/comments/process-one",
            headers={"X-Request-ID": "req-automation-comment"},
        )

    assert response.status_code == 200
    process.assert_awaited_once_with(request_id="req-automation-comment")


@pytest.mark.asyncio
async def test_comment_autopilot_run_stores_request_id(client):
    from agent.api.helpers import process_one_comment_action

    task_data = client.post(
        "/tasks", json={"title": "Comment request trace", "execution_type": "research"}
    ).json()
    comment = client.post(
        f"/tasks/{task_data['id']}/comments", json={"body": "@agent revise this"}
    ).json()
    db = get_db_session()
    try:
        db.add(CommentActionModel(
            task_id=task_data["id"], comment_id=comment["id"], status="pending",
            attempts=0, max_attempts=2,
        ))
        db.commit()
    finally:
        db.close()


    with patch(
        "agent.api.helpers._run_agent_prompt",
        new=AsyncMock(return_value=SimpleNamespace(result_text="revision", session_id=None)),
    ):
        result = await process_one_comment_action(request_id="req-comment-run")

    assert result["status"] == "succeeded"
    db = get_db_session()
    try:
        run = db.query(AgentRunModel).filter(
            AgentRunModel.source_comment_id == comment["id"]
        ).one()
        assert run.request_id == "req-comment-run"
    finally:
        db.close()


def _dispatch_test_helpers(agent_prompt):
    from agent.api.helpers import _is_write_capable

    return {
        "build_execution_prompt": lambda task, comments=None: "prompt",
        "_build_runtime_config": lambda *args, **kwargs: SimpleNamespace(),
        "_finalize_run_failure": _finalize_run_failure,
        "_finalize_run_success": lambda *args, **kwargs: True,
        "_mark_run_started": lambda db, run, *args: _mark_run_started_for_test(db, run),
        "_normalize_execution_result": lambda value: value,
        "_refresh_context_view": lambda *args, **kwargs: None,
        "_resolve_prompt_context": lambda *args, **kwargs: {},
        "_run_agent_prompt": agent_prompt,
        "_is_write_capable": _is_write_capable,
    }


def _mark_run_started_for_test(db, run):
    run.status = "running"
    run.write_capable = True
    db.commit()


@pytest.mark.asyncio
async def test_write_phase_timeout_is_uncertain_and_not_retried(client):
    from agent.orchestrator import _dispatch_phase

    db = get_db_session()
    try:
        parent_data = client.post(
            "/tasks", json={"title": "Uncertain write campaign", "execution_type": "orchestrate_seo_campaign"}
        ).json()
        parent = db.query(TaskModel).filter_by(id=parent_data["id"]).one()
        parent_run = _create_run(db, parent, "manual_execute", parent.execution_type)
        child = TaskModel(
            title="Campaign: publisher", execution_type="campaign_publisher",
            parent_task_id=parent.id, status="pending", created_at=_utcnow_iso(), updated_at=_utcnow_iso(),
        )
        db.add(child)
        db.commit()
        db.refresh(child)
        calls = 0

        async def uncertain(*args, **kwargs):
            nonlocal calls
            calls += 1
            raise RuntimeError("agent timed out after publish request")

        with pytest.raises(RuntimeError, match="timed out"):
            await _dispatch_phase(
                db,
                {"phase": "publisher", "execution_type": "campaign_publisher"},
                child.id, parent_run.run_id, {}, "goal",
                _dispatch_test_helpers(uncertain), False,
                ownership_check=lambda: True,
            )

        assert calls == 1
        child_run = db.query(AgentRunModel).filter_by(task_id=child.id).one()
        assert child_run.status == "review_required"
        assert child_run.write_capable is True
        assert "timed out" in child_run.error
    finally:
        db.close()


@pytest.mark.asyncio
async def test_write_phase_does_not_use_handoff_correction_retry(client):
    from agent.orchestrator import _dispatch_phase

    db = get_db_session()
    try:
        parent_data = client.post(
            "/tasks", json={"title": "Uncertain handoff", "execution_type": "orchestrate_seo_campaign"}
        ).json()
        parent = db.query(TaskModel).filter_by(id=parent_data["id"]).one()
        parent_run = _create_run(db, parent, "manual_execute", parent.execution_type)
        child = TaskModel(
            title="Campaign: publisher", execution_type="campaign_publisher",
            parent_task_id=parent.id, status="pending", created_at=_utcnow_iso(), updated_at=_utcnow_iso(),
        )
        db.add(child)
        db.commit()
        db.refresh(child)
        calls = 0

        async def published_without_handoff(*args, **kwargs):
            nonlocal calls
            calls += 1
            return SimpleNamespace(result_text="published", session_id=None)

        with pytest.raises(RuntimeError, match="handoff correction"):
            await _dispatch_phase(
                db,
                {"phase": "publisher", "execution_type": "campaign_publisher"},
                child.id, parent_run.run_id, {}, "goal",
                _dispatch_test_helpers(published_without_handoff), True,
                ownership_check=lambda: True,
            )

        assert calls == 1
        child_run = db.query(AgentRunModel).filter_by(task_id=child.id).one()
        assert child_run.status == "review_required"
    finally:
        db.close()


def test_campaign_retry_is_blocked_by_failed_publisher_child(client):
    db = get_db_session()
    try:
        task, parent_run = _campaign_task(db)
        state = db.query(OrchestrationStateModel).filter_by(
            orchestrator_run_id=parent_run.run_id
        ).one()
        state.status = "error"
        state.plan_json = "```json\n" + json.dumps({"phases": [
            {"phase": "publisher", "execution_type": "campaign_publisher", "depends_on": []}
        ]}) + "\n```"
        parent_run.status = "failed"
        task.status = "blocked"
        task.active_run_id = None
        child = TaskModel(
            title="Campaign: publisher", execution_type="campaign_publisher",
            parent_task_id=task.id, status="blocked", created_at=_utcnow_iso(), updated_at=_utcnow_iso(),
        )
        db.add(child)
        db.commit()
        db.refresh(child)
        child_run = AgentRunModel(
            run_id="failed-publisher-child", task_id=child.id, parent_run_id=parent_run.run_id,
            status="review_required", recovery_state="review_required",
            execution_type="campaign_publisher", write_capable=True,
            error="write result uncertain", started_at=_utcnow_iso(),
        )
        db.add(child_run)
        db.commit()
        task_id = task.id
    finally:
        db.close()

    with patch("agent.api.routers.tasks._execute_campaign_with_timeout", new=AsyncMock()) as execute:
        response = client.post(f"/tasks/{task_id}/execute")

    assert response.status_code == 200
    assert response.json()["status"] == "review_required"
    execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_lost_campaign_ownership_cancels_child_agent_call(client):
    from agent.orchestrator import _dispatch_phase

    db = get_db_session()
    try:
        parent_data = client.post(
            "/tasks", json={"title": "Cancel stale campaign", "execution_type": "orchestrate_seo_campaign"}
        ).json()
        parent = db.query(TaskModel).filter_by(id=parent_data["id"]).one()
        parent_run = _create_run(db, parent, "manual_execute", parent.execution_type)
        child = TaskModel(
            title="Campaign: publisher", execution_type="campaign_publisher",
            parent_task_id=parent.id, status="pending", created_at=_utcnow_iso(), updated_at=_utcnow_iso(),
        )
        db.add(child)
        db.commit()
        db.refresh(child)
        checks = 0
        started = asyncio.Event()
        cancelled = asyncio.Event()

        def ownership():
            nonlocal checks
            checks += 1
            return checks < 4

        async def long_agent(*args, **kwargs):
            started.set()
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                cancelled.set()
                raise

        work = asyncio.create_task(_dispatch_phase(
            db,
            {"phase": "publisher", "execution_type": "campaign_publisher"},
            child.id, parent_run.run_id, {}, "goal",
            _dispatch_test_helpers(long_agent), False,
            ownership_check=ownership,
        ))
        await asyncio.wait_for(started.wait(), timeout=1)
        with pytest.raises(orchestrator_module.LostRunOwnership):
            await asyncio.wait_for(work, timeout=1)
        assert cancelled.is_set()
    finally:
        db.close()


def test_new_campaign_does_not_reuse_old_child_run(client):
    from agent.orchestrator import _create_child_run

    db = get_db_session()
    try:
        task, old_parent = _campaign_task(db)
        task.active_run_id = None
        old_parent.status = "review_required"
        child = TaskModel(
            title="Campaign: researcher", execution_type="campaign_researcher",
            parent_task_id=task.id, status="in_progress", created_at=_utcnow_iso(), updated_at=_utcnow_iso(),
        )
        db.add(child)
        db.commit()
        db.refresh(child)
        old_child = AgentRunModel(
            run_id="old-child-run", task_id=child.id, parent_run_id=old_parent.run_id,
            status="running", execution_type="campaign_researcher", started_at=_utcnow_iso(),
        )
        db.add(old_child)
        child.active_run_id = old_child.run_id
        db.commit()
        new_parent = _create_run(db, task, "manual_execute", task.execution_type)

        new_child = _create_child_run(db, child, new_parent.run_id, "campaign_researcher")

        assert new_child.run_id != old_child.run_id
        assert new_child.parent_run_id == new_parent.run_id
        assert child.active_run_id == new_child.run_id
    finally:
        db.close()


@pytest.mark.asyncio
async def test_comment_autopilot_requires_approval_for_campaign_publisher(client):
    from agent.api.helpers import process_one_comment_action

    task = client.post(
        "/tasks", json={"title": "Publisher comment approval", "execution_type": "campaign_publisher"}
    ).json()
    comment = client.post(
        f"/tasks/{task['id']}/comments", json={"body": "@agent publish this"}
    ).json()
    db = get_db_session()
    try:
        db.add(CommentActionModel(
            task_id=task["id"], comment_id=comment["id"], status="pending", attempts=0, max_attempts=2,
        ))
        db.commit()
    finally:
        db.close()

    with patch("agent.api.helpers._run_agent_prompt", new=AsyncMock()) as run_agent:
        result = await process_one_comment_action(request_id="req-approval-comment")

    assert result["status"] == "review_required"
    run_agent.assert_not_awaited()
    db = get_db_session()
    try:
        assert db.query(AgentRunModel).filter_by(task_id=task["id"]).count() == 0
    finally:
        db.close()


def test_comment_lease_requires_current_task_run_ownership(client):
    from agent.api.helpers import _update_comment_action_if_owned

    db = get_db_session()
    try:
        task_data = client.post(
            "/tasks", json={"title": "Comment owner check", "execution_type": "research"}
        ).json()
        task = db.query(TaskModel).filter_by(id=task_data["id"]).one()
        old_run = _create_run(db, task, "manual_execute", "research")
        task.active_run_id = None
        old_run.status = "review_required"
        db.commit()
        new_run = _create_run(db, task, "manual_execute", "research")
        action = CommentActionModel(
            task_id=task.id, comment_id=999992, run_id=old_run.run_id, status="running",
            attempts=1, max_attempts=2, heartbeat_at=_utcnow_iso(),
            lease_expires_at=_lease_expires_at_for_test(), recovery_state="running",
        )
        db.add(action)
        db.commit()
        assert _heartbeat_comment_action(db, action, expected_run_id=old_run.run_id) is False
        assert _update_comment_action_if_owned(
            db, action.id, old_run.run_id, {CommentActionModel.status: "succeeded"}
        ) is False
        db.refresh(action)
        assert action.status == "running"
        assert new_run.run_id == task.active_run_id
    finally:
        db.close()


def _lease_expires_at_for_test():
    return (datetime.utcnow() + timedelta(minutes=5)).isoformat()


def test_stale_approval_campaign_with_queued_publisher_has_resume_path(client):
    db = get_db_session()
    try:
        task, parent_run = _campaign_task(db)
        state = db.query(OrchestrationStateModel).filter_by(
            orchestrator_run_id=parent_run.run_id
        ).one()
        state.status = "awaiting_approval"
        state.plan_json = "```json\n" + json.dumps({"phases": [
            {"phase": "publisher", "execution_type": "campaign_publisher", "depends_on": []}
        ]}) + "\n```"
        child = TaskModel(
            title="Campaign: publisher", execution_type="campaign_publisher",
            parent_task_id=task.id, status="pending", created_at=_utcnow_iso(), updated_at=_utcnow_iso(),
        )
        db.add(child)
        db.commit()
        db.refresh(child)
        child_run = AgentRunModel(
            run_id="queued-approval-publisher", task_id=child.id, parent_run_id=parent_run.run_id,
            status="queued", execution_type="campaign_publisher", write_capable=True,
            started_at=_utcnow_iso(),
        )
        db.add(child_run)
        parent_run.heartbeat_at = _old_timestamp()
        parent_run.lease_expires_at = _old_timestamp()
        db.commit()

        recover_stale_runs(db)
        db.refresh(parent_run)
        assert parent_run.status == "review_required"
        assert _claim_campaign_resume(db, parent_run.run_id, request_id="req-resume") is True
        db.refresh(parent_run)
        assert parent_run.status == "resuming"
    finally:
        db.close()


@pytest.mark.asyncio
async def test_retry_deadline_records_exhausted_trace(client):
    db = get_db_session()
    try:
        task_data = client.post(
            "/tasks", json={"title": "Deadline trace", "execution_type": "research"}
        ).json()
        task = db.query(TaskModel).filter_by(id=task_data["id"]).one()
        run = _create_run(db, task, "manual_execute", "research")

        async def fails():
            raise RuntimeError("timed out")

        clock = iter([0.0, 0.0, 1.0])
        with patch("agent.orchestrator.time.monotonic", side_effect=lambda: next(clock)), \
             patch("agent.orchestrator.asyncio.sleep", new=AsyncMock()):
            with pytest.raises(RuntimeError):
                await _run_with_retry(
                    fails, max_retries=3, base_delay=1, max_total_seconds=0.5,
                    trace_db=db, trace_run_id=run.run_id,
                )
        events = db.query(RunEventModel).filter_by(
            run_id=run.run_id, event_type="retry"
        ).order_by(RunEventModel.id).all()
        assert events[-1].outcome == "exhausted"
        assert json.loads(events[-1].payload)["attempt"] == 1
    finally:
        db.close()


def test_resume_request_id_is_stored_on_run_and_event(client):
    db = get_db_session()
    try:
        task, run = _campaign_task(db)
        assert _claim_campaign_resume(db, run.run_id, request_id="req-resume-trace") is True
        db.refresh(run)
        assert run.request_id == "req-resume-trace"
        event = db.query(RunEventModel).filter_by(
            run_id=run.run_id, event_type="campaign_resume"
        ).one()
        assert event.request_id == "req-resume-trace"
    finally:
        db.close()


def test_validation_failed_write_run_is_a_review_gate(client):
    task_data = client.post(
        "/tasks", json={"title": "Validation write gate", "execution_type": "webflow_publish"}
    ).json()
    db = get_db_session()
    try:
        task = db.query(TaskModel).filter_by(id=task_data["id"]).one()
        task.approved_at = _utcnow_iso()
        db.commit()
        run = _create_run(db, task, "manual_execute", "webflow_publish")
        _finalize_run_success(
            db,
            run,
            task,
            "The publisher wrote, but the output was invalid.",
            None,
            ValidationResult(status="failed", message="missing publish confirmation"),
        )
        db.refresh(run)
        assert run.status == "review_required"
        assert task.status == "blocked"
        task_id = task.id
        run_id = run.run_id
    finally:
        db.close()

    with patch("agent.api.helpers._run_agent_prompt", new=AsyncMock()) as run_agent:
        response = client.post(f"/tasks/{task_id}/execute")

    assert response.status_code == 200
    assert response.json()["run_id"] == run_id
    assert response.json()["status"] == "review_required"
    run_agent.assert_not_awaited()


def test_uncertain_dataforseo_post_is_not_retried_and_is_manifested(tmp_path, monkeypatch):
    monkeypatch.setenv("DATAFORSEO_LOGIN", "login")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "password")
    monkeypatch.setattr("agent.dataforseo.client.MANIFEST_DIR", str(tmp_path))
    client = DataForSEOClient()
    payload = [{"keyword": "uncertain"}]
    with patch.object(
        client.session,
        "request",
        side_effect=requests.exceptions.ReadTimeout("response lost after acceptance"),
    ) as request:
        with pytest.raises(DataForSEORecoveryError) as exc_info:
            client._task_post("serp/google/organic/task_post", payload)

    assert request.call_count == 1
    assert exc_info.value.task_ids == []
    manifest = json.loads((tmp_path / next(p.name for p in tmp_path.glob("*.json"))).read_text())
    assert manifest["unknown_requests"] == payload
    assert manifest["submission_errors"][0]["status"] == "unknown"


@pytest.mark.parametrize("failure", [
    "server_error",
    "malformed_response",
])
def test_uncertain_dataforseo_first_post_failure_is_manifested_without_retry(
    tmp_path, monkeypatch, failure
):
    monkeypatch.setenv("DATAFORSEO_LOGIN", "login")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "password")
    monkeypatch.setattr("agent.dataforseo.client.MANIFEST_DIR", str(tmp_path))
    client = DataForSEOClient()
    payload = [{"keyword": failure}]

    if failure == "server_error":
        response = requests.Response()
        response.status_code = 503
        response.reason = "upstream unavailable"
        request_side_effect = [response]
    else:
        response = requests.Response()
        response.status_code = 200
        response.json = lambda: (_ for _ in ()).throw(ValueError("invalid JSON"))
        request_side_effect = [response]

    with patch.object(
        client.session, "request", side_effect=request_side_effect
    ) as request:
        with pytest.raises(DataForSEORecoveryError) as exc_info:
            client._task_post("serp/google/organic/task_post", payload)

    assert request.call_count == 1
    assert exc_info.value.task_ids == []
    manifest_path = next(tmp_path.glob("*.json"))
    manifest = json.loads(manifest_path.read_text())
    assert manifest["unknown_requests"] == payload
    assert manifest["submission_errors"][0]["status"] == "unknown"


def test_recoverable_read_only_campaign_real_orchestration_resumes_incomplete_phase(
    client,
):
    db = get_db_session()
    try:
        task, run = _campaign_task(db)
        state = db.query(OrchestrationStateModel).filter_by(
            orchestrator_run_id=run.run_id
        ).one()
        state.status = "running"
        state.plan_json = "```json\n" + json.dumps({"phases": [
            {
                "phase": "researcher",
                "execution_type": "campaign_researcher",
                "depends_on": [],
            },
            {
                "phase": "analyst",
                "execution_type": "campaign_analyst",
                "depends_on": ["researcher"],
            },
        ]}) + "\n```"
        state.phase_outputs_json = json.dumps({"researcher": "saved result"})
        state.child_run_ids_json = json.dumps(["saved-researcher-child"])
        run.status = "recoverable"
        run.recovery_state = "recoverable"
        task.status = "pending"
        task.active_run_id = None
        db.commit()
        task_id = task.id
        run_id = run.run_id
    finally:
        db.close()

    async def dispatch_only_pending_phase(*args, **kwargs):
        phase_spec = args[1]
        return phase_spec["phase"], "analyst result", False

    dispatch = AsyncMock(side_effect=dispatch_only_pending_phase)
    with patch("agent.orchestrator._dispatch_phase", new=dispatch):
        response = client.post(f"/tasks/{task_id}/execute")

    assert response.status_code == 200
    assert response.json()["run_id"] == run_id
    assert response.json()["status"] == "completed"
    assert dispatch.call_count == 1
    assert dispatch.call_args.args[1]["phase"] == "analyst"


@pytest.mark.asyncio
async def test_normal_worker_stops_when_run_ownership_is_lost(client):
    db = get_db_session()
    try:
        task_data = client.post(
            "/tasks", json={"title": "Ownership cancellation", "execution_type": "research"}
        ).json()
        task = db.query(TaskModel).filter_by(id=task_data["id"]).one()
        run = _create_run(db, task, "manual_execute", "research")
        config = SimpleNamespace(_heartbeat_db=db, _heartbeat_run_id=run.run_id)
    finally:
        db.close()

    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def long_agent(*args, **kwargs):
        started.set()
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    with patch("agent.api.helpers.RUN_HEARTBEAT_INTERVAL_SECONDS", 0.01), \
        patch("agent.api.helpers._heartbeat_run", return_value=False), \
        patch("agent.api.helpers.SEOAgent.create_and_run_result", new=long_agent):
        with pytest.raises(RuntimeError, match="ownership"):
            await _run_agent_prompt("work", config, {})

    assert started.is_set()
    assert cancelled.is_set()


@pytest.mark.asyncio
async def test_comment_worker_stops_when_action_ownership_is_lost(client):
    db = get_db_session()
    try:
        task_data = client.post(
            "/tasks", json={"title": "Comment ownership cancellation", "execution_type": "research"}
        ).json()
        task = db.query(TaskModel).filter_by(id=task_data["id"]).one()
        run = _create_run(db, task, "comment_autopilot", "research")
        config = SimpleNamespace(
            _heartbeat_db=db,
            _heartbeat_run_id=run.run_id,
            _comment_action=object(),
            _comment_action_run_id=run.run_id,
        )
    finally:
        db.close()

    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def long_agent(*args, **kwargs):
        started.set()
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    with patch("agent.api.helpers.RUN_HEARTBEAT_INTERVAL_SECONDS", 0.01), \
        patch("agent.api.helpers._heartbeat_run", return_value=True), \
        patch("agent.api.helpers._heartbeat_comment_action", return_value=False), \
        patch("agent.api.helpers.SEOAgent.create_and_run_result", new=long_agent):
        with pytest.raises(RuntimeError, match="ownership"):
            await _run_agent_prompt("comment work", config, {})

    assert started.is_set()
    assert cancelled.is_set()


def test_recoverable_read_only_campaign_execute_resumes_saved_state(client):
    db = get_db_session()
    try:
        task, run = _campaign_task(db)
        state = db.query(OrchestrationStateModel).filter_by(
            orchestrator_run_id=run.run_id
        ).one()
        state.status = "running"
        state.plan_json = "```json\n" + json.dumps({"phases": [
            {"phase": "researcher", "execution_type": "campaign_researcher", "depends_on": []},
            {"phase": "analyst", "execution_type": "campaign_analyst", "depends_on": ["researcher"]},
        ]}) + "\n```"
        state.phase_outputs_json = json.dumps({"researcher": "saved result"})
        state.child_run_ids_json = json.dumps(["saved-child-run"])
        run.status = "recoverable"
        run.recovery_state = "recoverable"
        task.status = "pending"
        task.active_run_id = None
        db.commit()
        task_id = task.id
        run_id = run.run_id
    finally:
        db.close()

    with patch(
        "agent.api.routers.tasks._execute_campaign_with_timeout",
        new=AsyncMock(return_value=None),
    ) as execute:
        response = client.post(f"/tasks/{task_id}/execute")

    assert response.status_code == 200
    assert response.json()["run_id"] == run_id
    execute.assert_awaited_once()
    assert execute.call_args.kwargs["resume"] is True


def test_active_campaign_resume_returns_existing_run_without_second_dispatch(client):
    db = get_db_session()
    try:
        task, run = _campaign_task(db)
        state = db.query(OrchestrationStateModel).filter_by(
            orchestrator_run_id=run.run_id
        ).one()
        run.status = "running"
        state.status = "running"
        db.commit()
        task_id = task.id
        run_id = run.run_id
    finally:
        db.close()

    with patch(
        "agent.api.routers.tasks._execute_campaign_with_timeout",
        new=AsyncMock(),
    ) as execute:
        response = client.post(f"/tasks/{task_id}/execute?resume=true")

    assert response.status_code == 200
    assert response.json()["run_id"] == run_id
    assert response.json()["status"] == "running"
    execute.assert_not_awaited()


def test_failed_campaign_retry_with_completed_publisher_missing_output_requires_review(client):
    db = get_db_session()
    try:
        task, parent_run = _campaign_task(db)
        state = db.query(OrchestrationStateModel).filter_by(
            orchestrator_run_id=parent_run.run_id
        ).one()
        state.status = "error"
        state.plan_json = "```json\n" + json.dumps({"phases": [
            {"phase": "publisher", "execution_type": "campaign_publisher", "depends_on": []}
        ]}) + "\n```"
        state.phase_outputs_json = json.dumps({})
        state.child_run_ids_json = json.dumps([])
        parent_run.status = "failed"
        task.status = "blocked"
        task.active_run_id = None
        child = TaskModel(
            title="Campaign: publisher", execution_type="campaign_publisher",
            parent_task_id=task.id, status="completed",
            created_at=_utcnow_iso(), updated_at=_utcnow_iso(),
        )
        db.add(child)
        db.commit()
        db.refresh(child)
        db.add(AgentRunModel(
            run_id="completed-publisher-cycle-7", task_id=child.id,
            parent_run_id=parent_run.run_id, status="completed",
            execution_type="campaign_publisher", write_capable=True,
            started_at=_old_timestamp(), finished_at=_utcnow_iso(),
        ))
        db.commit()
        task_id = task.id
    finally:
        db.close()

    with patch(
        "agent.api.routers.tasks._execute_campaign_with_timeout",
        new=AsyncMock(),
    ) as execute:
        response = client.post(f"/tasks/{task_id}/execute")

    assert response.status_code == 200
    assert response.json()["status"] == "review_required"
    execute.assert_not_awaited()


def test_campaign_retry_with_running_publisher_child_is_reviewed_not_restarted(client):
    db = get_db_session()
    try:
        task, parent_run = _campaign_task(db)
        state = db.query(OrchestrationStateModel).filter_by(
            orchestrator_run_id=parent_run.run_id
        ).one()
        state.status = "error"
        state.plan_json = "```json\n" + json.dumps({"phases": [
            {"phase": "publisher", "execution_type": "campaign_publisher", "depends_on": []}
        ]}) + "\n```"
        parent_run.status = "failed"
        task.status = "blocked"
        task.active_run_id = None
        child = TaskModel(
            title="Campaign: publisher", execution_type="campaign_publisher",
            parent_task_id=task.id, status="in_progress",
            created_at=_utcnow_iso(), updated_at=_utcnow_iso(),
        )
        db.add(child)
        db.commit()
        db.refresh(child)
        child_run = AgentRunModel(
            run_id="running-publisher-cycle-7", task_id=child.id,
            parent_run_id=parent_run.run_id, status="running",
            execution_type="campaign_publisher", write_capable=True,
            started_at=_utcnow_iso(),
        )
        db.add(child_run)
        child.active_run_id = child_run.run_id
        db.commit()
        task_id = task.id
    finally:
        db.close()

    with patch(
        "agent.api.routers.tasks._execute_campaign_with_timeout",
        new=AsyncMock(),
    ) as execute:
        response = client.post(f"/tasks/{task_id}/execute")

    assert response.status_code == 200
    assert response.json()["status"] == "review_required"
    execute.assert_not_awaited()


@pytest.mark.parametrize("poll_error", [ValueError("invalid JSON"), requests.exceptions.HTTPError("400 bad request")])
def test_dataforseo_polling_error_is_recovery_with_partial_results(
    tmp_path, monkeypatch, poll_error
):
    monkeypatch.setenv("DATAFORSEO_LOGIN", "login")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "password")
    monkeypatch.setattr("agent.dataforseo.client.MANIFEST_DIR", str(tmp_path))
    client = DataForSEOClient()
    manifest = client._write_manifest(
        "post", [{"keyword": "one"}, {"keyword": "two"}], ["ready", "broken"]
    )
    client._last_manifest_path = manifest
    with patch.object(client, "_task_post", return_value=["ready", "broken"]), \
        patch.object(client, "_task_get", side_effect=[
            {"tasks": [{"result": [{"keyword": "one"}]}]}, poll_error
        ]), \
        patch("agent.dataforseo.client.time.sleep"), \
        patch("agent.dataforseo.client.time.monotonic", side_effect=[0.0, 1.0]):
        with pytest.raises(DataForSEORecoveryError) as exc_info:
            client._task_post_and_poll("post", "get", [{"keyword": "x"}], max_wait=10)

    assert exc_info.value.task_ids == ["broken"]
    assert exc_info.value.results == [{"keyword": "one"}]
    assert exc_info.value.errors[0]["task_id"] == "broken"
    saved = json.loads((tmp_path / manifest.rsplit("/", 1)[-1]).read_text())
    assert saved["completed_results"] == [{"keyword": "one"}]
    assert saved["recovery_errors"][0]["task_id"] == "broken"


@pytest.mark.parametrize("review_status", ["review_required", "needs_review"])
def test_write_review_gate_survives_client_task_status_change(client, review_status):
    task_data = client.post(
        "/tasks", json={"title": "Persistent review gate", "execution_type": "webflow_publish"}
    ).json()
    db = get_db_session()
    try:
        task = db.query(TaskModel).filter_by(id=task_data["id"]).one()
        task.approved_at = _utcnow_iso()
        run = _create_run(db, task, "manual_execute", "webflow_publish")
        run.status = review_status
        run.recovery_state = "review_required" if review_status == "review_required" else "none"
        run.validator_status = "failed"
        task.status = "pending"
        task.active_run_id = None
        db.commit()
        task_id = task.id
        run_id = run.run_id
    finally:
        db.close()

    with patch("agent.api.helpers._run_agent_prompt", new=AsyncMock()) as run_agent:
        response = client.post(f"/tasks/{task_id}/execute")

    assert response.status_code == 200
    assert response.json()["run_id"] == run_id
    assert response.json()["status"] == review_status
    run_agent.assert_not_awaited()


@pytest.mark.asyncio
async def test_write_agent_stops_when_heartbeat_database_fails(client):
    class BrokenHeartbeatDB:
        def query(self, *args, **kwargs):
            raise RuntimeError("database unavailable")

    config = SimpleNamespace(
        _heartbeat_db=BrokenHeartbeatDB(),
        _heartbeat_run_id="write-run",
        _write_capable=True,
    )
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def long_agent(*args, **kwargs):
        started.set()
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    with patch("agent.api.helpers.RUN_HEARTBEAT_INTERVAL_SECONDS", 0.01), \
        patch("agent.api.helpers.SEOAgent.create_and_run_result", new=long_agent):
        with pytest.raises(RunOwnershipLost, match="ownership"):
            await _run_agent_prompt("write", config, {})

    assert started.is_set()
    assert cancelled.is_set()
