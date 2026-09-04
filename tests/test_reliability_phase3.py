"""Phase 3 tests: run tracing is useful and safe."""

import json
from types import SimpleNamespace
from unittest.mock import patch

from agent.api.helpers import _log_run_event, build_post_tool_use_hook
from agent.api.main import AgentRunModel, RunEventModel, get_db_session


def test_tool_input_redacts_known_credentials(client):
    task = client.post(
        "/tasks", json={"title": "Trace me", "execution_type": "research"}
    ).json()
    db = get_db_session()
    try:
        run = AgentRunModel(
            run_id="trace-redaction-run",
            task_id=task["id"],
            request_id="trace-request",
            status="running",
            execution_type="research",
            trigger_source="test",
            validator_status="pending",
            started_at="2026-01-01T00:00:00",
        )
        db.add(run)
        db.commit()
        hook = build_post_tool_use_hook(db, run.run_id)

        import asyncio

        asyncio.run(
            hook(
                {
                    "tool_name": "http_request",
                    "tool_input": {
                        "api_key": "secret-key",
                        "nested": {"password": "secret-password"},
                        "query": "safe",
                    },
                    "tool_use_id": "tool-1",
                },
                "session-1",
                None,
            )
        )
        event = db.query(RunEventModel).filter_by(run_id=run.run_id).one()
        payload = json.loads(event.payload)
        assert payload["tool_input"]["api_key"] == "[REDACTED]"
        assert payload["tool_input"]["nested"]["password"] == "[REDACTED]"
        assert payload["tool_input"]["query"] == "safe"
        assert event.request_id == "trace-request"
        assert event.session_id == "session-1"
    finally:
        db.close()


def test_run_events_endpoint_paginates_with_bounded_limit(client):
    task = client.post(
        "/tasks", json={"title": "Events", "execution_type": "research"}
    ).json()
    db = get_db_session()
    try:
        run = AgentRunModel(
            run_id="trace-page-run",
            task_id=task["id"],
            request_id="page-request",
            status="running",
            execution_type="research",
            trigger_source="test",
            validator_status="pending",
            started_at="2026-01-01T00:00:00",
        )
        db.add(run)
        db.commit()
        for index in range(3):
            _log_run_event(db, run.run_id, f"event_{index}")
    finally:
        db.close()

    response = client.get("/runs/trace-page-run/events?page=2&limit=1")
    assert response.status_code == 200
    body = response.json()
    assert body["page"] == 2
    assert body["limit"] == 1
    assert body["total"] == 3
    assert len(body["events"]) == 1
    assert body["events"][0]["request_id"] == "page-request"

    bounded = client.get("/runs/trace-page-run/events?limit=9999")
    assert bounded.status_code == 200
    assert bounded.json()["limit"] <= 200


def test_oversized_trace_payload_is_bounded(client):
    db = get_db_session()
    try:
        _log_run_event(db, "unlinked-run", "large", {"text": "x" * 200_000})
        event = db.query(RunEventModel).filter_by(run_id="unlinked-run").one()
        assert len(event.payload.encode("utf-8")) <= 100_000
        assert json.loads(event.payload)["_truncated"] is True
    finally:
        db.close()


def test_trace_write_failure_does_not_escape():
    class BrokenDb:
        def add(self, item):
            pass

        def commit(self):
            raise RuntimeError("trace storage is down")

        def rollback(self):
            pass

        def query(self, model):
            raise RuntimeError("trace lookup is down")

    with patch("agent.api.helpers.logger.exception"):
        _log_run_event(BrokenDb(), "run", "failure")
