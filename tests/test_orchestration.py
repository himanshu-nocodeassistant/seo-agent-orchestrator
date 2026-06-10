"""
Tests for the multi-agent campaign orchestration system.

Red/Green TDD:
1. RED  — write tests first
2. GREEN — implement to pass
3. REFACTOR — clean up

Uses the in-memory SQLite DB from conftest.py.
"""

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ============================================================================
# FIXTURES
# ============================================================================

MINIMAL_PLAN_JSON = {
    "campaign_goal": "Improve blog SEO for Q3",
    "phases": [
        {
            "phase": "researcher",
            "task_title": "Research: No-code automation keywords",
            "task_description": "Find high-intent keywords for no-code tools.",
            "execution_type": "campaign_researcher",
            "depends_on": [],
        },
        {
            "phase": "content_writer",
            "task_title": "Write: No-code automation guide",
            "task_description": "Write a 1200-word blog post using research findings.",
            "execution_type": "campaign_draft_writer",
            "depends_on": ["researcher"],
        },
        {
            "phase": "publisher",
            "task_title": "Publish: No-code guide to Webflow",
            "task_description": "Publish the written post to Webflow CMS.",
            "execution_type": "campaign_publisher",
            "depends_on": ["content_writer"],
        },
        {
            "phase": "analyst",
            "task_title": "Analyse: Post-publish ranking signals",
            "task_description": "Query GSC for clicks and impressions 7 days post-publish.",
            "execution_type": "campaign_analyst",
            "depends_on": ["publisher"],
        },
    ],
}

PLAN_OUTPUT = f"Here is the campaign plan:\n```json\n{json.dumps(MINIMAL_PLAN_JSON, indent=2)}\n```"

WRITER_OUTPUT = (
    "Title: No-Code Automation Guide | NocodeAssistant\n"
    "URL slug: no-code-automation-guide\n"
    "Word count: 1250\n"
    "Webflow status: manual-only\n"
    "<!-- CHANGE_LOG\n"
    '{"url": "https://example.com/no-code-automation-guide", "field": "content", "before": null, "after": "blog post"}\n'
    "-->"
)


def _make_exec_result(text: str, session_id: str = "sess-1"):
    """Create a mock AgentExecutionResult-like object."""
    r = MagicMock()
    r.result_text = text
    r.session_id = session_id
    return r


@pytest.fixture
def mock_run_agent_prompt():
    """
    Patches _run_agent_prompt so it returns exec results directly (no nested coroutines).
    Side effects: plan → researcher → writer → publisher → analyst.
    """
    results = [
        _make_exec_result(PLAN_OUTPUT, "s0"),
        _make_exec_result("Research complete: found 10 keywords. Source: https://ahrefs.com/keywords?q=no-code", "s1"),
        _make_exec_result(WRITER_OUTPUT, "s2"),
        _make_exec_result(
            "Published item 123.\n<!-- CHANGE_LOG\n"
            '{"url": "https://example.com/no-code-automation-guide", "field": "publish", "before": null, "after": "published"}\n'
            "-->", "s3"
        ),
        _make_exec_result("Analysis complete. No ranking data yet.", "s4"),
    ]
    call_index = {"n": 0}

    async def _side_effect(*args, **kwargs):
        idx = call_index["n"]
        call_index["n"] += 1
        return results[idx]

    with patch("agent.api.main._run_agent_prompt", side_effect=_side_effect):
        yield


@pytest.fixture
def mock_run_agent_prompt_writer_fails():
    """Writer phase raises an exception."""
    call_index = {"n": 0}

    async def _side_effect(*args, **kwargs):
        idx = call_index["n"]
        call_index["n"] += 1
        if idx == 0:
            return _make_exec_result(PLAN_OUTPUT, "s0")
        if idx == 1:
            return _make_exec_result("Research complete. Top keyword: no-code automation. Source: https://ahrefs.com/kw", "s1")
        raise RuntimeError("Writer agent timed out")

    with patch("agent.api.main._run_agent_prompt", side_effect=_side_effect):
        yield


# ============================================================================
# PLAN PARSING
# ============================================================================

class TestParsePlan:
    def test_valid_json_block_returns_phases(self):
        from agent.orchestrator import _parse_orchestration_plan
        phases = _parse_orchestration_plan(PLAN_OUTPUT)
        assert len(phases) == 4
        assert phases[0]["phase"] == "researcher"
        assert phases[1]["execution_type"] == "campaign_draft_writer"

    def test_missing_json_block_raises(self):
        from agent.orchestrator import _parse_orchestration_plan
        with pytest.raises(ValueError, match="no.*plan block"):
            _parse_orchestration_plan("I cannot produce a plan right now.")

    def test_malformed_json_raises(self):
        from agent.orchestrator import _parse_orchestration_plan
        with pytest.raises(ValueError, match="malformed"):
            _parse_orchestration_plan("```json\n{bad json\n```")

    def test_empty_phases_raises(self):
        from agent.orchestrator import _parse_orchestration_plan
        empty = json.dumps({"campaign_goal": "test", "phases": []})
        with pytest.raises(ValueError, match="empty"):
            _parse_orchestration_plan(f"```json\n{empty}\n```")


# ============================================================================
# ORCHESTRATION PLAN VALIDATOR
# ============================================================================

class TestValidateOrchestrationPlan:
    def test_valid_plan_passes(self):
        from agent.runtime_profiles import _validate_orchestration_plan
        result = _validate_orchestration_plan(PLAN_OUTPUT)
        assert result.status == "passed"

    def test_no_json_block_fails(self):
        from agent.runtime_profiles import _validate_orchestration_plan
        result = _validate_orchestration_plan("No plan here.")
        assert result.status == "failed"
        assert "JSON plan block" in result.message

    def test_empty_phases_fails(self):
        from agent.runtime_profiles import _validate_orchestration_plan
        plan = json.dumps({"phases": []})
        result = _validate_orchestration_plan(f"```json\n{plan}\n```")
        assert result.status == "failed"
        assert "phases" in result.message

    def test_malformed_json_fails(self):
        from agent.runtime_profiles import _validate_orchestration_plan
        result = _validate_orchestration_plan("```json\n{broken\n```")
        assert result.status == "failed"
        assert "parse error" in result.message.lower()


# ============================================================================
# INTER-AGENT CONTEXT BUILDING
# ============================================================================

class TestBuildChildPrompt:
    def test_includes_prior_phase_output(self):
        from agent.orchestrator import _build_child_prompt_with_prior_outputs
        result = _build_child_prompt_with_prior_outputs(
            "Write a blog post.",
            "content_writer",
            {"researcher": "Found keywords: no-code, automation, workflow."},
            "Improve blog SEO for Q3",
        )
        assert "researcher Agent Output" in result
        assert "Found keywords" in result
        assert "Write a blog post." in result

    def test_truncates_long_prior_output(self):
        from agent.orchestrator import _build_child_prompt_with_prior_outputs
        long_output = "x" * 3000
        result = _build_child_prompt_with_prior_outputs(
            "base prompt",
            "content_writer",
            {"researcher": long_output},
            "goal",
        )
        # 1500 chars + "..."
        assert "..." in result
        assert "x" * 1501 not in result

    def test_no_prior_outputs_section_for_first_phase(self):
        from agent.orchestrator import _build_child_prompt_with_prior_outputs
        result = _build_child_prompt_with_prior_outputs(
            "Do research.",
            "researcher",
            {},
            "Improve blog SEO",
        )
        assert "Prior Phases" not in result
        assert "Do research." in result
        assert "Campaign Context" in result


# ============================================================================
# CHILD TASK CREATION
# ============================================================================

class TestCreateChildTask:
    def test_child_task_has_parent_task_id(self, client):
        # Create a parent task
        resp = client.post("/tasks", json={
            "title": "Campaign: Q3 Blog SEO",
            "description": "Improve blog SEO for Q3",
            "execution_type": "orchestrate_seo_campaign",
        })
        assert resp.status_code == 200
        parent_id = resp.json()["id"]

        # Use the helper directly
        import agent.api.main as main_module
        db = main_module.get_db_session()
        try:
            parent_task = db.query(main_module.TaskModel).filter(
                main_module.TaskModel.id == parent_id
            ).first()
            from agent.orchestrator import _create_child_task
            child = _create_child_task(db, parent_task, MINIMAL_PLAN_JSON["phases"][0])
            assert child.parent_task_id == parent_id
        finally:
            db.close()

    def test_child_task_execution_type_from_phase_spec(self, client):
        resp = client.post("/tasks", json={
            "title": "Campaign: Q3 Blog SEO 2",
            "execution_type": "orchestrate_seo_campaign",
        })
        assert resp.status_code == 200
        parent_id = resp.json()["id"]

        import agent.api.main as main_module
        db = main_module.get_db_session()
        try:
            parent_task = db.query(main_module.TaskModel).filter(
                main_module.TaskModel.id == parent_id
            ).first()
            from agent.orchestrator import _create_child_task
            phase_spec = {
                "phase": "researcher",
                "task_title": "Research: keywords",
                "task_description": "Find keywords.",
                "execution_type": "campaign_researcher",
            }
            child = _create_child_task(db, parent_task, phase_spec)
            assert child.execution_type == "campaign_researcher"
        finally:
            db.close()


# ============================================================================
# PROFILES
# ============================================================================

class TestCampaignProfiles:
    def test_all_campaign_profiles_registered(self):
        from agent.runtime_profiles import PROFILE_REGISTRY
        for name in [
            "orchestrate_seo_campaign",
            "campaign_researcher",
            "campaign_draft_writer",
            "campaign_publisher",
            "campaign_analyst",
        ]:
            assert name in PROFILE_REGISTRY, f"Missing profile: {name}"

    def test_orchestrator_profile_does_not_resume_session(self):
        from agent.runtime_profiles import PROFILE_REGISTRY
        assert PROFILE_REGISTRY["orchestrate_seo_campaign"].should_resume_session is False

    def test_analyst_profile_does_not_resume_session(self):
        from agent.runtime_profiles import PROFILE_REGISTRY
        assert PROFILE_REGISTRY["campaign_analyst"].should_resume_session is False

    def test_orchestrate_seo_campaign_in_executable_types(self):
        from agent.api.main import EXECUTABLE_TYPES
        assert "orchestrate_seo_campaign" in EXECUTABLE_TYPES

    def test_existing_profiles_unchanged(self):
        from agent.runtime_profiles import PROFILE_REGISTRY
        # Existing profiles must still be present
        for name in ["research", "blog_write", "rewrite_title", "manual", "seo_impact_review"]:
            assert name in PROFILE_REGISTRY, f"Existing profile missing: {name}"


# ============================================================================
# API ROUTING
# ============================================================================

class TestAPIRouting:
    def test_execute_task_routes_orchestrate_type(self, client, mock_run_agent_prompt):
        """orchestrate_seo_campaign tasks hit the orchestrator branch."""
        resp = client.post("/tasks", json={
            "title": "Q3 Blog Campaign",
            "description": "Run a full SEO campaign for Q3 blog content.",
            "execution_type": "orchestrate_seo_campaign",
        })
        task_id = resp.json()["id"]

        exec_resp = client.post(f"/tasks/{task_id}/execute")
        assert exec_resp.status_code == 200
        data = exec_resp.json()
        assert data["execution_type"] == "orchestrate_seo_campaign"

    def test_execute_single_agent_type_not_affected(self, client):
        """research tasks still go through the single-agent path."""
        resp = client.post("/tasks", json={
            "title": "Research: Bubble alternatives",
            "execution_type": "research",
        })
        task_id = resp.json()["id"]

        with patch("agent.api.main._run_agent_prompt") as mock:
            mock.return_value = AsyncMock(return_value=_make_exec_result("Research done."))()
            exec_resp = client.post(f"/tasks/{task_id}/execute")
        assert exec_resp.status_code == 200
        data = exec_resp.json()
        assert data["execution_type"] == "research"

    def test_get_orchestration_state_returns_404_for_unknown(self, client):
        resp = client.get("/orchestrations/nonexistent-run-id")
        assert resp.status_code == 404


# ============================================================================
# HAPPY PATH — FULL ORCHESTRATION
# ============================================================================

class TestFullOrchestration:
    @pytest.mark.asyncio
    async def test_happy_path_all_phases_complete(self, mock_run_agent_prompt):
        """
        All 4 phases run. OrchestrationStateModel.status='completed'.
        Each child AgentRunModel has parent_run_id set.
        phase_outputs_json contains all 4 phase keys.
        """
        import agent.api.main as main_module
        from agent.orchestrator import run_campaign_orchestration

        db = main_module.get_db_session()
        try:
            now = main_module.datetime.utcnow().isoformat()
            parent_task = main_module.TaskModel(
                title="Campaign: Q3 Blog SEO Happy",
                description="Improve blog SEO for Q3",
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

            await run_campaign_orchestration(db, parent_task, orch_run)
            db.refresh(orch_run)

            # Orchestrator run should be completed
            assert orch_run.status == "completed"

            # OrchestrationStateModel should exist and be completed
            state = db.query(main_module.OrchestrationStateModel).filter(
                main_module.OrchestrationStateModel.orchestrator_run_id == orch_run.run_id
            ).first()
            assert state is not None
            assert state.status == "completed"

            # All 4 phases should appear in phase_outputs
            phase_outputs = json.loads(state.phase_outputs_json)
            assert set(phase_outputs.keys()) == {"researcher", "content_writer", "publisher", "analyst"}

            # Child runs should have parent_run_id set
            child_run_ids = json.loads(state.child_run_ids_json)
            assert len(child_run_ids) == 4
            for child_run_id in child_run_ids:
                child_run = db.query(main_module.AgentRunModel).filter(
                    main_module.AgentRunModel.run_id == child_run_id
                ).first()
                assert child_run is not None
                assert child_run.parent_run_id == orch_run.run_id
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_failure_stops_pipeline(self, mock_run_agent_prompt_writer_fails):
        """
        When content_writer fails, publisher and analyst stay pending.
        Parent task becomes blocked. OrchestrationStateModel.status='error'.
        """
        import agent.api.main as main_module
        from agent.orchestrator import run_campaign_orchestration

        db = main_module.get_db_session()
        try:
            now = main_module.datetime.utcnow().isoformat()
            parent_task = main_module.TaskModel(
                title="Campaign: Q3 Blog SEO Fail",
                description="Improve blog SEO for Q3",
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

            await run_campaign_orchestration(db, parent_task, orch_run)
            db.refresh(orch_run)
            db.refresh(parent_task)

            # Orchestrator run should be failed/blocked
            assert orch_run.status in ("failed", "blocked")

            # Parent task should be blocked
            assert parent_task.status == "blocked"

            # OrchestrationStateModel should exist and be in error
            state = db.query(main_module.OrchestrationStateModel).filter(
                main_module.OrchestrationStateModel.orchestrator_run_id == orch_run.run_id
            ).first()
            assert state is not None
            assert state.status == "error"

            # Only researcher output should have been captured
            phase_outputs = json.loads(state.phase_outputs_json)
            assert "researcher" in phase_outputs
            assert "content_writer" not in phase_outputs

            # Remaining child tasks (publisher, analyst) should be pending
            child_tasks = db.query(main_module.TaskModel).filter(
                main_module.TaskModel.parent_task_id == parent_task.id
            ).all()
            statuses = {t.execution_type: t.status for t in child_tasks}
            assert statuses.get("campaign_publisher") == "pending"
            assert statuses.get("campaign_analyst") == "pending"
        finally:
            db.close()


# ============================================================================
# ORCHESTRATION STATE ENDPOINT
# ============================================================================

class TestOrchestrationStateEndpoint:
    def test_get_orchestration_state_after_run(self, client, mock_run_agent_prompt):
        """
        After an orchestrate_seo_campaign execution, GET /orchestrations/{run_id}
        returns the state with child_tasks populated.
        """
        resp = client.post("/tasks", json={
            "title": "Q3 Blog Campaign Endpoint Test",
            "description": "Full campaign",
            "execution_type": "orchestrate_seo_campaign",
        })
        task_id = resp.json()["id"]

        exec_resp = client.post(f"/tasks/{task_id}/execute")
        assert exec_resp.status_code == 200
        run_id = exec_resp.json()["run_id"]

        state_resp = client.get(f"/orchestrations/{run_id}")
        assert state_resp.status_code == 200
        data = state_resp.json()
        assert data["orchestrator_run_id"] == run_id
        assert data["status"] in ("completed", "error", "running")
        assert "child_tasks" in data
        assert "phases_completed" in data


# ============================================================================
# #4 — STRUCTURED PHASE SUMMARIES
# ============================================================================

class TestStructuredPhaseSummaries:
    def test_summary_block_extracted_when_present(self):
        """If prior agent wrote a ## Summary for Next Phase block, use it instead of truncating."""
        from agent.orchestrator import _build_child_prompt_with_prior_outputs

        output_with_summary = (
            "Lots of detailed research output...\n"
            "## Summary for Next Phase\n"
            "Top keywords: no-code, automation. Recommended angle: productivity.\n"
            "## End Summary\n"
        )
        result = _build_child_prompt_with_prior_outputs(
            "Write a blog post.",
            "content_writer",
            {"researcher": output_with_summary},
            "Improve blog SEO for Q3",
        )
        assert "Top keywords: no-code, automation" in result
        # Raw detail should not appear — only the summary was injected
        assert "Lots of detailed research output" not in result

    def test_falls_back_to_truncation_when_no_summary_block(self):
        """Without a summary block, truncation still works as before."""
        from agent.orchestrator import _build_child_prompt_with_prior_outputs

        long_output = "keyword: " + ("x" * 3000)
        result = _build_child_prompt_with_prior_outputs(
            "base prompt",
            "content_writer",
            {"researcher": long_output},
            "goal",
        )
        assert "..." in result
        assert "x" * 1501 not in result

    def test_summary_block_label_in_output(self):
        """The injected section heading should indicate it came from the summary block."""
        from agent.orchestrator import _build_child_prompt_with_prior_outputs

        output_with_summary = (
            "## Summary for Next Phase\n"
            "Focus on long-tail keywords.\n"
            "## End Summary\n"
        )
        result = _build_child_prompt_with_prior_outputs(
            "Write.",
            "content_writer",
            {"researcher": output_with_summary},
            "Q3 campaign",
        )
        assert "researcher" in result.lower()
        assert "Focus on long-tail keywords" in result


# ============================================================================
# #3 — PARALLEL DAG EXECUTION
# ============================================================================

PARALLEL_PLAN_JSON = {
    "campaign_goal": "Run two research streams in parallel",
    "phases": [
        {
            "phase": "keyword_researcher",
            "task_title": "Research: Keywords",
            "task_description": "Find keywords.",
            "execution_type": "campaign_researcher",
            "depends_on": [],
        },
        {
            "phase": "competitor_researcher",
            "task_title": "Research: Competitors",
            "task_description": "Analyse competitors.",
            "execution_type": "campaign_researcher",
            "depends_on": [],
        },
        {
            "phase": "content_writer",
            "task_title": "Write: Combined guide",
            "task_description": "Write using both research outputs.",
            "execution_type": "campaign_draft_writer",
            "depends_on": ["keyword_researcher", "competitor_researcher"],
        },
    ],
}

PARALLEL_PLAN_OUTPUT = f"Plan:\n```json\n{json.dumps(PARALLEL_PLAN_JSON, indent=2)}\n```"


class TestDAGResolution:
    def test_independent_phases_identified(self):
        """Phases with no depends_on (or all deps met) are in the first execution tier."""
        from agent.orchestrator import _resolve_execution_tiers

        phases = PARALLEL_PLAN_JSON["phases"]
        tiers = _resolve_execution_tiers(phases)
        assert len(tiers) == 2
        # Tier 0: both researcher phases (no dependencies)
        tier0_names = {p["phase"] for p in tiers[0]}
        assert tier0_names == {"keyword_researcher", "competitor_researcher"}
        # Tier 1: writer depends on both researchers
        tier1_names = {p["phase"] for p in tiers[1]}
        assert tier1_names == {"content_writer"}

    def test_serial_chain_produces_single_phase_tiers(self):
        """A -> B -> C produces 3 single-item tiers (no parallelism)."""
        from agent.orchestrator import _resolve_execution_tiers

        phases = MINIMAL_PLAN_JSON["phases"]  # researcher -> writer -> publisher -> analyst
        tiers = _resolve_execution_tiers(phases)
        assert len(tiers) == 4
        for tier in tiers:
            assert len(tier) == 1

    def test_unknown_dependency_raises(self):
        """A phase that depends_on a non-existent phase raises ValueError."""
        from agent.orchestrator import _resolve_execution_tiers

        phases = [
            {"phase": "writer", "depends_on": ["ghost_researcher"]},
        ]
        with pytest.raises(ValueError, match="ghost_researcher"):
            _resolve_execution_tiers(phases)

    def test_circular_dependency_raises(self):
        """A -> B -> A produces a ValueError."""
        from agent.orchestrator import _resolve_execution_tiers

        phases = [
            {"phase": "A", "depends_on": ["B"]},
            {"phase": "B", "depends_on": ["A"]},
        ]
        with pytest.raises(ValueError, match="[Cc]ircular"):
            _resolve_execution_tiers(phases)


@pytest.fixture
def mock_parallel_agent_prompt():
    """
    Returns results for: plan → keyword_researcher → competitor_researcher → content_writer.
    The two researchers run concurrently so call order between them is nondeterministic;
    we use a thread-safe counter keyed by execution index.
    """
    WRITER_OUT = (
        "Title: Combined Guide | NocodeAssistant\n"
        "URL slug: combined-guide\n"
        "Word count: 1300\n"
        "Webflow status: manual-only\n"
        "<!-- CHANGE_LOG\n"
        '{"url": "https://example.com/combined-guide", "field": "content", "before": null, "after": "post"}\n'
        "-->"
    )
    results = [
        _make_exec_result(PARALLEL_PLAN_OUTPUT, "s0"),    # orchestrator plan
        _make_exec_result("Keyword research done. Top keyword: no-code tools. Source: https://ahrefs.com/kw", "s1"),  # keyword_researcher
        _make_exec_result("Competitor analysis done. Top keyword: workflow automation. Source: https://semrush.com/kw", "s2"),  # competitor_researcher
        _make_exec_result(WRITER_OUT, "s3"),               # content_writer
    ]
    call_index = {"n": 0}
    import asyncio
    lock = asyncio.Lock()

    async def _side_effect(*args, **kwargs):
        async with lock:
            idx = call_index["n"]
            call_index["n"] += 1
        return results[idx]

    with patch("agent.api.main._run_agent_prompt", side_effect=_side_effect):
        yield


class TestParallelOrchestration:
    @pytest.mark.asyncio
    async def test_parallel_phases_both_complete(self, mock_parallel_agent_prompt):
        """Independent phases run in parallel; all outputs stored."""
        import agent.api.main as main_module
        from agent.orchestrator import run_campaign_orchestration

        db = main_module.get_db_session()
        try:
            now = main_module.datetime.utcnow().isoformat()
            parent_task = main_module.TaskModel(
                title="Parallel Campaign",
                description="Two parallel researchers then a writer",
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
            await run_campaign_orchestration(db, parent_task, orch_run)
            db.refresh(orch_run)

            assert orch_run.status == "completed"
            state = db.query(main_module.OrchestrationStateModel).filter(
                main_module.OrchestrationStateModel.orchestrator_run_id == orch_run.run_id
            ).first()
            assert state.status == "completed"
            phase_outputs = json.loads(state.phase_outputs_json)
            assert "keyword_researcher" in phase_outputs
            assert "competitor_researcher" in phase_outputs
            assert "content_writer" in phase_outputs
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_parallel_failure_stops_campaign(self):
        """If one parallel phase fails, the campaign stops (fail-fast)."""
        import agent.api.main as main_module
        from agent.orchestrator import run_campaign_orchestration

        call_index = {"n": 0}

        async def _side_effect(*args, **kwargs):
            idx = call_index["n"]
            call_index["n"] += 1
            if idx == 0:
                return _make_exec_result(PARALLEL_PLAN_OUTPUT, "s0")
            if idx == 1:
                return _make_exec_result("Keyword research done. Top keyword: no-code. Source: https://ahrefs.com/kw", "s1")
            raise RuntimeError("Competitor agent failed")

        db = main_module.get_db_session()
        try:
            now = main_module.datetime.utcnow().isoformat()
            parent_task = main_module.TaskModel(
                title="Parallel Fail Campaign",
                description="Parallel researchers, one fails",
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

            assert parent_task.status == "blocked"
            state = db.query(main_module.OrchestrationStateModel).filter(
                main_module.OrchestrationStateModel.orchestrator_run_id == orch_run.run_id
            ).first()
            assert state.status == "error"
            # content_writer should not have run
            phase_outputs = json.loads(state.phase_outputs_json)
            assert "content_writer" not in phase_outputs
        finally:
            db.close()


# ============================================================================
# #7 — RETRY WITH BACKOFF
# ============================================================================

class TestRetryWithBackoff:
    @pytest.mark.asyncio
    async def test_transient_failure_retried(self):
        """A timeout error is retried up to max_retries times."""
        from agent.orchestrator import _run_with_retry

        call_count = {"n": 0}

        async def flaky(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] < 3:
                raise RuntimeError("Agent execution timed out after 300s")
            return _make_exec_result("Success after retry")

        result = await _run_with_retry(flaky, max_retries=3, base_delay=0.0)
        assert result.result_text == "Success after retry"
        assert call_count["n"] == 3

    @pytest.mark.asyncio
    async def test_non_retryable_error_raises_immediately(self):
        """Budget-exceeded errors are not retried."""
        from agent.orchestrator import _run_with_retry

        call_count = {"n": 0}

        async def budget_error(*args, **kwargs):
            call_count["n"] += 1
            raise RuntimeError("Budget limit exceeded")

        with pytest.raises(RuntimeError, match="Budget limit exceeded"):
            await _run_with_retry(budget_error, max_retries=3, base_delay=0.0)

        assert call_count["n"] == 1  # no retry

    @pytest.mark.asyncio
    async def test_exhausted_retries_raises(self):
        """When all retries are exhausted, the original error propagates."""
        from agent.orchestrator import _run_with_retry

        async def always_fails(*args, **kwargs):
            raise RuntimeError("Agent execution timed out after 300s")

        with pytest.raises(RuntimeError, match="timed out"):
            await _run_with_retry(always_fails, max_retries=2, base_delay=0.0)

    @pytest.mark.asyncio
    async def test_plan_parse_error_not_retried(self):
        """Logic errors (bad plan format) must not be retried."""
        from agent.orchestrator import _run_with_retry

        call_count = {"n": 0}

        async def bad_plan(*args, **kwargs):
            call_count["n"] += 1
            raise ValueError("Plan JSON is malformed")

        with pytest.raises(ValueError):
            await _run_with_retry(bad_plan, max_retries=3, base_delay=0.0)

        assert call_count["n"] == 1


# ============================================================================
# #5 — SDK RESULT HARDENING
# ============================================================================

class TestSDKResultHardening:
    def test_normalize_handles_known_result_type(self):
        """AgentExecutionResult-like objects pass through unchanged."""
        from agent.api.main import _normalize_execution_result

        mock_result = MagicMock()
        mock_result.result_text = "Done."
        mock_result.session_id = "sess-x"
        result = _normalize_execution_result(mock_result)
        assert result.result_text == "Done."
        assert result.session_id == "sess-x"

    def test_normalize_handles_plain_string(self):
        """Plain string results are wrapped safely."""
        from agent.api.main import _normalize_execution_result

        result = _normalize_execution_result("plain string output")
        assert result.result_text == "plain string output"
        assert result.session_id is None

    def test_normalize_unknown_type_logs_and_wraps(self):
        """An unexpected result type is logged and converted to a safe wrapper."""
        from agent.api.main import _normalize_execution_result
        import logging

        unknown = {"type": "unexpected_sdk_event", "data": "something"}
        with patch("agent.api.main.logger") as mock_logger:
            result = _normalize_execution_result(unknown)
        mock_logger.warning.assert_called_once()
        warning_msg = mock_logger.warning.call_args[0][0]
        assert "unexpected" in warning_msg.lower() or "unknown" in warning_msg.lower()
        assert result.result_text is not None  # graceful, not None

    def test_normalize_none_result_handled(self):
        """None result is wrapped without crashing."""
        from agent.api.main import _normalize_execution_result

        result = _normalize_execution_result(None)
        assert result.result_text == "" or result.result_text is None
