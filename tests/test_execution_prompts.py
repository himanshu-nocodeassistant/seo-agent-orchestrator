"""Tests for execution prompt structure and fallback behavior."""

from types import SimpleNamespace

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

    def test_execute_endpoint_includes_comments_in_prompt(self, client, monkeypatch):
        """Integration: execute_task passes comments to build_execution_prompt."""
        from unittest.mock import AsyncMock, patch, call
        task = client.post("/tasks", json={"title": "Blog post", "execution_type": "blog_write"}).json()
        client.post(f"/tasks/{task['id']}/comments", json={"author": "user", "body": "Use casual tone"})

        config_patch = patch(
            "agent.config.AgentConfig.from_env",
            return_value=SimpleNamespace(cwd="", setting_sources=[], system_prompt=""),
        )
        run_mock = AsyncMock(return_value="done")
        run_patch = patch("agent.seo_agent.SEOAgent.create_and_run", new=run_mock)
        with config_patch, run_patch:
            client.post(f"/tasks/{task['id']}/execute")

        assert run_mock.called, "Agent was not called"
        prompt_used = run_mock.call_args.args[0]
        assert "Use casual tone" in prompt_used


class TestWebflowPromptFallbackOrder:
    def _task(self, execution_type: str):
        return SimpleNamespace(
            title="Test task",
            description="Task details",
            execution_type=execution_type,
            notes=None,
        )

    def test_rewrite_h1_prompt_prioritizes_draft_before_webflow(self, monkeypatch):
        monkeypatch.delenv("WEBFLOW_ACCESS_TOKEN", raising=False)
        prompt = build_execution_prompt(self._task("rewrite_h1"))

        assert "Step 4 — Finalize draft for manual use" in prompt
        assert "Step 5 — Optional Webflow update" in prompt
        assert prompt.index("Step 4 — Finalize draft for manual use") < prompt.index("Step 5 — Optional Webflow update")

    def test_rewrite_title_prompt_prioritizes_draft_before_webflow(self, monkeypatch):
        monkeypatch.delenv("WEBFLOW_ACCESS_TOKEN", raising=False)
        prompt = build_execution_prompt(self._task("rewrite_title"))

        assert "Step 3 — Finalize draft for manual use" in prompt
        assert "Step 4 — Optional Webflow update" in prompt

    def test_blog_write_prompt_has_manual_publishable_output(self, monkeypatch):
        monkeypatch.delenv("WEBFLOW_ACCESS_TOKEN", raising=False)
        prompt = build_execution_prompt(self._task("blog_write"))

        assert "Step 4 — Finalize draft for manual publishing" in prompt
        assert "Step 5 — Optional Webflow create" in prompt
