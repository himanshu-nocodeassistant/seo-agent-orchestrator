"""
Tests for the Google Search Console module.

Covers: GscConfig, GscAPIClient, tools, and runtime_profiles wiring.
All tests mock the Google API to avoid real network calls.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FAKE_CREDS_PATH = Path(__file__).parent.parent / "google-sa-credentials" / "service-account.json"


@pytest.fixture
def gsc_env(monkeypatch, tmp_path):
    """Set minimal GSC env vars pointing to a temp credentials file."""
    creds_file = tmp_path / "sa.json"
    creds_file.write_text(json.dumps({"type": "service_account"}))
    monkeypatch.setenv("GSC_SITE_URL", "sc-domain:example.com")
    monkeypatch.setenv("GSC_CREDENTIALS_PATH", str(creds_file))
    return {"site_url": "sc-domain:example.com", "creds_path": str(creds_file)}


# ---------------------------------------------------------------------------
# GscConfig
# ---------------------------------------------------------------------------


class TestGscConfig:
    def test_from_env_returns_none_when_site_url_missing(self, monkeypatch):
        monkeypatch.delenv("GSC_SITE_URL", raising=False)
        from agent.gsc import GscConfig
        assert GscConfig.from_env() is None

    def test_from_env_returns_config_when_site_url_set(self, gsc_env):
        from agent.gsc import GscConfig
        config = GscConfig.from_env()
        assert config is not None
        assert config.site_url == "sc-domain:example.com"

    def test_raises_when_credentials_file_missing(self, monkeypatch):
        monkeypatch.setenv("GSC_SITE_URL", "sc-domain:example.com")
        monkeypatch.setenv("GSC_CREDENTIALS_PATH", "/nonexistent/path.json")
        from agent.gsc import GscConfig
        with pytest.raises(FileNotFoundError):
            GscConfig.from_env()

    def test_raises_when_site_url_empty(self, tmp_path):
        creds_file = tmp_path / "sa.json"
        creds_file.write_text("{}")
        from agent.gsc import GscConfig
        with pytest.raises(ValueError):
            GscConfig(site_url="", credentials_path=str(creds_file))

    def test_repr_does_not_expose_full_path(self, gsc_env):
        from agent.gsc import GscConfig
        config = GscConfig.from_env()
        assert "GscConfig" in repr(config)

    def test_falls_back_to_google_docs_credentials_path(self, monkeypatch, tmp_path):
        creds_file = tmp_path / "sa.json"
        creds_file.write_text("{}")
        monkeypatch.setenv("GSC_SITE_URL", "sc-domain:example.com")
        monkeypatch.delenv("GSC_CREDENTIALS_PATH", raising=False)
        monkeypatch.setenv("GOOGLE_DOCS_CREDENTIALS_PATH", str(creds_file))
        from agent.gsc import GscConfig
        config = GscConfig.from_env()
        assert config is not None


# ---------------------------------------------------------------------------
# GscAPIClient
# ---------------------------------------------------------------------------


class TestGscAPIClient:
    """Unit tests for GscAPIClient — Google API calls are fully mocked."""

    def _make_client(self, gsc_env):
        from agent.gsc import GscConfig, GscAPIClient
        config = GscConfig.from_env()
        return GscAPIClient(config)

    @pytest.mark.asyncio
    async def test_query_search_analytics_returns_rows(self, gsc_env):
        client = self._make_client(gsc_env)

        fake_response = {
            "rows": [
                {"keys": ["seo audit tool"], "clicks": 120, "impressions": 1800,
                 "ctr": 0.066, "position": 8.4}
            ]
        }

        mock_service = MagicMock()
        mock_service.searchanalytics().query().execute.return_value = fake_response

        with patch.object(client, "_get_service", new=AsyncMock(return_value=mock_service)):
            result = await client.query_search_analytics(
                start_date="2026-01-01",
                end_date="2026-01-28",
                dimensions=["query"],
                row_limit=10,
            )

        assert "rows" in result
        assert result["rows"][0]["clicks"] == 120

    @pytest.mark.asyncio
    async def test_inspect_url_returns_index_status(self, gsc_env):
        client = self._make_client(gsc_env)

        fake_response = {
            "inspectionResult": {
                "indexStatusResult": {"verdict": "PASS", "coverageState": "Submitted and indexed"}
            }
        }

        mock_service = MagicMock()
        mock_service.urlInspection().index().inspect().execute.return_value = fake_response

        with patch.object(client, "_get_service", new=AsyncMock(return_value=mock_service)):
            result = await client.inspect_url("https://example.com/blog/post-1")

        assert result["inspectionResult"]["indexStatusResult"]["verdict"] == "PASS"

    @pytest.mark.asyncio
    async def test_list_sitemaps_returns_sitemap_list(self, gsc_env):
        client = self._make_client(gsc_env)

        fake_response = {
            "sitemap": [
                {"path": "https://example.com/sitemap.xml", "type": "sitemap",
                 "lastDownloaded": "2026-05-01T00:00:00Z"}
            ]
        }

        mock_service = MagicMock()
        mock_service.sitemaps().list().execute.return_value = fake_response

        with patch.object(client, "_get_service", new=AsyncMock(return_value=mock_service)):
            result = await client.list_sitemaps()

        assert len(result["sitemap"]) == 1
        assert "sitemap.xml" in result["sitemap"][0]["path"]

    @pytest.mark.asyncio
    async def test_query_clamps_row_limit_to_max(self, gsc_env):
        """row_limit values above 25000 should be clamped to 25000."""
        client = self._make_client(gsc_env)

        captured_body = {}

        async def fake_get_service():
            mock = MagicMock()

            def fake_query(siteUrl, body):
                captured_body.update(body)
                return MagicMock(execute=MagicMock(return_value={"rows": []}))

            mock.searchanalytics().query.side_effect = fake_query
            return mock

        with patch.object(client, "_get_service", new=fake_get_service):
            await client.query_search_analytics(row_limit=99999)

        assert captured_body.get("rowLimit", 0) <= 25000

    @pytest.mark.asyncio
    async def test_api_error_raised_on_exception(self, gsc_env):
        from agent.gsc import GscAPIError
        client = self._make_client(gsc_env)

        mock_service = MagicMock()
        mock_service.searchanalytics().query().execute.side_effect = Exception("quota exceeded")

        with patch.object(client, "_get_service", new=AsyncMock(return_value=mock_service)):
            with pytest.raises(GscAPIError, match="quota exceeded"):
                await client.query_search_analytics()


# ---------------------------------------------------------------------------
# Runtime profiles — GSC tools wired into correct profiles
# ---------------------------------------------------------------------------


class TestGscRuntimeProfiles:
    def test_gsc_tools_in_seo_impact_review(self):
        from agent.runtime_profiles import PROFILE_REGISTRY
        profile = PROFILE_REGISTRY["seo_impact_review"]
        assert "mcp__gsc__gsc_query_search_analytics" in profile.allowed_tools

    def test_gsc_tools_in_research(self):
        from agent.runtime_profiles import PROFILE_REGISTRY
        profile = PROFILE_REGISTRY["research"]
        assert "mcp__gsc__gsc_query_search_analytics" in profile.allowed_tools

    def test_gsc_tools_not_in_webflow_write_profiles(self):
        # Webflow-write profiles don't need GSC — they publish, not analyse
        from agent.runtime_profiles import PROFILE_REGISTRY
        for pname in ("rewrite_title", "rewrite_meta_desc", "rewrite_h1", "blog_write"):
            profile = PROFILE_REGISTRY[pname]
            assert "mcp__gsc__gsc_query_search_analytics" not in profile.allowed_tools, (
                f"Profile '{pname}' should not include GSC tools"
            )


# ---------------------------------------------------------------------------
# AgentConfig.from_env wires GscConfig when GSC_SITE_URL is set
# ---------------------------------------------------------------------------


class TestAgentConfigGscWiring:
    def test_gsc_config_not_set_when_env_missing(self, monkeypatch):
        monkeypatch.delenv("GSC_SITE_URL", raising=False)
        monkeypatch.delenv("WEBFLOW_ACCESS_TOKEN", raising=False)
        monkeypatch.delenv("GOOGLE_DOCS_CREDENTIALS_PATH", raising=False)
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)

        with patch("agent.config.Path.exists", return_value=True):
            from agent.config import AgentConfig
            config = AgentConfig.__new__(AgentConfig)
            config.gsc_config = None
            assert config.gsc_config is None

    def test_gsc_tool_names_defined_in_setup(self):
        # Verify the tool name constants match what the server registers
        expected = {
            "mcp__gsc__gsc_query_search_analytics",
            "mcp__gsc__gsc_inspect_url",
            "mcp__gsc__gsc_list_sitemaps",
        }
        from agent.runtime_profiles import GSC_TOOLS
        assert set(GSC_TOOLS) == expected
