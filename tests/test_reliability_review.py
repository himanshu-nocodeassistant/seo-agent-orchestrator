"""Regression tests found during the independent reliability review."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from agent.api.helpers import (
    _acquire_next_comment_action,
    _create_run,
    build_post_tool_use_hook,
)
from agent.api.main import (
    AgentRunModel,
    CommentActionModel,
    RunEventModel,
    TaskModel,
    get_db_session,
)
from agent.dataforseo.client import DataForSEOClient, DataForSEOError


def test_manual_execution_builds_trace_hook_with_run_session(client):
    task = client.post(
        "/tasks", json={"title": "Trace manual work", "execution_type": "research"}
    ).json()
    captured = {}

    def build_config(profile, resume_session_id, **kwargs):
        captured.update(kwargs)
        return object()

    with patch("agent.api.routers.tasks._build_runtime_config", side_effect=build_config), patch(
        "agent.api.helpers._run_agent_prompt",
        new=AsyncMock(return_value=SimpleNamespace(result_text="done", session_id=None)),
    ):
        response = client.post(f"/tasks/{task['id']}/execute")

    assert response.status_code == 200
    assert captured["run_id"] == response.json()["run_id"]
    assert captured["db"] is not None


def test_tool_use_refreshes_run_lease(client):
    task = client.post(
        "/tasks", json={"title": "Heartbeat trace", "execution_type": "research"}
    ).json()
    db = get_db_session()
    try:
        task_model = db.query(TaskModel).filter_by(id=task["id"]).one()
        run = _create_run(db, task_model, "manual_execute", "research")
        with patch("agent.api.helpers._heartbeat_run") as heartbeat:
            hook = build_post_tool_use_hook(db, run.run_id)
            import asyncio

            asyncio.run(hook({"tool_name": "Read", "tool_input": {}}, "session-1", None))
        heartbeat.assert_called_once_with(db, run, "session-1", record_event=False)
    finally:
        db.close()


def test_run_created_event_has_request_id_column(client):
    task = client.post(
        "/tasks", json={"title": "Trace identifiers", "execution_type": "research"}
    ).json()
    db = get_db_session()
    try:
        task_model = db.query(TaskModel).filter_by(id=task["id"]).one()
        run = _create_run(
            db, task_model, "manual_execute", "research", request_id="req-review"
        )
        event = db.query(RunEventModel).filter_by(run_id=run.run_id).one()
        assert event.request_id == "req-review"
    finally:
        db.close()


def test_seo_audit_stores_request_id(client):
    with patch(
        "agent.api.helpers._run_agent_prompt",
        new=AsyncMock(
            return_value=SimpleNamespace(
                result_text="Audit found keyword volume. Source: https://example.com",
                session_id=None,
            )
        ),
    ):
        response = client.post(
            "/runs/audit-review/seo-audit",
            headers={"X-Request-ID": "req-audit-review"},
        )

    assert response.status_code == 200
    run = client.get(f"/runs/{response.json()['run_id']}").json()
    assert run["request_id"] == "req-audit-review"


def test_partial_success_in_batch_is_written_to_recovery_manifest(client, tmp_path, monkeypatch):
    monkeypatch.setenv("DATAFORSEO_MAX_TASKS_PER_REQUEST", "2")
    monkeypatch.setattr("agent.dataforseo.client.MANIFEST_DIR", str(tmp_path))
    client_obj = DataForSEOClient(login="login", password="password")
    response = {
        "status_code": 20000,
        "tasks": [
            {"id": "submitted-1", "status_code": 20100},
            {"id": "failed-2", "status_code": 40000, "status_message": "bad task"},
        ],
    }

    with patch.object(client_obj, "_post", return_value=response):
        with pytest.raises(DataForSEOError):
            client_obj._task_post(
                "serp/google/organic/task_post", [{"keyword": "one"}, {"keyword": "two"}]
            )

    manifests = list(tmp_path.glob("*.json"))
    assert len(manifests) == 1
    saved = json.loads(manifests[0].read_text())
    assert [item["task_id"] for item in saved["tasks"]] == ["submitted-1"]


@pytest.mark.asyncio
async def test_comment_autopilot_does_not_run_on_an_existing_active_run(client):
    task = client.post(
        "/tasks", json={"title": "Active comment task", "execution_type": "research"}
    ).json()
    comment = client.post(
        f"/tasks/{task['id']}/comments", json={"body": "@agent revise this"}
    ).json()
    db = get_db_session()
    try:
        task_model = db.query(TaskModel).filter_by(id=task["id"]).one()
        action = CommentActionModel(
            task_id=task["id"],
            comment_id=comment["id"],
            status="pending",
            attempts=0,
            max_attempts=2,
        )
        db.add(action)
        db.commit()
        existing = _create_run(db, task_model, "manual_execute", "research")
    finally:
        db.close()

    with patch("agent.api.helpers._run_agent_prompt", new=AsyncMock()) as run_agent:
        result = await __import__("agent.api.helpers", fromlist=["process_one_comment_action"]).process_one_comment_action()

    assert result["processed"] is True
    assert result["status"] == "pending"
    run_agent.assert_not_awaited()
    db = get_db_session()
    try:
        run = db.query(AgentRunModel).filter_by(run_id=existing.run_id).one()
        assert run.status == "queued"
        action = db.query(CommentActionModel).filter_by(comment_id=comment["id"]).one()
        action.status = "retry_exhausted"
        db.commit()
    finally:
        db.close()
