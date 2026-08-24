"""
Tests for DataForSEOClient's HTTP layer: status checking and cumulative
cost tracking. All tests mock requests.Session.request — no real network
calls, no real billing.
"""
import json
import pytest
from unittest.mock import MagicMock, Mock, patch

import agent.dataforseo.logger as logger_module
from agent.dataforseo.client import (
    DataForSEOClient,
    DataForSEOError,
    DataForSEORecoveryError,
    TaskNotReadyError,
    _jittered_backoff,
    _TokenBucket,
)


@pytest.fixture(autouse=True)
def isolated_logs_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(logger_module, "LOGS_DIR", tmp_path)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DATAFORSEO_LOGIN", "test@example.com")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "test-password")
    return DataForSEOClient()


def _fake_response(status_code=200, json_data=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.raise_for_status.return_value = None
    resp.headers = {}
    return resp


class TestCostTracking:
    def test_starts_at_zero(self, client):
        assert client.total_cost == 0.0

    def test_post_accumulates_cost(self, client):
        data = {"status_code": 20000, "status_message": "Ok.", "cost": 0.1, "tasks": []}
        with patch.object(client.session, "request", return_value=_fake_response(json_data=data)):
            client._post("some/endpoint", [{"keyword": "x"}])
        assert client.total_cost == pytest.approx(0.1)

    def test_get_accumulates_cost(self, client):
        data = {"status_code": 20000, "status_message": "Ok.", "cost": 0.02, "tasks": []}
        with patch.object(client.session, "request", return_value=_fake_response(json_data=data)):
            client._get("some/endpoint")
        assert client.total_cost == pytest.approx(0.02)

    def test_multiple_calls_accumulate(self, client):
        data = {"status_code": 20000, "status_message": "Ok.", "cost": 0.05, "tasks": []}
        with patch.object(client.session, "request", return_value=_fake_response(json_data=data)):
            client._post("a", [])
            client._get("b")
            client._post("c", [])
        assert client.total_cost == pytest.approx(0.15)

    def test_missing_cost_field_defaults_to_zero(self, client):
        data = {"status_code": 20000, "status_message": "Ok.", "tasks": []}
        with patch.object(client.session, "request", return_value=_fake_response(json_data=data)):
            client._post("some/endpoint", [])
        assert client.total_cost == 0.0

    def test_cost_tracked_even_when_call_ultimately_errors(self, client):
        """A response that fails _check_status may still report real spend —
        never discard billed cost just because the call errored downstream."""
        data = {"status_code": 40000, "status_message": "Rejected", "cost": 0.02, "tasks": []}
        with patch.object(client.session, "request", return_value=_fake_response(json_data=data)):
            with pytest.raises(DataForSEOError):
                client._post("some/endpoint", [])
        assert client.total_cost == pytest.approx(0.02)

    def test_each_client_instance_tracks_its_own_cost(self, monkeypatch):
        monkeypatch.setenv("DATAFORSEO_LOGIN", "test@example.com")
        monkeypatch.setenv("DATAFORSEO_PASSWORD", "test-password")
        client_a = DataForSEOClient()
        client_b = DataForSEOClient()
        data = {"status_code": 20000, "status_message": "Ok.", "cost": 0.1, "tasks": []}
        with patch.object(client_a.session, "request", return_value=_fake_response(json_data=data)):
            client_a._post("some/endpoint", [])
        assert client_a.total_cost == pytest.approx(0.1)
        assert client_b.total_cost == 0.0


def _created_tasks_response(count: int):
    """A task_post response marking every task as created (status 20100)."""
    return {
        "status_code": 20000,
        "status_message": "Ok.",
        "tasks": [
            {
                "id": f"task-{i}",
                "status_code": 20100,
                "status_message": "Ok.",
            }
            for i in range(count)
        ],
    }


class TestTaskPostChunking:
    def test_payload_chunked_and_single_manifest(self, client, monkeypatch):
        """25 tasks with a 10-task cap => 3 POSTs (10/10/5), one manifest."""
        monkeypatch.setenv("DATAFORSEO_MAX_TASKS_PER_REQUEST", "10")
        tasks = [{"keyword": f"kw-{i}"} for i in range(25)]
        posted = []

        def fake_post(endpoint, payload):
            posted.append(payload)
            return _created_tasks_response(len(payload))

        bucket = Mock()
        with patch.object(client, "_post", side_effect=fake_post), \
             patch.object(client, "_write_manifest") as mock_manifest, \
             patch("agent.dataforseo.client._get_task_bucket", return_value=bucket):
            ids = client._task_post("serp/google/organic/task_post", tasks)

        assert [len(p) for p in posted] == [10, 10, 5]
        assert len(ids) == 25
        # one token per task, consumed per chunk
        assert bucket.consume.call_count == 3
        assert [c.args[0] for c in bucket.consume.call_args_list] == [10, 10, 5]
        # a single manifest covering all chunks
        manifest_payload = mock_manifest.call_args[0][1]
        assert len(manifest_payload) == 25

    def test_empty_payload_returns_without_posting(self, client):
        with patch.object(client, "_post") as mock_post, \
             patch.object(client, "_write_manifest") as mock_manifest:
            assert client._task_post("x/task_post", []) == []
        mock_post.assert_not_called()
        mock_manifest.assert_not_called()


class TestTaskPostAndPoll:
    def test_polls_all_pending_tasks_per_round(self, client, monkeypatch):
        """t1 ready on round 1, t2 not ready until round 2 — both are checked
        each round, and only t2 is polled in round 2."""
        monkeypatch.setenv("DATAFORSEO_MAX_TASKS_PER_REQUEST", "100")
        with patch.object(client, "_task_post", return_value=["t1", "t2"]), \
             patch.object(
                 client,
                 "_task_get",
                 side_effect=[
                     {"tasks": [{"result": [{"keyword": "a"}]}]},
                     TaskNotReadyError(40601, "not ready"),
                     {"tasks": [{"result": [{"keyword": "b"}]}]},
                 ],
             ) as mock_get, \
             patch("agent.dataforseo.client.time.sleep") as mock_sleep:
            results = client._task_post_and_poll(
                "p", "g", [{"keyword": "x"}], poll_interval=1, max_wait=60
            )

        assert results == [{"keyword": "a"}, {"keyword": "b"}]
        assert mock_get.call_count == 3
        # two rounds of sleeping, not per-task
        assert mock_sleep.call_count == 2

    def test_skips_stragglers_after_global_deadline(self, client, monkeypatch):
        monkeypatch.setenv("DATAFORSEO_MAX_TASKS_PER_REQUEST", "100")
        with patch.object(client, "_task_post", return_value=["slow"]), \
             patch.object(
                 client,
                 "_task_get",
                 side_effect=TaskNotReadyError(40601, "not ready"),
             ), \
             patch("agent.dataforseo.client.time.sleep"), \
             patch("agent.dataforseo.client.time.monotonic", side_effect=[0.0, 1000.0]):
            with pytest.raises(DataForSEORecoveryError) as exc_info:
                client._task_post_and_poll(
                    "p", "g", [{"keyword": "x"}], poll_interval=1, max_wait=10
                )
        assert exc_info.value.task_ids == ["slow"]


class TestBackoff:
    def test_jittered_backoff_bounded_by_cap(self, monkeypatch):
        monkeypatch.setattr(
            "agent.dataforseo.client.random.uniform",
            lambda a, b: (a + b) / 2,
        )
        assert _jittered_backoff(0) == pytest.approx(1.0)   # uniform(0, 2)
        assert _jittered_backoff(10) == pytest.approx(15.0)  # capped at 30

    def test_retry_after_header_respected(self, client):
        retryable = _fake_response(status_code=429)
        retryable.headers = {"Retry-After": "3"}
        ok = _fake_response(status_code=200, json_data={"status_code": 20000})
        with patch.object(
            client.session, "request", side_effect=[retryable, ok]
        ), patch("agent.dataforseo.client.time.sleep") as mock_sleep:
            client._get("some/endpoint")
        mock_sleep.assert_called_once_with(3.0)


class TestManifestWrite:
    def test_manifest_written_atomically(self, client, monkeypatch, tmp_path):
        monkeypatch.setattr("agent.dataforseo.client.MANIFEST_DIR", str(tmp_path))
        with patch.object(
            client,
            "_post",
            return_value=_created_tasks_response(1),
        ):
            ids = client._task_post("serp/google/organic/task_post", [{"keyword": "x"}])

        assert ids == ["task-0"]
        manifests = list(tmp_path.glob("*.json"))
        assert len(manifests) == 1
        manifest = json.loads(manifests[0].read_text())
        assert manifest["tasks"][0]["task_id"] == "task-0"
        assert list(tmp_path.glob("*.tmp")) == []


class TestTokenBucket:
    def test_consumes_tokens_without_blocking_when_available(self):
        bucket = _TokenBucket(60)
        bucket.consume(10)
        assert bucket.tokens == pytest.approx(50, abs=0.01)

    def test_refills_over_time(self, monkeypatch):
        bucket = _TokenBucket(60)  # 1 token/second
        bucket.tokens = 0
        bucket.updated_at = 100.0
        with patch(
            "agent.dataforseo.client.time.monotonic",
            side_effect=[100.0, 101.0],
        ), patch("agent.dataforseo.client.time.sleep"):
            bucket.consume(1)
        assert bucket.tokens == pytest.approx(0.0, abs=0.01)
