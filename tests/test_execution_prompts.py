"""Tests for execution prompt structure and fallback behavior."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from agent.api.main import build_execution_prompt


def _task(execution_type="rewrite_title"):
    return SimpleNamespace(
        title="Test task",
        description="Task details",
        execution_type=execution_type,
        notes=None,
    )


def _comment(body="Keep it concise", author="user"):
    return SimpleNamespace(author=author, body=body)


def _mock_config(site_name="TestSite", site_url="https://testsite.example.com"):
    """Return a minimal AgentConfig-like namespace for prompt substitution tests."""
    return SimpleNamespace(site_name=site_name, site_url=site_url)


class TestUserCommentsInPrompt:
    def test_user_comments_appended_to_prompt(self):
        comments = [_comment("Keep it concise")]
        prompt = build_execution_prompt(_task(), comments=comments)
        assert "User Notes" in prompt
        assert "Keep it concise" in prompt

    def test_multiple_user_comments_all_included(self):
        comments = [_comment("Keep it concise"), _comment("Focus on mobile users")]
        prompt = build_execution_prompt(_task(), comments=comments)
        assert "Keep it concise" in prompt
        assert "Focus on mobile users" in prompt

    def test_agent_comments_excluded_from_user_notes(self):
        comments = [_comment("agent output", author="agent"), _comment("user note", author="user")]
        prompt = build_execution_prompt(_task(), comments=comments)
        assert "user note" in prompt
        assert "agent output" not in prompt

    def test_no_comments_does_not_add_user_notes_section(self):
        prompt = build_execution_prompt(_task(), comments=[])
        assert "User Notes" not in prompt

    def test_none_comments_does_not_add_user_notes_section(self):
        prompt = build_execution_prompt(_task(), comments=None)
        assert "User Notes" not in prompt


class TestPromptSiteNameSubstitution:
    """Test that site_name and site_url are substituted from config param."""

    def test_build_execution_prompt_accepts_config_param(self):
        """Config param controls site_name substitution in all prompt branches."""
        config = _mock_config(site_name="AcmeCorp", site_url="https://acme.example.com")
        prompt = build_execution_prompt(_task("blog_write"), config=config)
        assert "AcmeCorp" in prompt

    def test_rewrite_title_uses_site_name(self):
        config = _mock_config(site_name="PortfolioSite")
        prompt = build_execution_prompt(_task("rewrite_title"), config=config)
        assert "PortfolioSite" in prompt

    def test_blog_write_uses_site_url(self):
        config = _mock_config(site_url="https://demo.example.com")
        prompt = build_execution_prompt(_task("blog_write"), config=config)
        assert "demo.example.com" in prompt

    def test_research_uses_site_url(self):
        config = _mock_config(site_url="https://mysite.example.com")
        prompt = build_execution_prompt(_task("research"), config=config)
        assert "mysite.example.com" in prompt

    def test_rewrite_meta_desc_has_no_webflow_steps(self):
        config = _mock_config()
        prompt = build_execution_prompt(_task("rewrite_meta_desc"), config=config)
        # Webflow-specific instructions must not appear
        assert "mcp__webflow__" not in prompt
        assert "Webflow Designer" not in prompt

    def test_rewrite_h1_has_no_webflow_steps(self):
        config = _mock_config()
        prompt = build_execution_prompt(_task("rewrite_h1"), config=config)
        assert "mcp__webflow__" not in prompt

    def test_blog_write_has_no_webflow_steps(self):
        config = _mock_config()
        prompt = build_execution_prompt(_task("blog_write"), config=config)
        assert "mcp__webflow__" not in prompt

    def test_update_schema_has_no_webflow_steps(self):
        config = _mock_config()
        prompt = build_execution_prompt(_task("update_schema"), config=config)
        assert "mcp__webflow__" not in prompt

    def test_alt_text_has_no_webflow_steps(self):
        config = _mock_config()
        prompt = build_execution_prompt(_task("alt_text"), config=config)
        assert "mcp__webflow__" not in prompt

    def test_internal_links_has_no_webflow_steps(self):
        config = _mock_config()
        prompt = build_execution_prompt(_task("internal_links"), config=config)
        assert "mcp__webflow__" not in prompt


class TestPromptStructure:
    """Test that key workflow sections are present in prompts."""

    def test_rewrite_title_has_keyword_research_step(self):
        prompt = build_execution_prompt(_task("rewrite_title"))
        assert "Keyword research" in prompt

    def test_rewrite_title_has_finalize_step(self):
        prompt = build_execution_prompt(_task("rewrite_title"))
        assert "Finalize draft" in prompt

    def test_rewrite_h1_has_fetch_step(self):
        prompt = build_execution_prompt(_task("rewrite_h1"))
        assert "Fetch the current page" in prompt

    def test_blog_write_has_outline_step(self):
        prompt = build_execution_prompt(_task("blog_write"))
        assert "Outline" in prompt

    def test_research_type_has_synthesize_step(self):
        prompt = build_execution_prompt(_task("research"))
        assert "Synthesize findings" in prompt

    def test_alt_text_has_categorization(self):
        prompt = build_execution_prompt(_task("alt_text"))
        assert "logos" in prompt.lower() or "alt text" in prompt.lower()

    def test_update_schema_has_json_ld_mention(self):
        prompt = build_execution_prompt(_task("update_schema"))
        assert "JSON-LD" in prompt

    def test_unknown_type_returns_task_title(self):
        task = _task("unknown_type")
        task.title = "My custom task"
        prompt = build_execution_prompt(task)
        assert "My custom task" in prompt
