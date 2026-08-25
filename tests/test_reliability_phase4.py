"""Phase 4 tests: health reports dependency state without side effects."""

from unittest.mock import Mock, patch

from agent.api.main import app


def test_health_reports_database_and_disabled_worker(client):
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"]["status"] == "ok"
    assert body["worker"]["status"] == "disabled"
    assert "secret" not in response.text.lower()


def test_health_reports_database_failure_without_internal_error(client):
    broken = Mock()
    broken.execute.side_effect = RuntimeError("database password leaked")
    broken.close.return_value = None
    with patch("agent.db.get_db_session", return_value=broken):
        response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] != "ok"
    assert body["database"]["status"] == "unavailable"
    assert "password" not in response.text.lower()


def test_health_reports_failed_worker(client):
    failed_worker = Mock()
    failed_worker.done.return_value = True
    failed_worker.cancelled.return_value = False
    previous = app.state.comment_autopilot_task
    app.state.comment_autopilot_task = failed_worker
    try:
        with patch("agent.api.main._autopilot_enabled", return_value=True):
            response = client.get("/health")
    finally:
        app.state.comment_autopilot_task = previous

    assert response.status_code == 200
    body = response.json()
    assert body["status"] != "ok"
    assert body["worker"]["status"] == "failed"
