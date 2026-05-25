"""
Unit tests for OrchestratorAgent.

Tests pipeline routing, sequential execution, inter-agent handoff,
progress comments, error handling, and legacy fallback — all without
hitting the Claude SDK.
"""

import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

from agent.config import AgentConfig
from agent.orchestrator import OrchestratorAgent, AGENT_PIPELINE, AGENT_REGISTRY
from agent.specialists.base import AgentContext, AgentResult


def _config() -> AgentConfig:
    return AgentConfig()


def _task(execution_type="research", title="Test Task", description="Test Desc"):
    return SimpleNamespace(
        id=42,
        title=title,
        description=description,
        execution_type=execution_type,
    )


def _comment(body="User note", author="user"):
    return SimpleNamespace(author=author, body=body)


# ============================================================================
# Pipeline registry
# ============================================================================

class TestPipelineRegistry:
    def test_research_only_pipeline(self):
        assert AGENT_PIPELINE["research"] == ["ResearchAgent"]

    def test_rewrite_title_pipeline(self):
        assert AGENT_PIPELINE["rewrite_title"] == ["ResearchAgent", "ContentAgent"]

    def test_rewrite_meta_desc_pipeline(self):
        assert AGENT_PIPELINE["rewrite_meta_desc"] == ["ResearchAgent", "ContentAgent"]

    def test_rewrite_h1_pipeline(self):
        assert AGENT_PIPELINE["rewrite_h1"] == ["ResearchAgent", "ContentAgent"]

    def test_blog_write_pipeline(self):
        assert AGENT_PIPELINE["blog_write"] == ["ResearchAgent", "ContentAgent"]

    def test_rewrite_blog_content_pipeline(self):
        assert AGENT_PIPELINE["rewrite_blog_content"] == ["ResearchAgent", "ContentAgent"]

    def test_update_schema_pipeline(self):
        assert AGENT_PIPELINE["update_schema"] == ["TechnicalSEOAgent"]

    def test_alt_text_pipeline(self):
        assert AGENT_PIPELINE["alt_text"] == ["TechnicalSEOAgent"]

    def test_internal_links_pipeline(self):
        assert AGENT_PIPELINE["internal_links"] == ["ResearchAgent", "TechnicalSEOAgent"]

    def test_seo_impact_review_pipeline(self):
        assert AGENT_PIPELINE["seo_impact_review"] == ["AnalyticsAgent"]

    def test_unknown_type_returns_empty_pipeline(self):
        orchestrator = OrchestratorAgent(_config(), lambda _: None)
        assert orchestrator.get_pipeline("nonexistent_type") == []

    def test_get_pipeline_delegates_to_registry(self):
        orchestrator = OrchestratorAgent(_config(), lambda _: None)
        assert orchestrator.get_pipeline("research") == ["ResearchAgent"]

    def test_all_pipeline_agents_in_registry(self):
        """Every agent name referenced in AGENT_PIPELINE must exist in AGENT_REGISTRY."""
        for etype, agents in AGENT_PIPELINE.items():
            for agent_name in agents:
                assert agent_name in AGENT_REGISTRY, \
                    f"Agent '{agent_name}' in pipeline '{etype}' missing from AGENT_REGISTRY"


# ============================================================================
# OrchestratorAgent.run() — single-stage pipeline
# ============================================================================

class TestOrchestratorRun:
    @pytest.mark.asyncio
    async def test_research_only_pipeline_calls_one_agent(self):
        comments: list = []
        posted: list = []

        mock_result = AgentResult(
            agent_name="ResearchAgent",
            output="Research done",
            structured={},
        )

        with patch.object(
            AGENT_REGISTRY["ResearchAgent"], "run", new=AsyncMock(return_value=mock_result)
        ):
            orchestrator = OrchestratorAgent(_config(), lambda b: posted.append(b))
            result = await orchestrator.run(_task("research"), comments)

        assert result == "Research done"

    @pytest.mark.asyncio
    async def test_progress_comments_posted_for_single_stage(self):
        posted: list = []

        mock_result = AgentResult(agent_name="ResearchAgent", output="Done", structured={})

        with patch.object(
            AGENT_REGISTRY["ResearchAgent"], "run", new=AsyncMock(return_value=mock_result)
        ):
            orchestrator = OrchestratorAgent(_config(), lambda b: posted.append(b))
            await orchestrator.run(_task("research"), [])

        assert any("🔄" in c and "ResearchAgent" in c for c in posted), \
            f"No start comment found. Got: {posted}"
        assert any("✅" in c and "ResearchAgent" in c for c in posted), \
            f"No complete comment found. Got: {posted}"

    @pytest.mark.asyncio
    async def test_progress_comments_posted_for_two_stage_pipeline(self):
        posted: list = []

        research_result = AgentResult(agent_name="ResearchAgent", output="Research", structured={})
        content_result = AgentResult(agent_name="ContentAgent", output="Content", structured={})

        with (
            patch.object(AGENT_REGISTRY["ResearchAgent"], "run", new=AsyncMock(return_value=research_result)),
            patch.object(AGENT_REGISTRY["ContentAgent"], "run", new=AsyncMock(return_value=content_result)),
        ):
            orchestrator = OrchestratorAgent(_config(), lambda b: posted.append(b))
            result = await orchestrator.run(_task("blog_write"), [])

        assert result == "Content"  # final stage wins
        # Should have 4 comments: 🔄 Research, ✅ Research, 🔄 Content, ✅ Content
        assert len([c for c in posted if "🔄" in c]) == 2
        assert len([c for c in posted if "✅" in c]) == 2

    @pytest.mark.asyncio
    async def test_sequential_pipeline_passes_prior_outputs(self):
        """Second agent must receive first agent's output in ctx.prior_outputs."""
        content_ctx: list = []

        research_result = AgentResult(agent_name="ResearchAgent", output="ResearchOut", structured={})

        async def capture_content_run(ctx: AgentContext):
            content_ctx.append(ctx)
            return AgentResult(agent_name="ContentAgent", output="ContentOut", structured={})

        with (
            patch.object(AGENT_REGISTRY["ResearchAgent"], "run", new=AsyncMock(return_value=research_result)),
            patch.object(AGENT_REGISTRY["ContentAgent"], "run", side_effect=capture_content_run),
        ):
            orchestrator = OrchestratorAgent(_config(), lambda _: None)
            await orchestrator.run(_task("blog_write"), [])

        # ContentAgent should have been called exactly once
        assert len(content_ctx) == 1
        prior = content_ctx[0].prior_outputs
        assert len(prior) == 1
        assert prior[0]["agent"] == "ResearchAgent"
        assert prior[0]["output"] == "ResearchOut"

    @pytest.mark.asyncio
    async def test_user_notes_passed_to_context(self):
        """User comments (author=user) are extracted into ctx.user_notes."""
        captured: list = []

        async def capture_run(ctx: AgentContext):
            captured.append(ctx)
            return AgentResult(agent_name="ResearchAgent", output="ok", structured={})

        comments = [_comment("Focus on enterprise", author="user"),
                    _comment("Agent output ignored", author="agent")]

        with patch.object(AGENT_REGISTRY["ResearchAgent"], "run", side_effect=capture_run):
            orchestrator = OrchestratorAgent(_config(), lambda _: None)
            await orchestrator.run(_task("research"), comments)

        assert captured[0].user_notes == ["Focus on enterprise"]

    @pytest.mark.asyncio
    async def test_site_url_and_name_passed_to_context(self, monkeypatch):
        """site_url and site_name from config propagate to AgentContext."""
        captured: list = []

        async def capture_run(ctx: AgentContext):
            captured.append(ctx)
            return AgentResult(agent_name="ResearchAgent", output="ok", structured={})

        monkeypatch.setenv("TARGET_SITE_URL", "https://portfolio.example.com")
        monkeypatch.setenv("TARGET_SITE_NAME", "PortfolioSite")
        config = AgentConfig.from_env()

        with patch.object(AGENT_REGISTRY["ResearchAgent"], "run", side_effect=capture_run):
            orchestrator = OrchestratorAgent(config, lambda _: None)
            await orchestrator.run(_task("research"), [])

        assert captured[0].site_url == "https://portfolio.example.com"
        assert captured[0].site_name == "PortfolioSite"

    @pytest.mark.asyncio
    async def test_agent_failure_posts_error_comment(self):
        """When a specialist raises, orchestrator posts ❌ comment and re-raises."""
        posted: list = []

        with patch.object(
            AGENT_REGISTRY["ResearchAgent"],
            "run",
            new=AsyncMock(side_effect=RuntimeError("SDK timeout")),
        ):
            orchestrator = OrchestratorAgent(_config(), lambda b: posted.append(b))
            with pytest.raises(RuntimeError, match="SDK timeout"):
                await orchestrator.run(_task("research"), [])

        assert any("❌" in c for c in posted), f"No error comment posted. Got: {posted}"

    @pytest.mark.asyncio
    async def test_unknown_type_falls_back_to_legacy(self):
        """Unknown execution_type → _run_legacy_fallback → SEOAgent.create_and_run."""
        legacy_mock = AsyncMock(return_value="legacy output")

        # SEOAgent is imported locally inside _run_legacy_fallback; patch at module source
        with patch("agent.seo_agent.SEOAgent.create_and_run", new=legacy_mock):
            orchestrator = OrchestratorAgent(_config(), lambda _: None)
            result = await orchestrator.run(_task("totally_unknown_type"), [])

        assert legacy_mock.called
        assert result == "legacy output"

    @pytest.mark.asyncio
    async def test_analytics_pipeline_single_stage(self):
        """seo_impact_review uses only AnalyticsAgent."""
        mock_result = AgentResult(agent_name="AnalyticsAgent", output="Review done", structured={})

        with patch.object(AGENT_REGISTRY["AnalyticsAgent"], "run", new=AsyncMock(return_value=mock_result)):
            orchestrator = OrchestratorAgent(_config(), lambda _: None)
            result = await orchestrator.run(_task("seo_impact_review"), [])

        assert result == "Review done"

    @pytest.mark.asyncio
    async def test_internal_links_pipeline_order(self):
        """internal_links → ResearchAgent then TechnicalSEOAgent."""
        order: list = []

        async def research_run(ctx):
            order.append("Research")
            return AgentResult(agent_name="ResearchAgent", output="Links research", structured={})

        async def tech_run(ctx):
            order.append("Technical")
            return AgentResult(agent_name="TechnicalSEOAgent", output="Link plan", structured={})

        with (
            patch.object(AGENT_REGISTRY["ResearchAgent"], "run", side_effect=research_run),
            patch.object(AGENT_REGISTRY["TechnicalSEOAgent"], "run", side_effect=tech_run),
        ):
            orchestrator = OrchestratorAgent(_config(), lambda _: None)
            result = await orchestrator.run(_task("internal_links"), [])

        assert order == ["Research", "Technical"]
        assert result == "Link plan"
