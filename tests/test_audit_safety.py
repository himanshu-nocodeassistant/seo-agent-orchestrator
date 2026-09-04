"""Audit payloads contain metadata, not secrets or unbounded text."""

import json


def test_run_event_redacts_secrets_and_bounds_log_text(client):
    from agent.api.main import RunEventModel, TaskModel, _create_run, _log_run_event, get_db_session

    db = get_db_session()
    try:
        task = client.post("/tasks", json={"title": "Audit task"}).json()
        db_task = db.get(TaskModel, task["id"])
        run = _create_run(db, db_task, "test", "manual")
        _log_run_event(db, run.run_id, "tool_use", {"access_token": "secret", "text": "x" * 5000})
        event = (
            db.query(RunEventModel)
            .filter(RunEventModel.run_id == run.run_id, RunEventModel.event_type == "tool_use")
            .one()
        )
        payload = json.loads(event.payload)
        assert "secret" not in event.payload
        assert payload["access_token"] == "[redacted]"
        assert payload["text"].endswith("[truncated]")
        assert len(payload["text"]) < 5000
    finally:
        db.close()
