"""
Tests for GoogleSearchConsoleClient — Search Analytics and URL Inspection methods.
All Google API calls are mocked so no credentials are required.
"""

import asyncio
import pytest
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch


def run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_client():
    from unittest.mock import MagicMock
    from agent.gsc.client import GoogleSearchConsoleClient
    from agent.gsc.config import GoogleSearchConsoleConfig

    config = MagicMock(spec=GoogleSearchConsoleConfig)
    config.credentials_path = MagicMock()
    config.credentials_path.__str__ = lambda s: "/fake/creds.json"
    config.site_url = "sc-domain:nocodeassistant.agency"
    return GoogleSearchConsoleClient(config)


def _mock_webmasters_service(client, rows):
    """Inject a mock webmasters service that returns the given rows."""
    service = MagicMock()
    service.searchanalytics().query().execute.return_value = {"rows": rows}
    client._webmasters_service = service
    return service


def _mock_searchconsole_service(client, inspection_result):
    """Inject a mock searchconsole service that returns the given inspection result."""
    service = MagicMock()
    service.urlInspection().index().inspect().execute.return_value = {
        "inspectionResult": inspection_result
    }
    client._searchconsole_service = service
    return service


# ---------------------------------------------------------------------------
# Search Analytics tests
# ---------------------------------------------------------------------------

class TestGetPageMetrics:
    def test_returns_metrics_when_data_exists(self):
        client = _make_client()
        _mock_webmasters_service(client, [{
            "clicks": 42, "impressions": 1000, "ctr": 0.042, "position": 3.5
        }])
        result = run(client.get_page_metrics(
            "https://nocodeassistant.agency/weweb-agency", "2026-01-01", "2026-01-28"
        ))
        assert result["clicks"] == 42
        assert result["impressions"] == 1000
        assert result["ctr"] == pytest.approx(0.042)
        assert result["position"] == pytest.approx(3.5)

    def test_returns_zeros_when_no_rows(self):
        client = _make_client()
        _mock_webmasters_service(client, [])
        result = run(client.get_page_metrics(
            "https://nocodeassistant.agency/weweb-agency", "2026-01-01", "2026-01-28"
        ))
        assert result == {"clicks": 0, "impressions": 0, "ctr": 0.0, "position": 0.0}

    def test_raises_on_api_error(self):
        from agent.gsc.client import GoogleSearchConsoleError
        client = _make_client()
        service = MagicMock()
        service.searchanalytics().query().execute.side_effect = Exception("quota exceeded")
        client._webmasters_service = service
        with pytest.raises(GoogleSearchConsoleError, match="quota exceeded"):
            run(client.get_page_metrics(
                "https://nocodeassistant.agency/", "2026-01-01", "2026-01-28"
            ))


class TestGetPageMetricsRange:
    def test_data_available_false_when_change_too_recent(self):
        client = _make_client()
        today = date.today()
        result = run(client.get_page_metrics_range(
            url="https://nocodeassistant.agency/",
            change_date=str(today),  # change today — after window hasn't started
        ))
        assert result["data_available"] is False

    def test_computes_deltas(self):
        client = _make_client()
        call_count = 0

        async def fake_get_metrics(url, start, end):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"clicks": 10, "impressions": 500, "ctr": 0.02, "position": 5.0}
            return {"clicks": 15, "impressions": 600, "ctr": 0.025, "position": 4.5}

        client.get_page_metrics = fake_get_metrics

        old_date = str(date.today() - timedelta(days=60))
        result = run(client.get_page_metrics_range(
            url="https://nocodeassistant.agency/", change_date=old_date
        ))
        assert result["data_available"] is True
        assert result["delta"]["clicks_delta"] == 5
        assert result["delta"]["impressions_delta"] == 100
        assert result["delta"]["ctr_delta"] == pytest.approx(0.005, abs=1e-7)
        assert result["delta"]["position_delta"] == pytest.approx(-0.5, abs=1e-7)


# ---------------------------------------------------------------------------
# URL Inspection tests
# ---------------------------------------------------------------------------

def _make_inspection_response(inspection_result):
    """Build a mock discovery service that returns the given inspection result."""
    svc = MagicMock()
    svc.urlInspection().index().inspect().execute.return_value = {
        "inspectionResult": inspection_result
    }
    return svc


class TestInspectUrl:
    def test_indexed_page(self):
        inspection_result = {
            "indexStatusResult": {
                "verdict": "PASS",
                "coverageState": "Submitted and indexed",
                "robotsTxtState": "ALLOWED",
                "indexingState": "INDEXING_ALLOWED",
                "lastCrawlTime": "2026-04-20T10:00:00Z",
                "pageFetchState": "SUCCESSFUL",
                "googleCanonical": "https://nocodeassistant.agency/weweb-agency",
                "userCanonical": "https://nocodeassistant.agency/weweb-agency",
                "sitemap": ["https://nocodeassistant.agency/sitemap.xml"],
                "referringUrls": [],
            },
            "mobileUsabilityResult": {"verdict": "PASS"},
            "richResultsResult": {"verdict": "VERDICT_UNSPECIFIED"},
        }
        client = _make_client()
        with patch("agent.gsc.client.discovery.build", return_value=_make_inspection_response(inspection_result)), \
             patch("agent.gsc.client.service_account.Credentials.from_service_account_file"):
            result = run(client.inspect_url("https://nocodeassistant.agency/weweb-agency"))
        assert result["is_indexed"] is True
        assert result["verdict"] == "PASS"
        assert result["coverage_state"] == "Submitted and indexed"
        assert result["google_canonical"] == "https://nocodeassistant.agency/weweb-agency"
        assert result["mobile_usability_verdict"] == "PASS"

    def test_not_indexed_page(self):
        inspection_result = {
            "indexStatusResult": {
                "verdict": "NEUTRAL",
                "coverageState": "Crawled - currently not indexed",
                "robotsTxtState": "ALLOWED",
                "indexingState": "INDEXING_ALLOWED",
                "lastCrawlTime": "2026-04-01T08:00:00Z",
                "pageFetchState": "SUCCESSFUL",
            },
            "mobileUsabilityResult": {},
            "richResultsResult": {},
        }
        client = _make_client()
        with patch("agent.gsc.client.discovery.build", return_value=_make_inspection_response(inspection_result)), \
             patch("agent.gsc.client.service_account.Credentials.from_service_account_file"):
            result = run(client.inspect_url("https://nocodeassistant.agency/some-page"))
        assert result["is_indexed"] is False
        assert result["verdict"] == "NEUTRAL"
        assert result["coverage_state"] == "Crawled - currently not indexed"

    def test_raises_on_api_error(self):
        from agent.gsc.client import GoogleSearchConsoleError
        svc = MagicMock()
        svc.urlInspection().index().inspect().execute.side_effect = Exception("403 Forbidden")
        client = _make_client()
        with patch("agent.gsc.client.discovery.build", return_value=svc), \
             patch("agent.gsc.client.service_account.Credentials.from_service_account_file"):
            with pytest.raises(GoogleSearchConsoleError, match="403 Forbidden"):
                run(client.inspect_url("https://nocodeassistant.agency/"))


class TestInspectUrls:
    def test_bulk_returns_all_results(self):
        client = _make_client()
        call_results = [
            {"url": "https://nocodeassistant.agency/a", "is_indexed": True, "verdict": "PASS"},
            {"url": "https://nocodeassistant.agency/b", "is_indexed": False, "verdict": "NEUTRAL"},
        ]
        idx = 0

        async def fake_inspect(url):
            nonlocal idx
            r = call_results[idx]
            idx += 1
            return r

        client.inspect_url = fake_inspect
        results = run(client.inspect_urls([
            "https://nocodeassistant.agency/a",
            "https://nocodeassistant.agency/b",
        ]))
        assert len(results) == 2
        assert results[0]["is_indexed"] is True
        assert results[1]["is_indexed"] is False

    def test_bulk_handles_individual_errors_gracefully(self):
        from agent.gsc.client import GoogleSearchConsoleError
        client = _make_client()

        async def fake_inspect(url):
            raise GoogleSearchConsoleError("rate limit")

        client.inspect_url = fake_inspect
        results = run(client.inspect_urls(["https://nocodeassistant.agency/broken"]))
        assert results[0]["verdict"] == "ERROR"
        assert results[0]["is_indexed"] is False
        assert "rate limit" in results[0]["error"]
