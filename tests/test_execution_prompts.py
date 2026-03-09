"""Tests for execution prompt structure and fallback behavior."""

from types import SimpleNamespace

from agent.api.main import build_execution_prompt


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
