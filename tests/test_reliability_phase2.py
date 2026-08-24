"""Phase 2 tests: DataForSEO requests remain bounded and recoverable."""

import json
from unittest.mock import patch

import pytest

from agent.dataforseo.client import (
    DataForSEORecoveryError,
    DataForSEOClient,
    TaskNotReadyError,
)


def _response(status_code=200, data=None, headers=None):
    class Response:
        reason = "OK"

        def __init__(self):
            self.status_code = status_code
            self.headers = headers or {}

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(self.status_code)

        def json(self):
            return data or {"status_code": 20000, "tasks": []}

    return Response()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DATAFORSEO_LOGIN", "login")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "password")
    return DataForSEOClient()


def test_every_request_has_connect_and_read_timeout(client):
    with patch.object(client.session, "request", return_value=_response()) as request:
        client._get("some/endpoint")

    timeout = request.call_args.kwargs["timeout"]
    assert isinstance(timeout, tuple)
    assert timeout[0] > 0
    assert timeout[1] > 0


def test_retry_after_delay_is_capped(client):
    retry = _response(429, headers={"Retry-After": "9999"})
    ok = _response()
    with patch.object(client.session, "request", side_effect=[retry, ok]), patch(
        "agent.dataforseo.client.time.sleep"
    ) as sleep:
        client._get("some/endpoint")

    assert sleep.call_args.args[0] <= 30


def test_manifest_survives_failure_after_first_batch(client, tmp_path, monkeypatch):
    monkeypatch.setenv("DATAFORSEO_MAX_TASKS_PER_REQUEST", "1")
    monkeypatch.setattr("agent.dataforseo.client.MANIFEST_DIR", str(tmp_path))
    created = {"status_code": 20000, "tasks": [{"id": "submitted-1", "status_code": 20100}]}

    with patch.object(client, "_post", side_effect=[created, RuntimeError("second batch")]):
        with pytest.raises(RuntimeError, match="second batch"):
            client._task_post("serp/google/organic/task_post", [{"keyword": "one"}, {"keyword": "two"}])

    manifests = list(tmp_path.glob("*.json"))
    assert len(manifests) == 1
    saved = json.loads(manifests[0].read_text())
    assert [task["task_id"] for task in saved["tasks"]] == ["submitted-1"]


def test_manifest_names_are_collision_safe(client, tmp_path, monkeypatch):
    monkeypatch.setattr("agent.dataforseo.client.MANIFEST_DIR", str(tmp_path))
    first = client._write_manifest("endpoint", [{"keyword": "one"}], ["one"])
    second = client._write_manifest("endpoint", [{"keyword": "two"}], ["two"])

    assert first != second
    assert len(list(tmp_path.glob("*.json"))) == 2


def test_poll_timeout_preserves_ids_and_manifest(client, monkeypatch):
    monkeypatch.setattr(client, "_task_post", lambda endpoint, payload: ["task-1"])
    client._last_manifest_path = "/tmp/recovery-manifest.json"
    monkeypatch.setattr(client, "_task_get", lambda endpoint, task_id: (_ for _ in ()).throw(TaskNotReadyError(40601, "queued")))
    monkeypatch.setattr("agent.dataforseo.client.time.sleep", lambda seconds: None)
    clock = iter([0.0, 1801.0])
    monkeypatch.setattr("agent.dataforseo.client.time.monotonic", lambda: next(clock))

    with pytest.raises(DataForSEORecoveryError) as exc_info:
        client._task_post_and_poll("post", "get", [{"keyword": "one"}], max_wait=1800)

    error = exc_info.value
    assert error.task_ids == ["task-1"]
    assert error.manifest_path
