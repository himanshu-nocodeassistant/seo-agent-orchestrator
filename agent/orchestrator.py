"""
Multi-agent campaign orchestrator.

Python-managed dispatch loop: the orchestrator agent produces a JSON plan,
then this module creates child tasks and runs each specialized child agent,
with DAG-based tier resolution for parallelism and retry on transient failures.

Scalability note (#1): `run_campaign_orchestration` is called inside a FastAPI
async endpoint on a single uvicorn worker. For production scale, move campaign
dispatch to a task queue (Celery + Redis, or arq) and return a 202 Accepted
with a polling endpoint. The DB schema is already queue-friendly: each
AgentRunModel has parent_run_id and status, and OrchestrationStateModel tracks
current_phase so a worker can resume after restart.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from datetime import datetime
from typing import Optional
from uuid import uuid4

logger = logging.getLogger(__name__)

# Errors whose message matches these patterns are transient and safe to retry.
_RETRYABLE_PATTERNS = [
    r"timed out",
    r"timeout",
    r"connection reset",
    r"503",
    r"502",
    r"rate.?limit",
    r"temporarily unavailable",
]

# These patterns indicate logic or budget errors — retrying would waste money or loop forever.
_NON_RETRYABLE_PATTERNS = [
    r"budget.*(exceeded|limit)",
    r"malformed",
    r"no.*plan block",
    r"dependency",
    r"circular",
]


def _is_retryable(exc: BaseException) -> bool:
    """Return True if the exception is a transient failure worth retrying."""
    msg = str(exc).lower()
    for pattern in _NON_RETRYABLE_PATTERNS:
        if re.search(pattern, msg):
            return False
    for pattern in _RETRYABLE_PATTERNS:
        if re.search(pattern, msg):
            return True
    # Non-RuntimeError exceptions (ValueError, TypeError) are logic errors — don't retry.
    return False


async def _run_with_retry(
    coro_fn,
    *args,
    max_retries: int = 2,
    base_delay: float = 1.0,
    max_total_seconds: Optional[float] = None,
    **kwargs,
):
    """
    Call `coro_fn(*args, **kwargs)` with exponential backoff on transient failures.

    Args:
        coro_fn: Async callable to retry.
        max_retries: Total attempts (1 = no retry).
        base_delay: Initial sleep between retries in seconds (doubled each attempt).
        max_total_seconds: Optional wall-clock deadline across all attempts. If set,
            each attempt checks the clock before running; if the deadline has passed,
            raises RuntimeError immediately rather than retrying.

    Raises:
        The last exception if all retries are exhausted or the error is non-retryable.
        RuntimeError if max_total_seconds is exceeded before all retries are used.

    Scalability note (#7): In production, circuit-breaker logic (e.g. tenacity with
    circuit_breaker) would prevent hammering a downstream that's fully down.
    """
    deadline = time.monotonic() + max_total_seconds if max_total_seconds is not None else None
    last_exc: Optional[BaseException] = None
    delay = base_delay
    for attempt in range(max_retries):
        if deadline is not None and time.monotonic() > deadline:
            raise RuntimeError(
                f"_run_with_retry exceeded max_total_seconds={max_total_seconds} "
                f"after {attempt} attempt(s)"
            )
        try:
            return await coro_fn(*args, **kwargs)
        except BaseException as exc:
            if not _is_retryable(exc):
                raise
            last_exc = exc
            if attempt < max_retries - 1:
                if deadline is not None and time.monotonic() > deadline:
                    raise RuntimeError(
                        f"_run_with_retry exceeded max_total_seconds={max_total_seconds} "
                        f"after {attempt + 1} attempt(s)"
                    )
                logger.warning(
                    "Transient failure (attempt %d/%d): %s — retrying in %.1fs",
                    attempt + 1, max_retries, exc, delay,
                )
                await asyncio.sleep(delay)
                delay *= 2
    raise last_exc


def _extract_summary_block(output: str) -> Optional[str]:
    """
    Extract the content between '## Summary for Next Phase' and '## End Summary'.

    Returns None if no such block exists.

    Inter-agent protocol (#4): agents are instructed to close their output with a
    '## Summary for Next Phase ... ## End Summary' block. This keeps cross-agent
    context tight (no raw truncation of long outputs) and gives the next agent
    a clean, structured handoff rather than a truncated wall of text.
    """
    match = re.search(
        r"##\s*Summary for Next Phase\s*\n(.*?)##\s*End Summary",
        output,
        re.DOTALL | re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()
    return None


def _parse_orchestration_plan(result_text: str) -> list[dict]:
    """
    Extract and return the phases list from the orchestrator's JSON plan block.

    Raises:
        ValueError: when no valid JSON plan block with at least one phase is found.
    """
    match = re.search(r"```json\s*(.*?)```", result_text, re.DOTALL)
    if not match:
        raise ValueError("Orchestrator output contains no ```json ... ``` plan block.")
    try:
        plan = json.loads(match.group(1))
    except json.JSONDecodeError as e:
        raise ValueError(f"Plan JSON is malformed: {e}") from e
    phases = plan.get("phases")
    if not phases:
        raise ValueError("Plan JSON has no 'phases' list or phases is empty.")
    return phases


def _resolve_execution_tiers(phases: list[dict]) -> list[list[dict]]:
    """
    Topological sort of phases into parallel execution tiers using Kahn's algorithm.

    Each tier is a list of phases whose dependencies are all satisfied by
    previous tiers. Phases in the same tier can run concurrently.

    Args:
        phases: List of phase dicts, each with 'phase' and 'depends_on' keys.

    Returns:
        List of tiers, each tier being a list of phase dicts.

    Raises:
        ValueError: if a phase depends on an unknown phase or a circular dependency exists.
    """
    phase_names = {p["phase"] for p in phases}
    for p in phases:
        for dep in p.get("depends_on", []):
            if dep not in phase_names:
                raise ValueError(
                    f"Phase '{p['phase']}' depends on unknown phase '{dep}'."
                )

    # Kahn's algorithm
    in_degree: dict[str, int] = {p["phase"]: 0 for p in phases}
    dependents: dict[str, list[str]] = {p["phase"]: [] for p in phases}
    phase_map = {p["phase"]: p for p in phases}

    for p in phases:
        for dep in p.get("depends_on", []):
            dependents[dep].append(p["phase"])
            in_degree[p["phase"]] += 1

    tiers: list[list[dict]] = []
    queue = [name for name, deg in in_degree.items() if deg == 0]

    while queue:
        tier = [phase_map[name] for name in queue]
        tiers.append(tier)
        next_queue = []
        for name in queue:
            for dep_name in dependents[name]:
                in_degree[dep_name] -= 1
                if in_degree[dep_name] == 0:
                    next_queue.append(dep_name)
        queue = next_queue

    phases_scheduled = sum(len(t) for t in tiers)
    if phases_scheduled != len(phases):
        raise ValueError(
            "Circular dependency detected in campaign plan — cannot resolve execution order."
        )

    return tiers


def _build_child_prompt_with_prior_outputs(
    base_prompt: str,
    phase: str,
    phase_outputs: dict[str, str],
    campaign_goal: str,
) -> str:
    """
    Prepend campaign context and prior phase summaries to a child agent's prompt.

    Uses structured summary blocks when available (#4); falls back to 1500-char
    truncation when the prior agent did not write a summary block.

    Agents should close their output with:
        ## Summary for Next Phase
        <concise handoff notes>
        ## End Summary
    """
    lines = [
        "## Campaign Context",
        f"Goal: {campaign_goal}",
        f"Your role in this campaign: {phase} agent",
        "",
    ]

    if phase_outputs:
        lines.append("## Outputs from Prior Phases")
        for prior_phase, output in phase_outputs.items():
            summary = _extract_summary_block(output)
            if summary:
                lines.append(f"### {prior_phase} Agent Summary")
                lines.append(summary)
            else:
                truncated = output[:1500] + ("..." if len(output) > 1500 else "")
                lines.append(f"### {prior_phase} Agent Output")
                lines.append(truncated)
            lines.append("")

    lines.append("## Your Task")
    lines.append(base_prompt)
    lines.append("")
    lines.append(
        "When you finish, write a '## Summary for Next Phase' block followed by "
        "'## End Summary' with a concise handoff for the next agent."
    )

    return "\n".join(lines)


async def _dispatch_phase(
    db,
    phase_spec: dict,
    child_task_id: int,
    orchestrator_run_id: str,
    phase_outputs: dict[str, str],
    campaign_goal: str,
    helpers: dict,
    phase_has_dependents: bool,
    ownership_guard=None,
) -> tuple[str, str, bool]:
    """
    Run a single child agent phase and return (phase_name, result_text, degraded).

    ``degraded`` is True when the phase had downstream dependents but its final
    output still lacked a ``## Summary for Next Phase`` block after one
    correction retry, so the next agent will receive a truncated handoff.

    Raises on failure so the caller can apply fail-fast logic.

    Session isolation: each phase gets its own DB session so concurrent tier
    phases never share/interleave a SQLAlchemy session (the PostToolUse hook
    and run/task writes all go through the phase-local session).
    """
    from agent.db import SessionLocal, TaskModel
    from agent.runtime_profiles import get_execution_profile

    phase_name = phase_spec["phase"]
    child_exec_type = phase_spec.get("execution_type", phase_name)
    child_profile = get_execution_profile(child_exec_type)
    guard = ownership_guard or (lambda: None)

    phase_db = SessionLocal()
    try:
        guard()
        child_task = phase_db.query(TaskModel).filter(TaskModel.id == child_task_id).first()
        if child_task is None:
            raise RuntimeError(f"Child task {child_task_id} not found for phase [{phase_name}]")

        base_child_prompt = helpers["build_execution_prompt"](child_task, comments=[])
        child_prompt = _build_child_prompt_with_prior_outputs(
            base_child_prompt, phase_name, phase_outputs, campaign_goal
        )

        child_run = _create_child_run(
            phase_db, child_task, orchestrator_run_id, child_exec_type
        )

        child_prompt_context = helpers["_resolve_prompt_context"](
            phase_db, child_run, child_task, [], child_prompt, child_profile
        )
        child_run.prompt_text = child_prompt
        helpers["_mark_run_started"](
            phase_db, child_run, child_prompt_context, child_profile.execution_type, None
        )
        child_config = helpers["_build_runtime_config"](
            child_profile, None, db=phase_db, run_id=child_run.run_id
        )

        guard()
        child_execution = helpers["_normalize_execution_result"](
            await _run_with_retry(
                helpers["_run_agent_prompt"],
                child_prompt,
                child_config,
                child_prompt_context,
                max_retries=2,
                base_delay=1.0,
                max_total_seconds=child_profile.timeout_seconds,
            )
        )
        guard()
        result_text = child_execution.result_text or ""
        session_id = child_execution.session_id

        # Handoff protocol (#4): phases with dependents must end with a
        # '## Summary for Next Phase' block. If missing, run ONE correction
        # retry asking only for the block — no extra cost for final phases.
        if phase_has_dependents and _extract_summary_block(result_text) is None:
            guard()
            retry_prompt = (
                f"{child_prompt}\n\nIMPORTANT: Your previous output did not include "
                "a structured handoff for the next phase. Keep everything you "
                "produced, but append this block at the very end of your final "
                "output:\n\n"
                "## Summary for Next Phase\n"
                "<concise handoff notes for the next agent>\n"
                "## End Summary"
            )
            retry_execution = helpers["_normalize_execution_result"](
                await _run_with_retry(
                    helpers["_run_agent_prompt"],
                    retry_prompt,
                    child_config,
                    child_prompt_context,
                    max_retries=1,
                    base_delay=1.0,
                    max_total_seconds=child_profile.timeout_seconds,
                )
            )
            if retry_execution.result_text:
                result_text = retry_execution.result_text
                session_id = retry_execution.session_id or session_id

        guard()
        child_validation = child_profile.validator(result_text)
        if child_validation.status == "failed":
            raise RuntimeError(
                f"Phase [{phase_name}] output failed validation: {child_validation.message}"
            )
        helpers["_finalize_run_success"](
            phase_db, child_run, child_task,
            result_text,
            session_id,
            child_validation,
        )
        helpers["_refresh_context_view"](phase_db, task_id=child_task.id)

        degraded = phase_has_dependents and _extract_summary_block(result_text) is None
        return phase_name, result_text, degraded
    finally:
        phase_db.close()


async def run_campaign_orchestration(
    db,
    parent_task,
    orchestrator_run,
    resume: bool = False,
    ownership_guard=None,
    run_claim=None,
) -> None:
    """
    Drive a full multi-agent SEO campaign from a single orchestrator run.

    Flow (fresh run):
    1. Run the orchestrator agent to produce a JSON plan.
    2. Parse the plan, validate every phase's execution_type, and resolve
       execution tiers (DAG-based).
    3. Create child TaskModel rows (one per phase).
    4. Dispatch each tier: phases within a tier run concurrently via asyncio.gather.
       Fail-fast: if any phase in a tier fails, remaining tiers are skipped.
    5. Finalize the orchestrator run.

    Resume flow (``resume=True``):
    - Requires an OrchestrationStateModel with status='awaiting_approval' for
      this run and ``parent_task.approved_at`` set.
    - Skips plan creation; reloads the saved plan, phase outputs and child runs;
      continues from the first tier with pending phases on the SAME orchestrator
      run (no re-billing the orchestrator).

    Args:
        db: SQLAlchemy session (caller owns lifecycle).
        parent_task: TaskModel for the orchestrate_seo_campaign task.
        orchestrator_run: AgentRunModel created by execute_task for this run.
        resume: Whether this call is resuming a paused campaign.
    """
    # Import here to avoid circular imports (main imports orchestrator, orchestrator
    # needs models and helpers from main).
    from agent.api import helpers as helpers_module
    from agent.db import (
        AgentRunModel,
        OrchestrationStateModel,
        TaskModel,
    )
    from agent.prompts import build_execution_prompt
    from agent.runtime_profiles import ValidationResult, get_execution_profile

    helpers = {
        "build_execution_prompt": build_execution_prompt,
        "_build_runtime_config": helpers_module._build_runtime_config,
        "_finalize_run_failure": helpers_module._finalize_run_failure,
        "_finalize_run_success": helpers_module._finalize_run_success,
        "_mark_run_started": helpers_module._mark_run_started,
        "_normalize_execution_result": helpers_module._normalize_execution_result,
        "_refresh_context_view": helpers_module._refresh_context_view,
        "_resolve_prompt_context": helpers_module._resolve_prompt_context,
        "_run_agent_prompt": helpers_module._run_agent_prompt,
    }
    guard = ownership_guard or (lambda: None)

    campaign_goal = parent_task.description or parent_task.title
    guard()

    # ── Resume path: reuse the saved plan/state from the paused run ───────────
    if resume:
        guard()
        state = db.query(OrchestrationStateModel).filter(
            OrchestrationStateModel.orchestrator_run_id == orchestrator_run.run_id
        ).first()
        if state is None or state.status != "awaiting_approval":
            raise RuntimeError(
                "Cannot resume: no campaign paused awaiting approval for this run."
            )
        if not parent_task.approved_at:
            raise RuntimeError("Cannot resume: task has not been approved yet.")
        try:
            phases = _parse_orchestration_plan(state.plan_json or "")
            tiers = _resolve_execution_tiers(phases)
            phase_outputs = json.loads(state.phase_outputs_json or "{}")
            child_run_ids = json.loads(state.child_run_ids_json or "[]")
        except (ValueError, json.JSONDecodeError) as e:
            helpers_module._finalize_run_failure(
                db,
                orchestrator_run,
                parent_task,
                f"Resume failed: {e}",
                claim=run_claim,
            )
            helpers_module.add_task_failed_comment(
                db, parent_task.id, f"Resume failed: {e}"
            )
            return
        plan_text = state.plan_json or ""
        helpers_module.add_task_comment(
            db, parent_task.id, "Campaign resuming after approval.", "agent"
        )
        state.status = "running"
        state.updated_at = datetime.utcnow().isoformat()
        db.commit()
        guard()

        # Reload existing child tasks (matched by the deterministic title scheme
        # used in _create_child_task) and drop tiers that are fully completed.
        existing_children = db.query(TaskModel).filter(
            TaskModel.parent_task_id == parent_task.id
        ).all()
        by_title = {c.title: c for c in existing_children}
        child_tasks: dict[str, TaskModel] = {}
        for phase_spec in phases:
            title = phase_spec.get("task_title", f"Campaign: {phase_spec['phase']}")
            child_task = by_title.get(title)
            if child_task is None:
                raise RuntimeError(
                    f"Cannot resume: child task for phase [{phase_spec['phase']}] is missing."
                )
            child_tasks[phase_spec["phase"]] = child_task

        completed = set(phase_outputs)
        tiers = [
            tier
            for tier in tiers
            if any(p["phase"] not in completed for p in tier)
        ]
        if not tiers:
            summary = "Campaign already completed."
            helpers_module._finalize_run_success(
                db, orchestrator_run, parent_task, summary, None,
                ValidationResult(status="passed"), claim=run_claim,
            )
            helpers_module.add_task_completed_comment(db, parent_task.id, summary)
            return

    # ── Fresh run: orchestrator produces plan ────────────────────────────────
    else:
        guard()
        orch_profile = get_execution_profile("orchestrate_seo_campaign")
        orch_config = helpers_module._build_runtime_config(orch_profile, None)

        orch_prompt_context = helpers_module._resolve_prompt_context(
            db, orchestrator_run, parent_task, [], "", orch_profile
        )
        orchestrator_run.prompt_text = build_execution_prompt(parent_task, comments=[])
        helpers_module._mark_run_started(
            db, orchestrator_run, orch_prompt_context, orch_profile.execution_type, None
        )

        raw_execution = helpers_module._normalize_execution_result(
            await _run_with_retry(
                helpers_module._run_agent_prompt,
                orchestrator_run.prompt_text,
                orch_config,
                orch_prompt_context,
                max_retries=2,
                base_delay=1.0,
                max_total_seconds=orch_profile.timeout_seconds,
            )
        )
        guard()
        plan_text = raw_execution.result_text or ""

        try:
            phases = _parse_orchestration_plan(plan_text)
            # Fail fast: every phase execution_type must resolve before any
            # child task is created or any tier is dispatched.
            for phase_spec in phases:
                get_execution_profile(
                    phase_spec.get("execution_type", phase_spec["phase"])
                )
            tiers = _resolve_execution_tiers(phases)
        except ValueError as e:
            helpers_module._finalize_run_failure(
                db, orchestrator_run, parent_task, str(e), claim=run_claim
            )
            helpers_module.add_task_failed_comment(db, parent_task.id, str(e))
            return

        # ── Persist orchestration state ──────────────────────────────────────
        now = datetime.utcnow().isoformat()
        state = OrchestrationStateModel(
            orchestrator_run_id=orchestrator_run.run_id,
            campaign_goal=campaign_goal,
            plan_json=plan_text,
            current_phase=phases[0]["phase"] if phases else None,
            phase_outputs_json=json.dumps({}),
            child_run_ids_json=json.dumps([]),
            status="running",
            created_at=now,
            updated_at=now,
        )
        db.add(state)
        db.commit()
        db.refresh(state)
        guard()

        # ── Create child tasks ───────────────────────────────────────────────
        child_tasks = {}
        for phase_spec in phases:
            child_task = _create_child_task(db, parent_task, phase_spec)
            child_tasks[phase_spec["phase"]] = child_task

        tier_summary = " → ".join(
            "[" + ", ".join(p["phase"] for p in tier) + "]" for tier in tiers
        )
        helpers_module.add_task_comment(
            db,
            parent_task.id,
            f"Campaign plan created. Execution order: {tier_summary}",
            "agent",
        )
        phase_outputs: dict[str, str] = {}
        child_run_ids: list[str] = []

    # Phases that some other phase depends on need a structured handoff block.
    dependents = {dep for p in phases for dep in p.get("depends_on", [])}

    # ── Tier-by-tier dispatch (parallel within tier) ─────────────────────────
    for tier in tiers:
        guard()
        pending_in_tier = [p for p in tier if p["phase"] not in phase_outputs]
        if not pending_in_tier:
            continue
        tier_names = [p["phase"] for p in pending_in_tier]
        state.current_phase = (
            tier_names[0] if len(tier_names) == 1 else f"parallel:{','.join(tier_names)}"
        )
        state.updated_at = datetime.utcnow().isoformat()
        db.commit()

        helpers_module.add_task_comment(
            db,
            parent_task.id,
            f"Starting {'phases' if len(pending_in_tier) > 1 else 'phase'}: "
            f"{', '.join(tier_names)}",
            "agent",
        )

        # Approval gate: if any phase in this tier requires approval and the
        # parent task has not been approved, pause the campaign.
        for phase_spec in pending_in_tier:
            child_exec_type = phase_spec.get("execution_type", phase_spec["phase"])
            child_profile = get_execution_profile(child_exec_type)
            if child_profile.requires_approval and not parent_task.approved_at:
                guard()
                state.status = "awaiting_approval"
                state.current_phase = phase_spec["phase"]
                state.updated_at = datetime.utcnow().isoformat()
                db.commit()
                helpers_module.add_task_comment(
                    db,
                    parent_task.id,
                    f"Campaign paused before phase [{phase_spec['phase']}] — human approval required. "
                    "Set approved_at on this task, then POST /tasks/{id}/execute?resume=true to continue.",
                    "agent",
                )
                return

        # Mark all phases in this tier as in_progress
        for phase_spec in pending_in_tier:
            child_task = child_tasks[phase_spec["phase"]]
            child_task.status = "in_progress"
            child_task.updated_at = datetime.utcnow().isoformat()
        db.commit()

        # Dispatch all phases in this tier concurrently (each with its own session)
        tasks_coros = [
            _dispatch_phase(
                db, phase_spec, child_tasks[phase_spec["phase"]].id,
                orchestrator_run.run_id, phase_outputs, campaign_goal, helpers,
                phase_spec["phase"] in dependents,
                ownership_guard=ownership_guard,
            )
            for phase_spec in pending_in_tier
        ]

        tier_results = await asyncio.gather(*tasks_coros, return_exceptions=True)
        guard()

        # Check for failures (fail-fast)
        failed_phase = None
        failed_error = None
        for phase_spec, result in zip(pending_in_tier, tier_results):
            if isinstance(result, BaseException):
                failed_phase = phase_spec["phase"]
                failed_error = result
                # Mark failed child task
                child_task = child_tasks[failed_phase]
                helpers_module._finalize_run_failure(
                    db,
                    _get_latest_run_for_task(db, AgentRunModel, child_task.id),
                    child_task,
                    str(failed_error),
                )
                helpers_module._refresh_context_view(db, task_id=child_task.id)
                helpers_module.add_task_failed_comment(
                    db, child_task.id, str(failed_error)
                )
            else:
                phase_name, result_text, degraded = result
                phase_outputs[phase_name] = result_text
                child_run_ids.append(
                    _get_latest_run_id_for_task(
                        db, AgentRunModel, child_tasks[phase_name].id
                    )
                )
                helpers_module.add_task_comment(
                    db, parent_task.id, f"Phase [{phase_name}] complete.", "agent"
                )
                if degraded:
                    degraded_map = json.loads(state.handoff_degraded_json or "{}")
                    degraded_map[phase_name] = True
                    state.handoff_degraded_json = json.dumps(degraded_map)
                    helpers_module.add_task_comment(
                        db,
                        parent_task.id,
                        f"Phase [{phase_name}] produced no summary block — "
                        "the next agent will receive a truncated handoff.",
                        "agent",
                    )

        state.phase_outputs_json = json.dumps(phase_outputs)
        state.child_run_ids_json = json.dumps(child_run_ids)
        state.updated_at = datetime.utcnow().isoformat()
        db.commit()

        if failed_phase is not None:
            state.status = "error"
            state.error = f"Phase [{failed_phase}] failed: {failed_error}"
            state.updated_at = datetime.utcnow().isoformat()
            db.commit()

            helpers_module._finalize_run_failure(
                db, orchestrator_run, parent_task,
                f"Campaign stopped at phase [{failed_phase}]: {failed_error}",
                claim=run_claim,
            )
            helpers_module.add_task_failed_comment(
                db, parent_task.id,
                f"Campaign stopped at phase [{failed_phase}]: {failed_error}",
            )
            return

    # ── Finalize campaign ─────────────────────────────────────────────────────
    guard()
    state.status = "completed"
    state.current_phase = None
    state.updated_at = datetime.utcnow().isoformat()
    db.commit()

    summary_lines = ["Campaign completed. Phase results:"]
    for phase_name, output in phase_outputs.items():
        snippet = output[:200].replace("\n", " ")
        summary_lines.append(f"- **{phase_name}**: {snippet}...")
    summary = "\n".join(summary_lines)

    helpers_module._finalize_run_success(
        db, orchestrator_run, parent_task,
        summary,
        raw_execution.session_id if not resume else None,
        ValidationResult(status="passed"),
        claim=run_claim,
    )
    helpers_module.add_task_completed_comment(db, parent_task.id, summary)


def _get_latest_run_for_task(db, AgentRunModel, task_id: int):
    """Return the most recently created AgentRunModel for a task."""
    return (
        db.query(AgentRunModel)
        .filter(AgentRunModel.task_id == task_id)
        .order_by(AgentRunModel.id.desc())
        .first()
    )


def _get_latest_run_id_for_task(db, AgentRunModel, task_id: int) -> str:
    run = _get_latest_run_for_task(db, AgentRunModel, task_id)
    return run.run_id if run else ""


def _create_child_task(db, parent_task, phase_spec: dict):
    """Create a child TaskModel row for a campaign phase."""
    from agent.api.main import TaskModel

    now = datetime.utcnow().isoformat()
    child = TaskModel(
        title=phase_spec.get("task_title", f"Campaign: {phase_spec['phase']}"),
        description=phase_spec.get("task_description"),
        status="pending",
        priority=parent_task.priority,
        execution_type=phase_spec.get("execution_type", phase_spec["phase"]),
        parent_task_id=parent_task.id,
        created_at=now,
        updated_at=now,
    )
    db.add(child)
    db.commit()
    db.refresh(child)
    return child


def _create_child_run(db, child_task, parent_run_id: str, execution_type: str):
    """Create an AgentRunModel for a child phase, linked to the orchestrator run."""
    from agent.api.main import AgentRunModel, RunEventModel

    now = datetime.utcnow().isoformat()
    run = AgentRunModel(
        run_id=str(uuid4()),
        task_id=child_task.id,
        parent_run_id=parent_run_id,
        status="queued",
        execution_type=execution_type,
        trigger_source="orchestrator",
        session_id=None,
        validator_status="pending",
        profile_name=None,
        prompt_text=None,
        prompt_context_json=None,
        result_summary=None,
        error=None,
        source_comment_id=None,
        started_at=now,
        finished_at=None,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    child_task.active_run_id = run.run_id
    child_task.last_run_id = run.run_id
    child_task.updated_at = now
    db.commit()

    db.add(RunEventModel(
        run_id=run.run_id,
        event_type="run_created",
        payload=json.dumps({"trigger_source": "orchestrator", "parent_run_id": parent_run_id}),
        created_at=now,
    ))
    db.commit()
    return run
