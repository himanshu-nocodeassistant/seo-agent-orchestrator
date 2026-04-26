"""
Tests for the GSC API endpoints (/gsc/inspect, /gsc/inspect-bulk, /gsc/page-metrics).
Uses TestClient with a mocked GSC client — no real credentials needed.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from agent.api.main import app
    return TestClient(app)


def _mock_gsc_client(monkeypatch, inspect_result=None, bulk_result=None, metrics_result=None):
    """Patch _get_gsc_client to return a mock with async methods."""
    mock = MagicMock()
    if inspect_result is not None:
        mock.inspect_url = AsyncMock(return_value=inspect_result)
    if bulk_result is not None:
        mock.inspect_urls = AsyncMock(return_value=bulk_result)
    if metrics_result is not None:
        mock.get_page_metrics_range = AsyncMock(return_value=metrics_result)
    monkeypatch.setattr("agent.api.main._get_gsc_client", lambda: mock)
    return mock


# ---------------------------------------------------------------------------
# /gsc/inspect
# ---------------------------------------------------------------------------

class TestInspectEndpoint:
    def test_returns_inspection_result(self, client, monkeypatch):
        _mock_gsc_client(monkeypatch, inspect_result={
            "url": "https://nocodeassistant.agency/weweb-agency",
            "verdict": "PASS",
            "is_indexed": True,
            "coverage_state": "Submitted and indexed",
        })
        resp = client.get("/gsc/inspect", params={"url": "https://nocodeassistant.agency/weweb-agency"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_indexed"] is True
        assert data["verdict"] == "PASS"

    def test_503_when_not_configured(self, client, monkeypatch):
        monkeypatch.setattr("agent.api.main._get_gsc_client", lambda: None)
        resp = client.get("/gsc/inspect", params={"url": "https://nocodeassistant.agency/"})
        assert resp.status_code == 503

    def test_500_on_api_error(self, client, monkeypatch):
        from agent.gsc.client import GoogleSearchConsoleError
        mock = MagicMock()
        mock.inspect_url = AsyncMock(side_effect=GoogleSearchConsoleError("API down"))
        monkeypatch.setattr("agent.api.main._get_gsc_client", lambda: mock)
        resp = client.get("/gsc/inspect", params={"url": "https://nocodeassistant.agency/"})
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# /gsc/inspect-bulk
# ---------------------------------------------------------------------------

class TestInspectBulkEndpoint:
    def test_returns_summary_and_results(self, client, monkeypatch):
        _mock_gsc_client(monkeypatch, bulk_result=[
            {"url": "https://nocodeassistant.agency/a", "is_indexed": True, "verdict": "PASS"},
            {"url": "https://nocodeassistant.agency/b", "is_indexed": False, "verdict": "NEUTRAL"},
        ])
        resp = client.post("/gsc/inspect-bulk", json={"urls": [
            "https://nocodeassistant.agency/a",
            "https://nocodeassistant.agency/b",
        ]})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert data["indexed_count"] == 1
        assert data["not_indexed_count"] == 1
        assert data["error_count"] == 0

    def test_400_on_empty_urls(self, client, monkeypatch):
        _mock_gsc_client(monkeypatch, bulk_result=[])
        resp = client.post("/gsc/inspect-bulk", json={"urls": []})
        assert resp.status_code == 400

    def test_400_on_too_many_urls(self, client, monkeypatch):
        _mock_gsc_client(monkeypatch, bulk_result=[])
        resp = client.post("/gsc/inspect-bulk", json={"urls": [f"https://example.com/{i}" for i in range(101)]})
        assert resp.status_code == 400

    def test_503_when_not_configured(self, client, monkeypatch):
        monkeypatch.setattr("agent.api.main._get_gsc_client", lambda: None)
        resp = client.post("/gsc/inspect-bulk", json={"urls": ["https://nocodeassistant.agency/"]})
        assert resp.status_code == 503

    def test_error_urls_counted_separately(self, client, monkeypatch):
        _mock_gsc_client(monkeypatch, bulk_result=[
            {"url": "https://nocodeassistant.agency/a", "is_indexed": True, "verdict": "PASS"},
            {"url": "https://nocodeassistant.agency/b", "is_indexed": False, "verdict": "ERROR", "error": "timeout"},
        ])
        resp = client.post("/gsc/inspect-bulk", json={"urls": [
            "https://nocodeassistant.agency/a",
            "https://nocodeassistant.agency/b",
        ]})
        data = resp.json()
        assert data["error_count"] == 1
        assert data["not_indexed_count"] == 0


# ---------------------------------------------------------------------------
# /gsc/page-metrics
# ---------------------------------------------------------------------------

class TestPageMetricsEndpoint:
    def test_returns_before_after_metrics(self, client, monkeypatch):
        _mock_gsc_client(monkeypatch, metrics_result={
            "url": "https://nocodeassistant.agency/weweb-agency",
            "before": {"clicks": 10, "impressions": 500, "ctr": 0.02, "position": 5.0},
            "after": {"clicks": 15, "impressions": 600, "ctr": 0.025, "position": 4.5},
            "delta": {"clicks_delta": 5, "impressions_delta": 100, "ctr_delta": 0.005, "position_delta": -0.5},
            "data_available": True,
        })
        resp = client.get("/gsc/page-metrics", params={
            "url": "https://nocodeassistant.agency/weweb-agency",
            "change_date": "2026-01-01",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["data_available"] is True
        assert data["delta"]["clicks_delta"] == 5

    def test_503_when_not_configured(self, client, monkeypatch):
        monkeypatch.setattr("agent.api.main._get_gsc_client", lambda: None)
        resp = client.get("/gsc/page-metrics", params={
            "url": "https://nocodeassistant.agency/",
            "change_date": "2026-01-01",
        })
        assert resp.status_code == 503
