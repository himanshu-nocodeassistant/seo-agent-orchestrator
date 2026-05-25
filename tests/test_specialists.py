"""
Unit tests for specialist agents.

Tests tool whitelists, MCP server presence, prompt construction,
and AgentResult return contract — all without hitting the SDK.
"""

import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from agent.config import AgentConfig
from agent.specialists.base import AgentContext, AgentResult
from agent.specialists.research_agent import ResearchAgent
from agent.specialists.content_agent import ContentAgent
from agent.specialists.analytics_agent import AnalyticsAgent
from agent.specialists.technical_seo_agent import TechnicalSEOAgent


def _config() -> AgentConfig:
    """Minimal AgentConfig for tests."""
    return AgentConfig()


def _ctx(**kwargs) -> AgentContext:
    """Create a minimal AgentContext with sensible defaults."""
    defaults = dict(
        task_id=1,
        task_title="Test Task",
        task_description="A test description",
        execution_type="research",
        pipeline_step=0,
        pipeline_total=1,
        prior_outputs=[],
        user_notes=[],
        site_url="https://example.com",
        site_name="ExampleSite",
    )
    defaults.update(kwargs)
    return AgentContext(**defaults)


# ============================================================================
# ResearchAgent
# ============================================================================

class TestResearchAgent:
    def test_uses_only_websearch_webfetch(self):
        agent = ResearchAgent(_config())
        opts = agent._build_options()
        assert opts.allowed_tools == ["WebSearch", "WebFetch"]

    def test_has_no_mcp_servers(self):
        agent = ResearchAgent(_config())
        opts = agent._build_options()
        assert opts.mcp_servers == {}

    def test_has_no_setting_sources(self):
        agent = ResearchAgent(_config())
        opts = agent._build_options()
        assert opts.setting_sources == []

    def test_name_is_research_agent(self):
        assert ResearchAgent.name == "ResearchAgent"

    def test_prompt_includes_task_title(self):
        agent = ResearchAgent(_config())
        ctx = _ctx(task_title="Keyword Research for Bubble Agency")
        prompt = agent._build_prompt(ctx)
        assert "Keyword Research for Bubble Agency" in prompt

    def test_prompt_includes_site_url(self):
        agent = ResearchAgent(_config())
        ctx = _ctx(site_url="https://acme.example.com")
        prompt = agent._build_prompt(ctx)
        assert "acme.example.com" in prompt

    def test_prompt_includes_pipeline_stage(self):
        agent = ResearchAgent(_config())
        ctx = _ctx(pipeline_step=0, pipeline_total=2)
        prompt = agent._build_prompt(ctx)
        assert "1 of 2" in prompt

    def test_prompt_includes_user_notes(self):
        agent = ResearchAgent(_config())
        ctx = _ctx(user_notes=["Focus on mobile intent"])
        prompt = agent._build_prompt(ctx)
        assert "Focus on mobile intent" in prompt

    def test_prompt_has_research_output_block(self):
        agent = ResearchAgent(_config())
        ctx = _ctx()
        prompt = agent._build_prompt(ctx)
        assert "RESEARCH_OUTPUT" in prompt

    @pytest.mark.asyncio
    async def test_run_returns_agent_result(self):
        agent = ResearchAgent(_config())
        ctx = _ctx()

        async def _fake_query(*args, **kwargs):
            from claude_agent_sdk.types import ResultMessage
            msg = MagicMock(spec=ResultMessage)
            msg.result = "Research complete"
            yield msg

        with patch("agent.specialists.base.query", side_effect=_fake_query):
            result = await agent.run(ctx)

        assert isinstance(result, AgentResult)
        assert result.agent_name == "ResearchAgent"
        assert "Research complete" in result.output


# ============================================================================
# ContentAgent
# ============================================================================

class TestContentAgent:
    def test_allows_skill_tool(self):
        agent = ContentAgent(_config())
        opts = agent._build_options()
        assert "Skill" in opts.allowed_tools

    def test_allows_read_write_edit(self):
        agent = ContentAgent(_config())
        opts = agent._build_options()
        for tool in ("Read", "Write", "Edit"):
            assert tool in opts.allowed_tools

    def test_without_google_docs_has_no_mcp(self):
        config = _config()
        assert config.google_docs_config is None
        agent = ContentAgent(config)
        opts = agent._build_options()
        assert opts.mcp_servers == {}

    def test_without_google_docs_no_gdocs_tools(self):
        agent = ContentAgent(_config())
        opts = agent._build_options()
        assert not any("google_docs" in t for t in opts.allowed_tools)

    def test_has_setting_sources_for_skill(self):
        agent = ContentAgent(_config())
        opts = agent._build_options()
        assert "user" in opts.setting_sources or "project" in opts.setting_sources

    def test_name_is_content_agent(self):
        assert ContentAgent.name == "ContentAgent"

    def test_prompt_includes_task_title(self):
        agent = ContentAgent(_config())
        ctx = _ctx(task_title="Write Blog Post", execution_type="blog_write")
        prompt = agent._build_prompt(ctx)
        assert "Write Blog Post" in prompt

    def test_prompt_includes_prior_research(self):
        agent = ContentAgent(_config())
        prior = [{"agent": "ResearchAgent", "output": "Primary keyword: bubble agency", "structured": {}}]
        ctx = _ctx(execution_type="blog_write", prior_outputs=prior)
        prompt = agent._build_prompt(ctx)
        assert "bubble agency" in prompt

    def test_prompt_blog_write_includes_copywriting_step(self):
        agent = ContentAgent(_config())
        ctx = _ctx(execution_type="blog_write")
        prompt = agent._build_prompt(ctx)
        assert "copywriting" in prompt.lower()

    def test_prompt_rewrite_title_includes_options_step(self):
        agent = ContentAgent(_config())
        ctx = _ctx(execution_type="rewrite_title")
        prompt = agent._build_prompt(ctx)
        assert "options" in prompt.lower() or "brand voice" in prompt.lower()

    def test_prompt_includes_user_notes(self):
        agent = ContentAgent(_config())
        ctx = _ctx(execution_type="blog_write", user_notes=["Use casual tone"])
        prompt = agent._build_prompt(ctx)
        assert "Use casual tone" in prompt

    @pytest.mark.asyncio
    async def test_run_returns_agent_result(self):
        agent = ContentAgent(_config())
        ctx = _ctx(execution_type="blog_write")

        async def _fake_query(*args, **kwargs):
            from claude_agent_sdk.types import ResultMessage
            msg = MagicMock(spec=ResultMessage)
            msg.result = "Blog post written"
            yield msg

        with patch("agent.specialists.base.query", side_effect=_fake_query):
            result = await agent.run(ctx)

        assert isinstance(result, AgentResult)
        assert result.agent_name == "ContentAgent"


# ============================================================================
# AnalyticsAgent
# ============================================================================

class TestAnalyticsAgent:
    def test_is_read_only_no_write_or_edit(self):
        agent = AnalyticsAgent(_config())
        opts = agent._build_options()
        assert "Write" not in opts.allowed_tools
        assert "Edit" not in opts.allowed_tools

    def test_allows_read_webfetch_bash(self):
        agent = AnalyticsAgent(_config())
        opts = agent._build_options()
        assert "Read" in opts.allowed_tools
        assert "WebFetch" in opts.allowed_tools
        assert "Bash" in opts.allowed_tools

    def test_has_no_mcp_servers(self):
        agent = AnalyticsAgent(_config())
        opts = agent._build_options()
        assert opts.mcp_servers == {}

    def test_has_no_setting_sources(self):
        agent = AnalyticsAgent(_config())
        opts = agent._build_options()
        assert opts.setting_sources == []

    def test_name_is_analytics_agent(self):
        assert AnalyticsAgent.name == "AnalyticsAgent"

    def test_prompt_includes_phase_instructions(self):
        agent = AnalyticsAgent(_config())
        ctx = _ctx(execution_type="seo_impact_review")
        prompt = agent._build_prompt(ctx)
        assert "PHASE 1" in prompt
        assert "PHASE 2" in prompt
        assert "PHASE 3" in prompt

    def test_prompt_includes_site_url(self):
        agent = AnalyticsAgent(_config())
        ctx = _ctx(site_url="https://feedback.example.com")
        prompt = agent._build_prompt(ctx)
        assert "feedback.example.com" in prompt

    @pytest.mark.asyncio
    async def test_run_returns_agent_result(self):
        agent = AnalyticsAgent(_config())
        ctx = _ctx(execution_type="seo_impact_review")

        async def _fake_query(*args, **kwargs):
            from claude_agent_sdk.types import ResultMessage
            msg = MagicMock(spec=ResultMessage)
            msg.result = "Review complete"
            yield msg

        with patch("agent.specialists.base.query", side_effect=_fake_query):
            result = await agent.run(ctx)

        assert isinstance(result, AgentResult)
        assert result.agent_name == "AnalyticsAgent"
        assert "Review complete" in result.output


# ============================================================================
# TechnicalSEOAgent
# ============================================================================

class TestTechnicalSEOAgent:
    def test_uses_skill_tool(self):
        agent = TechnicalSEOAgent(_config())
        opts = agent._build_options()
        assert "Skill" in opts.allowed_tools

    def test_uses_webfetch(self):
        agent = TechnicalSEOAgent(_config())
        opts = agent._build_options()
        assert "WebFetch" in opts.allowed_tools

    def test_has_no_mcp_servers(self):
        agent = TechnicalSEOAgent(_config())
        opts = agent._build_options()
        assert opts.mcp_servers == {}

    def test_has_setting_sources_for_skill(self):
        agent = TechnicalSEOAgent(_config())
        opts = agent._build_options()
        assert "user" in opts.setting_sources or "project" in opts.setting_sources

    def test_name_is_technical_seo_agent(self):
        assert TechnicalSEOAgent.name == "TechnicalSEOAgent"

    def test_prompt_update_schema_includes_json_ld(self):
        agent = TechnicalSEOAgent(_config())
        ctx = _ctx(execution_type="update_schema")
        prompt = agent._build_prompt(ctx)
        assert "JSON-LD" in prompt

    def test_prompt_update_schema_invokes_skill(self):
        agent = TechnicalSEOAgent(_config())
        ctx = _ctx(execution_type="update_schema")
        prompt = agent._build_prompt(ctx)
        assert "schema-markup" in prompt.lower() or "Skill" in prompt

    def test_prompt_alt_text_has_categorization(self):
        agent = TechnicalSEOAgent(_config())
        ctx = _ctx(execution_type="alt_text")
        prompt = agent._build_prompt(ctx)
        assert "logos" in prompt.lower() or "alt text" in prompt.lower()

    def test_prompt_internal_links_has_link_plan(self):
        agent = TechnicalSEOAgent(_config())
        ctx = _ctx(execution_type="internal_links")
        prompt = agent._build_prompt(ctx)
        assert "link plan" in prompt.lower() or "internal link" in prompt.lower()

    def test_prompt_includes_prior_research(self):
        agent = TechnicalSEOAgent(_config())
        prior = [{"agent": "ResearchAgent", "output": "Top keyword: schema markup service", "structured": {}}]
        ctx = _ctx(execution_type="update_schema", prior_outputs=prior)
        prompt = agent._build_prompt(ctx)
        assert "schema markup service" in prompt

    @pytest.mark.asyncio
    async def test_run_returns_agent_result(self):
        agent = TechnicalSEOAgent(_config())
        ctx = _ctx(execution_type="update_schema")

        async def _fake_query(*args, **kwargs):
            from claude_agent_sdk.types import ResultMessage
            msg = MagicMock(spec=ResultMessage)
            msg.result = "Schema generated"
            yield msg

        with patch("agent.specialists.base.query", side_effect=_fake_query):
            result = await agent.run(ctx)

        assert isinstance(result, AgentResult)
        assert result.agent_name == "TechnicalSEOAgent"
        assert "Schema generated" in result.output
