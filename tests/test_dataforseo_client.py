"""
Tests for DataForSEOClient's HTTP layer: status checking and cumulative
cost tracking. All tests mock requests.Session.request — no real network
calls, no real billing.
"""
import pytest
from unittest.mock import MagicMock, patch

import agent.dataforseo.logger as logger_module
from agent.dataforseo.client import DataForSEOClient, DataForSEOError


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
