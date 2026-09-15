"""Phase 5 tests: active runs have leases and safe stale recovery."""

from datetime import datetime, timedelta

from agent.api.helpers import (
    _create_run,
    _heartbeat_run,
    _utcnow_iso,
    recover_stale_runs,
)
from agent.api.main import AgentRunModel, RunEventModel, TaskModel, get_db_session


def _old_timestamp(minutes=16):
    return (datetime.utcnow() - timedelta(minutes=minutes)).isoformat()


def test_new_run_has_lease_and_heartbeat(client):
    task_data = client.post(
        "/tasks", json={"title": "Leased", "execution_type": "research"}
    ).json()
    db = get_db_session()
    try:
        task = db.query(TaskModel).filter_by(id=task_data["id"]).one()
        run = _create_run(db, task, "manual_execute", "research")
        assert run.heartbeat_at
        assert run.lease_expires_at
        assert run.recovery_state == "none"
    finally:
        db.close()


def test_heartbeat_keeps_current_run_active(client):
    task_data = client.post(
        "/tasks", json={"title": "Heartbeat", "execution_type": "research"}
    ).json()
    db = get_db_session()
    try:
        task = db.query(TaskModel).filter_by(id=task_data["id"]).one()
        run = _create_run(db, task, "manual_execute", "research")
        old_heartbeat = run.heartbeat_at
        _heartbeat_run(db, run, session_id="session-1")
        assert run.heartbeat_at >= old_heartbeat
        assert run.session_id == "session-1"
        assert run.status == "queued"
    finally:
        db.close()


def test_stale_read_only_run_becomes_recoverable(client):
    task_data = client.post(
        "/tasks", json={"title": "Recover read", "execution_type": "research"}
    ).json()
    db = get_db_session()
    try:
        task = db.query(TaskModel).filter_by(id=task_data["id"]).one()
        run = _create_run(db, task, "manual_execute", "research")
        run.status = "running"
        run.heartbeat_at = _old_timestamp()
        run.lease_expires_at = _old_timestamp()
        db.commit()

        recovered = recover_stale_runs(db)

        assert run.run_id in {item.run_id for item in recovered}
        assert run.status == "recoverable"
        assert run.recovery_state == "recoverable"
        db.refresh(task)
        assert task.active_run_id is None
        event = (
            db.query(RunEventModel)
            .filter_by(run_id=run.run_id, event_type="run_recovery")
            .one()
        )
        assert "recoverable" in event.payload
    finally:
        db.close()


def test_stale_write_run_requires_review_and_is_not_retried(client):
    task_data = client.post(
        "/tasks", json={"title": "Recover write", "execution_type": "rewrite_title"}
    ).json()
    db = get_db_session()
    try:
        task = db.query(TaskModel).filter_by(id=task_data["id"]).one()
        run = _create_run(db, task, "manual_execute", "rewrite_title")
        run.status = "running"
        run.heartbeat_at = _old_timestamp()
        run.lease_expires_at = _old_timestamp()
        db.commit()

        recover_stale_runs(db)

        assert run.status == "review_required"
        assert run.recovery_state == "review_required"
        db.refresh(task)
        assert task.status == "blocked"
        assert task.active_run_id is None
    finally:
        db.close()


def test_current_heartbeat_is_not_reclaimed(client):
    task_data = client.post(
        "/tasks", json={"title": "Still alive", "execution_type": "research"}
    ).json()
    db = get_db_session()
    try:
        task = db.query(TaskModel).filter_by(id=task_data["id"]).one()
        run = _create_run(db, task, "manual_execute", "research")
        run.status = "running"
        run.heartbeat_at = _utcnow_iso()
        db.commit()

        assert recover_stale_runs(db) == []
        assert run.status == "running"
    finally:
        db.close()
