import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def gsc_env(fake_credentials_path):
    from agent.gsc import GscConfig

    return GscConfig(site_url="sc-domain:example.com", credentials_path=fake_credentials_path)


def test_gsc_page_metrics_aggregates_one_page_period(gsc_env):
    from agent.gsc import GscAPIClient

    client = GscAPIClient(gsc_env)
    client.query_search_analytics = AsyncMock(
        return_value={"rows": [{"clicks": 12, "impressions": 200, "ctr": 0.06, "position": 4.5}]}
    )

    import asyncio

    result = asyncio.run(client.get_page_metrics("https://example.com/page", "2026-02-01", "2026-02-28"))

    assert result == {"clicks": 12, "impressions": 200, "ctr": 0.06, "position": 4.5}
    client.query_search_analytics.assert_awaited_once()
    call = client.query_search_analytics.await_args.kwargs
    assert call["dimensions"] == ["page"]
    assert call["dimension_filter_groups"][0]["filters"][0]["expression"] == "https://example.com/page"


def test_gsc_page_metrics_range_marks_recent_change_unavailable(gsc_env):
    from agent.gsc import GscAPIClient

    client = GscAPIClient(gsc_env)
    client.get_page_metrics = AsyncMock()

    import asyncio

    result = asyncio.run(client.get_page_metrics_range("https://example.com/page", "2999-01-01"))

    assert result["data_available"] is False
    client.get_page_metrics.assert_not_awaited()


def test_gsc_endpoint_returns_metrics(client, monkeypatch):
    from agent.api.routers import gsc

    fake = MagicMock()
    fake.get_page_metrics_range = AsyncMock(return_value={"url": "https://example.com", "data_available": True})
    fake.close = AsyncMock()
    monkeypatch.setattr(gsc, "_gsc_client", lambda: fake)

    response = client.get(
        "/gsc/page-metrics",
        params={"url": "https://example.com", "change_date": "2026-02-01"},
    )

    assert response.status_code == 200
    assert response.json()["data_available"] is True
    fake.get_page_metrics_range.assert_awaited_once_with("https://example.com", "2026-02-01", 28)


def test_gsc_endpoint_returns_503_when_unconfigured(client, monkeypatch):
    from agent.api.routers import gsc

    monkeypatch.setattr(gsc.GscConfig, "from_env", classmethod(lambda cls: None))
    response = client.get(
        "/gsc/page-metrics",
        params={"url": "https://example.com", "change_date": "2026-02-01"},
    )

    assert response.status_code == 503
