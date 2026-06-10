"""
Safety hardening tests — red/green TDD.

Each class maps to one gap fix from plans/agent-safety-hardening.md.
Run with:
    python -m pytest tests/test_safety_hardening.py -v
"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ============================================================================
# Fix 1 — G3.1: get_execution_profile raises on unknown type
# ============================================================================

class TestGetExecutionProfile:
    def test_known_type_returns_profile(self):
        from agent.runtime_profiles import get_execution_profile
        profile = get_execution_profile("research")
        assert profile.execution_type == "research"

    def test_none_returns_manual(self):
        from agent.runtime_profiles import get_execution_profile
        profile = get_execution_profile(None)
        assert profile.execution_type == "manual"

    def test_empty_string_returns_manual(self):
        from agent.runtime_profiles import get_execution_profile
        profile = get_execution_profile("")
        assert profile.execution_type == "manual"

    def test_unknown_string_raises_value_error(self):
        from agent.runtime_profiles import get_execution_profile
        with pytest.raises(ValueError, match="hallucinated_type"):
            get_execution_profile("hallucinated_type")

    def test_error_message_lists_valid_types(self):
        from agent.runtime_profiles import get_execution_profile, PROFILE_REGISTRY
        with pytest.raises(ValueError) as exc_info:
            get_execution_profile("not_a_real_type")
        assert "research" in str(exc_info.value)
        assert "manual" in str(exc_info.value)


# ============================================================================
# Fix 2 — G3.3: Bash absent from default AgentConfig allowed_tools
# ============================================================================

class TestAgentConfigDefaults:
    def test_bash_not_in_default_allowed_tools(self):
        from agent.config import AgentConfig
        config = AgentConfig()
        assert "Bash" not in config.allowed_tools

    def test_core_read_tools_still_present(self):
        from agent.config import AgentConfig
        config = AgentConfig()
        for tool in ["Read", "Write", "Edit", "Glob", "Grep"]:
            assert tool in config.allowed_tools, f"{tool} missing from defaults"

    def test_web_tools_still_present(self):
        from agent.config import AgentConfig
        config = AgentConfig()
        assert "WebSearch" in config.allowed_tools
        assert "WebFetch" in config.allowed_tools


# ============================================================================
# Fix 3 — G1.2: _run_with_retry respects max_total_seconds wall-clock cap
# ============================================================================

class TestRunWithRetryWallClock:
    @pytest.mark.asyncio
    async def test_exceeds_wall_clock_raises(self):
        """After the first attempt, if the deadline has passed, do not retry."""
        from agent.orchestrator import _run_with_retry

        call_count = {"n": 0}

        async def slow_transient(*args, **kwargs):
            call_count["n"] += 1
            await asyncio.sleep(0.05)  # each attempt takes 50ms
            raise RuntimeError("Agent execution timed out after 300s")

        with pytest.raises(RuntimeError):
            await _run_with_retry(
                slow_transient,
                max_retries=5,
                base_delay=0.0,
                max_total_seconds=0.06,  # 60ms — fits one attempt (50ms), not three (150ms)
            )

        # Without the cap all 5 attempts would run (250ms total).
        # With the 60ms cap the retry loop must stop before all 5 complete.
        assert call_count["n"] < 5

    @pytest.mark.asyncio
    async def test_none_max_total_seconds_does_not_change_behaviour(self):
        """Omitting max_total_seconds keeps existing retry behaviour intact."""
        from agent.orchestrator import _run_with_retry

        call_count = {"n": 0}

        async def flaky(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] < 3:
                raise RuntimeError("Agent execution timed out after 300s")
            return "ok"

        result = await _run_with_retry(flaky, max_retries=3, base_delay=0.0)
        assert result == "ok"
        assert call_count["n"] == 3


# ============================================================================
# Fix 4 — G1.1: Campaign orchestration has a top-level timeout
# ============================================================================

class TestCampaignTimeout:
    @pytest.mark.asyncio
    async def test_campaign_raises_on_timeout(self):
        """
        If run_campaign_orchestration hangs, the endpoint raises RuntimeError
        with a helpful message rather than blocking forever.
        """
        import agent.api.main as main_module

        async def _hanging_orchestration(*args, **kwargs):
            await asyncio.sleep(9999)

        db = main_module.get_db_session()
        try:
            now = main_module.datetime.utcnow().isoformat()
            parent_task = main_module.TaskModel(
                title="Timeout Campaign",
                description="Should time out",
                execution_type="orchestrate_seo_campaign",
                status="in_progress",
                created_at=now,
                updated_at=now,
            )
            db.add(parent_task)
            db.commit()
            db.refresh(parent_task)
            run = main_module._create_run(
                db, parent_task, "manual_execute", "orchestrate_seo_campaign"
            )

            with patch("agent.orchestrator.run_campaign_orchestration", side_effect=_hanging_orchestration):
                with patch.dict("os.environ", {"CAMPAIGN_TIMEOUT_SECONDS": "1"}):
                    with pytest.raises((RuntimeError, asyncio.TimeoutError)):
                        await main_module._execute_campaign_with_timeout(
                            db, parent_task, run
                        )
        finally:
            db.close()


# ============================================================================
# Fix 5 — G2.4: Validator failure stops downstream phases
# ============================================================================

class TestValidatorFailureStopsPipeline:
    @pytest.mark.asyncio
    async def test_failed_validation_raises_in_dispatch_phase(self):
        """
        When the child profile's validator returns status='failed',
        _dispatch_phase raises RuntimeError so the orchestrator tier fails.
        """
        import agent.api.main as main_module
        from agent.orchestrator import run_campaign_orchestration
        import json

        # Writer output that is missing required fields — will fail _validate_blog_write
        bad_writer_output = (
            "Here is a draft.\n"
            "<!-- CHANGE_LOG\n"
            '{"url": "https://example.com/post", "field": "content"}\n'
            "-->"
        )

        results_iter = iter([
            # Plan
            MagicMock(result_text=(
                "```json\n" + json.dumps({
                    "campaign_goal": "test",
                    "phases": [{
                        "phase": "content_writer",
                        "task_title": "Write post",
                        "task_description": "Write it.",
                        "execution_type": "campaign_draft_writer",
                        "depends_on": [],
                    }]
                }) + "\n```"
            ), session_id="s0"),
            # Writer — bad output
            MagicMock(result_text=bad_writer_output, session_id="s1"),
        ])

        async def _side_effect(*args, **kwargs):
            return next(results_iter)

        db = main_module.get_db_session()
        try:
            now = main_module.datetime.utcnow().isoformat()
            parent_task = main_module.TaskModel(
                title="Validation Fail Campaign",
                description="Writer output should fail validation",
                execution_type="orchestrate_seo_campaign",
                status="in_progress",
                created_at=now,
                updated_at=now,
            )
            db.add(parent_task)
            db.commit()
            db.refresh(parent_task)
            orch_run = main_module._create_run(
                db, parent_task, "manual_execute", "orchestrate_seo_campaign"
            )

            with patch("agent.api.main._run_agent_prompt", side_effect=_side_effect):
                await run_campaign_orchestration(db, parent_task, orch_run)

            db.refresh(orch_run)
            db.refresh(parent_task)

            # Campaign must be stopped — not completed
            assert orch_run.status in ("failed", "blocked")
            assert parent_task.status == "blocked"

            state = db.query(main_module.OrchestrationStateModel).filter(
                main_module.OrchestrationStateModel.orchestrator_run_id == orch_run.run_id
            ).first()
            assert state.status == "error"
        finally:
            db.close()


# ============================================================================
# Fix 6 — G2.1: Research validator requires URL and keyword token
# ============================================================================

class TestResearchValidator:
    def test_output_with_url_and_keyword_passes(self):
        from agent.runtime_profiles import _validate_research_output
        output = (
            "Found top keywords: no-code automation, workflow tools.\n"
            "Source: https://ahrefs.com/keywords?q=no-code\n"
            "Volume estimates from GSC data."
        )
        result = _validate_research_output(output)
        assert result.status == "passed"

    def test_empty_output_fails(self):
        from agent.runtime_profiles import _validate_research_output
        result = _validate_research_output("")
        assert result.status == "failed"

    def test_output_without_url_fails(self):
        from agent.runtime_profiles import _validate_research_output
        result = _validate_research_output(
            "Found many keywords: no-code automation, workflow tools. Great search terms."
        )
        assert result.status == "failed"
        assert "URL" in result.message

    def test_output_without_keyword_token_fails(self):
        from agent.runtime_profiles import _validate_research_output
        result = _validate_research_output(
            "Competitor analysis complete. See https://example.com for details."
        )
        assert result.status == "failed"
        assert "keyword" in result.message.lower()

    def test_research_profile_uses_new_validator(self):
        from agent.runtime_profiles import PROFILE_REGISTRY, _validate_research_output
        profile = PROFILE_REGISTRY["research"]
        assert profile.validator is _validate_research_output

    def test_campaign_researcher_profile_uses_new_validator(self):
        from agent.runtime_profiles import PROFILE_REGISTRY, _validate_research_output
        profile = PROFILE_REGISTRY["campaign_researcher"]
        assert profile.validator is _validate_research_output


# ============================================================================
# Fix 7 — G3.2: Split campaign_content_writer into draft-only + publish-only
# ============================================================================

class TestContentWriterSplit:
    def test_campaign_draft_writer_profile_exists(self):
        from agent.runtime_profiles import PROFILE_REGISTRY
        assert "campaign_draft_writer" in PROFILE_REGISTRY

    def test_campaign_draft_writer_has_no_webflow_tools(self):
        from agent.runtime_profiles import PROFILE_REGISTRY, WEBFLOW_TOOLS
        profile = PROFILE_REGISTRY["campaign_draft_writer"]
        for tool in WEBFLOW_TOOLS:
            assert tool not in profile.allowed_tools, f"draft writer must not have {tool}"

    def test_campaign_draft_writer_has_edit_tools(self):
        from agent.runtime_profiles import PROFILE_REGISTRY
        profile = PROFILE_REGISTRY["campaign_draft_writer"]
        assert "Write" in profile.allowed_tools
        assert "Edit" in profile.allowed_tools

    def test_campaign_publisher_profile_has_no_write_edit(self):
        """Publisher must not be able to modify file content — only publish to CMS."""
        from agent.runtime_profiles import PROFILE_REGISTRY
        profile = PROFILE_REGISTRY["campaign_publisher"]
        assert "Write" not in profile.allowed_tools
        assert "Edit" not in profile.allowed_tools

    def test_campaign_content_writer_is_removed(self):
        """Old monolithic profile must no longer exist to prevent accidental use."""
        from agent.runtime_profiles import PROFILE_REGISTRY
        assert "campaign_content_writer" not in PROFILE_REGISTRY

    def test_campaign_draft_writer_validator_requires_blog_fields(self):
        from agent.runtime_profiles import PROFILE_REGISTRY, _validate_blog_write
        profile = PROFILE_REGISTRY["campaign_draft_writer"]
        # Validator should be blog-write aware (wrapped or direct)
        bad = profile.validator("some draft without required fields")
        assert bad.status == "failed"


# ============================================================================
# Fix 8 — G2.2: Grounding instruction injected for research profiles
# ============================================================================

class TestGroundingInstruction:
    def test_research_profile_has_grounding_tag(self):
        from agent.runtime_profiles import PROFILE_REGISTRY
        profile = PROFILE_REGISTRY["research"]
        assert "grounding-required" in profile.procedural_tags

    def test_campaign_researcher_profile_has_grounding_tag(self):
        from agent.runtime_profiles import PROFILE_REGISTRY
        profile = PROFILE_REGISTRY["campaign_researcher"]
        assert "grounding-required" in profile.procedural_tags

    def test_grounding_instruction_appears_in_prompt(self):
        """When profile has grounding-required tag, to_prompt() must include the cite-sources rule."""
        from agent.memory_service import (
            ComposedPromptContext, EpisodicContext, ProceduralContext,
            SemanticContext, ShortTermContext,
        )
        procedural = ProceduralContext(
            execution_type="research",
            profile_name="research",
            tool_policy=["WebSearch", "WebFetch"],
            validator_name="_validate_research_output",
            max_turns=12,
            timeout_seconds=480,
            procedural_tags=["grounding-required", "research"],
            workflow_prompt="Do keyword research.",
        )
        ctx = ComposedPromptContext(
            short_term=ShortTermContext(
                run_id="r1", task_id=1, execution_type="research",
                trigger_source="test", session_id=None, validator_status=None,
                task_title="Test", task_description=None,
            ),
            episodic=EpisodicContext(task_id=1, execution_type="research"),
            semantic=SemanticContext(
                project_overview="", strategy="", learnings="", context_view=""
            ),
            procedural=procedural,
        )
        prompt = ctx.to_prompt()
        assert "cite" in prompt.lower() or "source" in prompt.lower(), (
            "Grounding instruction missing from prompt for grounding-required profile"
        )

    def test_non_research_profiles_do_not_have_grounding_tag(self):
        from agent.runtime_profiles import PROFILE_REGISTRY
        for name in ["blog_write", "rewrite_title", "campaign_publisher", "manual"]:
            profile = PROFILE_REGISTRY[name]
            assert "grounding-required" not in profile.procedural_tags, (
                f"{name} should not have grounding-required tag"
            )


# ============================================================================
# Fix 9 — G2.3: Human approval gate before campaign_publisher
# ============================================================================

class TestApprovalGate:
    def test_execution_profile_has_requires_approval_field(self):
        from agent.runtime_profiles import ExecutionProfile
        import dataclasses
        fields = {f.name for f in dataclasses.fields(ExecutionProfile)}
        assert "requires_approval" in fields

    def test_campaign_publisher_requires_approval(self):
        from agent.runtime_profiles import PROFILE_REGISTRY
        profile = PROFILE_REGISTRY["campaign_publisher"]
        assert profile.requires_approval is True

    def test_other_profiles_do_not_require_approval(self):
        from agent.runtime_profiles import PROFILE_REGISTRY
        for name in ["campaign_draft_writer", "campaign_researcher", "research", "manual"]:
            profile = PROFILE_REGISTRY[name]
            assert profile.requires_approval is False, (
                f"{name} should not require approval"
            )

    @pytest.mark.asyncio
    async def test_unapproved_publisher_halts_campaign(self):
        """
        When campaign_publisher fires without parent_task.approved_at set,
        the orchestration must stop with status='awaiting_approval', not error.
        """
        import agent.api.main as main_module
        from agent.orchestrator import run_campaign_orchestration
        import json

        draft_output = (
            "Title: Guide to No-Code Automation\n"
            "URL Slug: no-code-automation-guide\n"
            "Word Count: 1200\n"
            "Webflow Status: draft saved\n"
            "<!-- CHANGE_LOG\n"
            '{"url": "https://example.com/no-code-automation-guide", "field": "content"}\n'
            "-->\n"
            "## Summary for Next Phase\nDraft is ready to publish.\n## End Summary"
        )

        results_iter = iter([
            # Plan — researcher + draft_writer → publisher
            MagicMock(result_text=(
                "```json\n" + json.dumps({
                    "campaign_goal": "test",
                    "phases": [
                        {
                            "phase": "draft_writer",
                            "task_title": "Write post",
                            "task_description": "Write it.",
                            "execution_type": "campaign_draft_writer",
                            "depends_on": [],
                        },
                        {
                            "phase": "publisher",
                            "task_title": "Publish post",
                            "task_description": "Publish it.",
                            "execution_type": "campaign_publisher",
                            "depends_on": ["draft_writer"],
                        },
                    ]
                }) + "\n```"
            ), session_id="s0"),
            # Draft writer — good output
            MagicMock(result_text=draft_output, session_id="s1"),
            # Publisher should never be called — approval gate should stop here
        ])

        async def _side_effect(*args, **kwargs):
            return next(results_iter)

        db = main_module.get_db_session()
        try:
            now = main_module.datetime.utcnow().isoformat()
            parent_task = main_module.TaskModel(
                title="Approval Gate Campaign",
                description="Should pause before publisher",
                execution_type="orchestrate_seo_campaign",
                status="in_progress",
                approved_at=None,  # not approved
                created_at=now,
                updated_at=now,
            )
            db.add(parent_task)
            db.commit()
            db.refresh(parent_task)
            orch_run = main_module._create_run(
                db, parent_task, "manual_execute", "orchestrate_seo_campaign"
            )

            with patch("agent.api.main._run_agent_prompt", side_effect=_side_effect):
                await run_campaign_orchestration(db, parent_task, orch_run)

            db.refresh(orch_run)
            db.refresh(parent_task)

            state = db.query(main_module.OrchestrationStateModel).filter(
                main_module.OrchestrationStateModel.orchestrator_run_id == orch_run.run_id
            ).first()

            assert state.status == "awaiting_approval", (
                f"Expected awaiting_approval, got {state.status}"
            )
            # Publisher phase must NOT have run — only 2 results consumed (plan + draft)
            with pytest.raises(StopIteration):
                next(results_iter)  # publisher result was never popped → still in iterator
        finally:
            db.close()
