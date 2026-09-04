"""Shared runtime helpers for the Kanban API.

Extracted from the former agent/api/main.py monolith (see git history).
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from agent import db as db_module
from agent.config import AgentConfig
from agent.db import (
    AgentRunModel,
    CommentActionModel,
    CommentModel,
    OrchestrationStateModel,
    RunEventModel,
    TaskModel,
    TaskSessionModel,
)
from agent.memory_service import (
    build_short_term_context,
    compose_prompt_context,
    fetch_episodic_context,
    fetch_procedural_context,
    fetch_semantic_context,
    generate_context_view_markdown,
)
from agent.runtime_profiles import WEBFLOW_TOOLS, ValidationResult, get_execution_profile
from agent.run_claims import (
    LeaseLost,
    NeedsReview,
    RunClaimConflict,
    RunClaimService,
    lease_heartbeat,
)
from agent.seo_agent import SEOAgent

logger = logging.getLogger(__name__)
comment_autopilot_lock = asyncio.Lock()

def add_task_comment(db, task_id: int, body: str, author: str = "agent") -> CommentModel:
    """
    Add a comment to a task and increment comment_count.
    
    Args:
        db: Database session
        task_id: ID of the task to comment on
        body: Comment text
        author: Author of the comment ("agent" or "user")
    
    Returns:
        The created CommentModel instance
    """
    task = db.query(TaskModel).filter(TaskModel.id == task_id).first()
    if not task:
        return None
    
    now = _utcnow_iso()
    db_comment = CommentModel(
        task_id=task_id,
        author=author,
        body=body,
        created_at=now,
    )
    db.add(db_comment)
    
    # Increment comment count
    task.comment_count += 1
    
    db.commit()
    db.refresh(db_comment)
    
    return db_comment


def add_task_started_comment(db, task_id: int, task_title: str) -> CommentModel:
    """Add a comment when task execution starts."""
    comment_body = "🤖 Task started by agent"
    return add_task_comment(db, task_id, comment_body, "agent")


def add_task_completed_comment(db, task_id: int, result_summary: str = None) -> CommentModel:
    """Add a comment when task completes."""
    if result_summary:
        # Truncate result for comment
        summary = result_summary[:200] + "..." if len(result_summary) > 200 else result_summary
        comment_body = f"✅ Task completed\n\n{summary}"
    else:
        comment_body = "✅ Task completed"
    return add_task_comment(db, task_id, comment_body, "agent")


def add_task_failed_comment(db, task_id: int, error_message: str) -> CommentModel:
    """Add a comment when task fails."""
    # Truncate error message
    error = error_message[:300] + "..." if len(error_message) > 300 else error_message
    comment_body = f"❌ Task failed\n\nError: {error}"
    return add_task_comment(db, task_id, comment_body, "agent")


def add_google_doc_comment(db, task_id: int, doc_url: str) -> CommentModel:
    """Add a comment with Google Doc link when doc is created."""
    comment_body = f"📄 Google Doc created\n\n{doc_url}"
    return add_task_comment(db, task_id, comment_body, "agent")


def add_subtasks_created_comment(db, task_id: int, subtask_count: int) -> CommentModel:
    """Add a comment when subtasks are created."""
    comment_body = f"📋 {subtask_count} subtask(s) created"
    return add_task_comment(db, task_id, comment_body, "agent")


def is_agent_trigger_comment(author: str, body: str) -> bool:
    """Return True when a comment should trigger autopilot processing."""
    if author != "user":
        return False
    if not body:
        return False
    return body.strip().lower().startswith("@agent")


def extract_agent_comment_instruction(body: str) -> str:
    """Extract actionable instruction from a trigger comment."""
    stripped = (body or "").strip()
    if stripped.lower().startswith("@agent"):
        return stripped[6:].strip()
    return stripped


def build_comment_revision_prompt(task, user_comment_body: str) -> str:
    """Build a follow-up prompt that applies user feedback to prior output."""
    feedback = extract_agent_comment_instruction(user_comment_body) or "Revise the output based on user feedback."
    current_output = task.notes or "(no prior output was saved)"
    task_details = task.description or "(no additional task description)"

    return f"""You are revising an existing task output based on explicit user feedback from a task comment.

Original task title:
{task.title}

Original task details:
{task_details}

Execution type:
{task.execution_type or "manual"}

Current saved output/draft:
{current_output}

User revision request (from @agent comment):
{feedback}

Instructions:
1. Keep the original task intent.
2. Apply the user's requested edits exactly.
3. Return the full revised output, not a summary.
"""


def _autopilot_enabled() -> bool:
    """Return True when background comment autopilot should run."""
    return os.environ.get("COMMENT_AUTOPILOT_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}


def _autopilot_interval_seconds() -> int:
    """Get autopilot polling interval with a safe default."""
    raw = os.environ.get("COMMENT_AUTOPILOT_INTERVAL_SECONDS", "300").strip()
    try:
        value = int(raw)
    except ValueError:
        return 300
    return max(value, 1)


def _agent_execution_timeout_seconds() -> int:
    """Get a bounded timeout for agent execution calls."""
    raw = os.environ.get("AGENT_EXECUTION_TIMEOUT_SECONDS", "900").strip()
    try:
        value = int(raw)
    except ValueError:
        return 900
    return max(value, 1)


def _campaign_timeout_seconds() -> int:
    """Top-level timeout for a full multi-agent campaign (all tiers combined).

    Defaults to 5400s (6 tiers × 900s each). Override with CAMPAIGN_TIMEOUT_SECONDS.
    """
    raw = os.environ.get("CAMPAIGN_TIMEOUT_SECONDS", "5400").strip()
    try:
        value = int(raw)
    except ValueError:
        return 5400
    return max(value, 1)

async def _execute_campaign_with_timeout(
    db, task, run, resume: bool = False, ownership_guard=None, run_claim=None
) -> None:
    """Run the campaign orchestration with a top-level wall-clock timeout.

    Raises RuntimeError if the campaign exceeds CAMPAIGN_TIMEOUT_SECONDS so the
    FastAPI endpoint can fail the run cleanly rather than blocking indefinitely.
    """
    from agent.orchestrator import run_campaign_orchestration

    timeout = _campaign_timeout_seconds()
    try:
        await asyncio.wait_for(
            run_campaign_orchestration(
                db,
                task,
                run,
                resume=resume,
                ownership_guard=ownership_guard,
                run_claim=run_claim,
            ),
            timeout=timeout,
        )
    except asyncio.TimeoutError as e:
        raise RuntimeError(
            f"Campaign timed out after {timeout}s — "
            "increase CAMPAIGN_TIMEOUT_SECONDS or reduce the number of phases."
        ) from e

def _project_root() -> str:
    return str(Path(__file__).resolve().parents[2])


def _serialize_prompt_context(prompt_context) -> str:
    if prompt_context is None:
        return "{}"
    return json.dumps(prompt_context.as_dict(), ensure_ascii=False)

def _task_response(task, db=None) -> dict:
    """Serialize task model into API response shape."""
    resume_available = False
    if task.execution_type == "orchestrate_seo_campaign" and task.last_run_id:
        owns_db = db is None
        if owns_db:
            db = db_module.SessionLocal()
        try:
            state = db.query(OrchestrationStateModel).filter(
                OrchestrationStateModel.orchestrator_run_id == task.last_run_id
            ).first()
            resume_available = bool(state and state.status == "awaiting_approval")
        finally:
            if owns_db:
                db.close()

    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "priority": task.priority,
        "assignee": task.assignee,
        "due_date": task.due_date,
        "execution_type": task.execution_type,
        "requires_approval": task.requires_approval,
        "approved_at": task.approved_at,
        "notes": task.notes,
        "model": task.model,
        "parent_task_id": task.parent_task_id,
        "comment_count": task.comment_count,
        "last_run_id": task.last_run_id,
        "active_run_id": task.active_run_id,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "resume_available": resume_available,
    }


def _run_response(run) -> dict:
    return {
        "run_id": run.run_id,
        "task_id": run.task_id,
        "status": run.status,
        "execution_type": run.execution_type,
        "trigger_source": run.trigger_source,
        "session_id": run.session_id,
        "validator_status": run.validator_status,
        "profile_name": run.profile_name,
        "error": run.error,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
    }

def _log_run_event(db, run_id: str, event_type: str, payload: Optional[dict] = None) -> None:
    db.add(
        RunEventModel(
            run_id=run_id,
            event_type=event_type,
            payload=json.dumps(payload or {}, ensure_ascii=False),
            created_at=_utcnow_iso(),
        )
    )
    db.commit()


def build_post_tool_use_hook(db, run_id: str):
    """
    Return a PostToolUse hook function that writes a RunEventModel row for
    every tool call the agent makes.

    Args:
        db: SQLAlchemy session (caller owns lifecycle).
        run_id: The AgentRunModel.run_id this hook is attached to.

    Returns:
        Async callable matching the SDK HookMatcher signature.
    """
    async def _hook(hook_input, session_id, ctx):
        tool_name = hook_input.get("tool_name", "unknown")
        tool_input = hook_input.get("tool_input", {})
        tool_use_id = hook_input.get("tool_use_id", "")
        _log_run_event(
            db,
            run_id,
            "tool_use",
            {"tool_name": tool_name, "tool_input": tool_input, "tool_use_id": tool_use_id},
        )

    return _hook

def _get_task_session_id(db, task_id: Optional[int]) -> Optional[str]:
    if task_id is None:
        return None
    session = db.query(TaskSessionModel).filter(TaskSessionModel.task_id == task_id).first()
    return session.session_id if session else None


def _upsert_task_session(db, task_id: int, session_id: str, run_id: str) -> None:
    record = db.query(TaskSessionModel).filter(TaskSessionModel.task_id == task_id).first()
    now = _utcnow_iso()
    if record is None:
        record = TaskSessionModel(
            task_id=task_id,
            session_id=session_id,
            last_run_id=run_id,
            updated_at=now,
        )
        db.add(record)
    else:
        record.session_id = session_id
        record.last_run_id = run_id
        record.updated_at = now
    db.commit()

def _create_run(db, task, trigger_source: str, execution_type: Optional[str], source_comment_id: Optional[int] = None):
    run = AgentRunModel(
        run_id=str(uuid4()),
        task_id=task.id if task else None,
        status="queued",
        execution_type=execution_type or "manual",
        trigger_source=trigger_source,
        session_id=None,
        validator_status="pending",
        profile_name=None,
        prompt_text=None,
        prompt_context_json=None,
        result_summary=None,
        error=None,
        source_comment_id=source_comment_id,
        started_at=_utcnow_iso(),
        finished_at=None,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    if task is not None:
        task.active_run_id = run.run_id
        task.last_run_id = run.run_id
        task.updated_at = _utcnow_iso()
        db.commit()
    _log_run_event(db, run.run_id, "run_created", {"trigger_source": trigger_source})
    return run


def _mark_run_started(db, run, prompt_context, profile_name: str, session_id: Optional[str]) -> None:
    run.status = "running"
    run.profile_name = profile_name
    run.prompt_context_json = _serialize_prompt_context(prompt_context)
    run.session_id = session_id
    db.commit()
    _log_run_event(db, run.run_id, "run_started", {"profile_name": profile_name, "session_id": session_id})


def _finalize_run_success(
    db,
    run,
    task,
    result_text: str,
    session_id: Optional[str],
    validation: ValidationResult,
    claim=None,
) -> None:
    now = _utcnow_iso()
    if claim is not None:
        run_status = "completed" if validation.status == "passed" else "needs_review"
        task_status = "completed" if validation.status == "passed" else "blocked"
        RunClaimService(db).finalize(
            claim.task_id,
            claim.run_id,
            claim.owner_token,
            claim.fence_version,
            status=run_status,
            result_summary=result_text,
            error=validation.message if validation.status != "passed" else None,
            validator_status=validation.status,
            session_id=session_id,
            task_status=task_status,
            task_notes=result_text,
        )
        db.refresh(run)
        db.refresh(task)
        if session_id and run.task_id is not None:
            _upsert_task_session(db, run.task_id, session_id, run.run_id)
        _log_run_event(
            db,
            run.run_id,
            "run_completed",
            {"validator_status": validation.status, "message": validation.message},
        )
        return
    run.session_id = session_id
    run.result_summary = result_text
    run.validator_status = validation.status
    run.finished_at = now
    run.status = "completed" if validation.status == "passed" else "needs_review"
    run.error = validation.message if validation.status != "passed" else None

    task.notes = result_text
    task.status = "completed" if validation.status == "passed" else "blocked"
    task.active_run_id = None
    task.last_run_id = run.run_id
    task.updated_at = now
    db.commit()

    if session_id and run.task_id is not None:
        _upsert_task_session(db, run.task_id, session_id, run.run_id)
    _log_run_event(
        db,
        run.run_id,
        "run_completed",
        {"validator_status": validation.status, "message": validation.message},
    )


def _finalize_run_failure(
    db, run, task, error_message: str, status: str = "failed", claim=None
) -> None:
    now = _utcnow_iso()
    if claim is not None:
        RunClaimService(db).finalize(
            claim.task_id,
            claim.run_id,
            claim.owner_token,
            claim.fence_version,
            status=status,
            error=error_message,
            validator_status="failed",
            task_status="blocked",
            task_notes=f"Error: {error_message}",
        )
        db.refresh(run)
        db.refresh(task)
        _log_run_event(
            db, run.run_id, "run_failed", {"error": error_message, "status": status}
        )
        return
    run.status = status
    run.error = error_message
    run.finished_at = now
    run.validator_status = "failed"
    task.status = "blocked"
    task.notes = f"Error: {error_message}"
    task.active_run_id = None
    task.last_run_id = run.run_id
    task.updated_at = now
    db.commit()
    _log_run_event(db, run.run_id, "run_failed", {"error": error_message, "status": status})


def _refresh_context_view(db, task_id: Optional[int] = None) -> None:
    context_path = Path(_project_root()) / "memory" / "seo-context.md"
    context_path.parent.mkdir(parents=True, exist_ok=True)
    context_path.write_text(generate_context_view_markdown(db, task_id=task_id), encoding="utf-8")

async def _run_agent_prompt(prompt: str, config: AgentConfig, prompt_context) -> object:
    """Execute a prompt via SEOAgent using layered memory context."""
    os.environ.pop("CLAUDECODE", None)
    timeout = _agent_execution_timeout_seconds()
    try:
        return await asyncio.wait_for(
            SEOAgent.create_and_run_result(prompt, config, prompt_context=prompt_context),
            timeout=timeout,
        )
    except asyncio.TimeoutError as e:
        raise RuntimeError(f"Agent execution timed out after {timeout}s") from e


def _build_runtime_config(
    profile,
    resume_session_id: Optional[str],
    db=None,
    run_id: Optional[str] = None,
) -> AgentConfig:
    from claude_agent_sdk.types import HookMatcher

    config = AgentConfig.from_env()
    config.cwd = _project_root()
    config.setting_sources = []
    config.system_prompt = (
        "You are an autonomous SEO agent. Execute the given task completely "
        "and autonomously. Use the tools available to you. Report what you did "
        "and the outcome clearly at the end."
    )
    config.allowed_tools = list(profile.allowed_tools)
    config.max_turns = profile.max_turns
    config.max_budget_usd = profile.max_budget_usd
    config.max_thinking_tokens = profile.max_thinking_tokens
    config.resume = resume_session_id if profile.should_resume_session else None

    if db is not None and run_id is not None:
        config.hooks = {
            "PostToolUse": [HookMatcher(hooks=[build_post_tool_use_hook(db, run_id)])]
        }

    return config


def _normalize_execution_result(execution):
    """
    Coerce any SDK result type into an object with .result_text and .session_id.

    Known SDK types (AgentExecutionResult) pass through unchanged. Plain strings
    are wrapped. Unknown types are logged as a warning and wrapped gracefully so
    the caller never crashes on an unexpected SDK payload (#5).

    Scalability note (#5): if the SDK adds new result event types (streaming
    chunks, tool-call receipts), they'll appear here first. Log the full payload
    so debugging is easy. Do not silently discard — unknown ≠ empty.
    """
    if execution is None:
        return type("ExecutionResult", (), {"result_text": "", "session_id": None})()
    if hasattr(execution, "result_text"):
        return execution
    if isinstance(execution, str):
        return type("ExecutionResult", (), {"result_text": execution, "session_id": None})()
    # Unknown type — log and wrap rather than crash
    logger.warning(
        "Unknown SDK result type '%s' — wrapping gracefully. Payload: %r",
        type(execution).__name__,
        execution,
    )
    text = str(execution) if execution else ""
    return type("ExecutionResult", (), {"result_text": text, "session_id": None})()

def _comment_action_stale_seconds() -> int:
    """Return the timeout after which a crashed comment worker may be retried."""
    raw = os.environ.get("COMMENT_ACTION_STALE_SECONDS", "300").strip()
    try:
        value = int(raw)
    except ValueError:
        return 300
    return max(value, 1)


def _parse_action_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return parsed.replace(tzinfo=None)


def _comment_action_is_stale(action: CommentActionModel, now: datetime) -> bool:
    updated_at = _parse_action_timestamp(action.updated_at)
    if action.status != "running" or updated_at is None:
        return False
    return updated_at <= now - timedelta(seconds=_comment_action_stale_seconds())


def _claim_comment_action(db, action: CommentActionModel, now: str) -> bool:
    """Conditionally claim an action so two workers cannot run it together."""
    previous_status = action.status
    previous_attempts = action.attempts
    result = (
        db.query(CommentActionModel)
        .filter(
            CommentActionModel.id == action.id,
            CommentActionModel.status == previous_status,
            CommentActionModel.attempts == previous_attempts,
            CommentActionModel.updated_at == action.updated_at,
        )
        .update(
            {
                CommentActionModel.status: "running",
                CommentActionModel.attempts: CommentActionModel.attempts + 1,
                CommentActionModel.updated_at: now,
            },
            synchronize_session=False,
        )
    )
    if result != 1:
        db.rollback()
        return False
    db.commit()
    db.refresh(action)
    return True


def _mark_claimed_action(
    db, action_id: int, attempt: int, *, status: str, last_error: str
) -> bool:
    """Update an action only if this worker still owns its attempt."""
    updated = (
        db.query(CommentActionModel)
        .filter(
            CommentActionModel.id == action_id,
            CommentActionModel.status == "running",
            CommentActionModel.attempts == attempt,
        )
        .update(
            {
                CommentActionModel.status: status,
                CommentActionModel.last_error: last_error,
                CommentActionModel.updated_at: _utcnow_iso(),
            },
            synchronize_session=False,
        )
    )
    db.commit()
    return updated == 1


def _find_comment_action_candidate(db, now: datetime) -> Optional[CommentActionModel]:
    """Return the oldest pending, retryable, or stale action."""
    actions = (
        db.query(CommentActionModel)
        .filter(CommentActionModel.attempts <= CommentActionModel.max_attempts)
        .order_by(CommentActionModel.id.asc())
        .all()
    )
    for action in actions:
        if action.status in {"pending", "failed"} and action.attempts < action.max_attempts:
            return action
        if action.status == "running" and _comment_action_is_stale(action, now):
            return action
    return None


def _acquire_next_comment_action(db) -> Optional[CommentActionModel]:
    """Find and atomically claim the next comment action.

    The conditional update is the correctness boundary.  The legacy process
    lock may still exist for compatibility, but it is not needed when workers
    use separate processes or database sessions.
    """
    now = _utcnow_iso()
    now_dt = _parse_action_timestamp(now) or datetime.utcnow()

    # Retry if another worker won the conditional update while this worker
    # was reading candidates.  A bounded loop avoids spinning on a hot queue.
    for _ in range(20):
        action = _find_comment_action_candidate(db, now_dt)
        if action is None:
            comments = db.query(CommentModel).order_by(CommentModel.id.asc()).all()
            for comment in comments:
                if not is_agent_trigger_comment(comment.author, comment.body):
                    continue
                task = db.query(TaskModel).filter(TaskModel.id == comment.task_id).first()
                if task and task.updated_at and task.updated_at > comment.created_at:
                    continue
                if db.query(CommentActionModel).filter_by(comment_id=comment.id).first():
                    continue
                action = CommentActionModel(
                    task_id=comment.task_id,
                    comment_id=comment.id,
                    status="pending",
                    attempts=0,
                    max_attempts=2,
                    created_at=now,
                    updated_at=now,
                )
                db.add(action)
                try:
                    db.commit()
                    db.refresh(action)
                    break
                except IntegrityError:
                    db.rollback()
                    action = None
            if action is None:
                return None

        # A stale action that has used all attempts cannot make progress.
        # Close it explicitly instead of leaving it permanently running.
        if action.status == "running" and action.attempts >= action.max_attempts:
            if _claim_comment_action(db, action, now):
                action.status = "retry_exhausted"
                action.last_error = "Stale comment action exhausted its retries."
                action.updated_at = now
                db.commit()
            continue

        if _claim_comment_action(db, action, now):
            return action
    return None


async def process_one_comment_action() -> dict:
    """Process exactly one pending trigger comment action."""
    # Do not use the process-local lock as a correctness mechanism.  The
    # conditional comment-action claim and the durable task lease protect
    # workers in different processes.
    db = db_module.get_db_session()
    try:
        action = _acquire_next_comment_action(db)
        if action is None:
            return {"processed": False, "reason": "no_pending_trigger_comments"}
        action_attempt = action.attempts

        task = db.query(TaskModel).filter(TaskModel.id == action.task_id).first()
        comment = db.query(CommentModel).filter(CommentModel.id == action.comment_id).first()
        if not task or not comment:
            action.status = "retry_exhausted"
            action.last_error = "Task or comment no longer exists."
            action.updated_at = _utcnow_iso()
            db.commit()
            return {
                "processed": True,
                "task_id": action.task_id,
                "comment_id": action.comment_id,
                "status": action.status,
                "attempts": action.attempts,
            }

        profile = get_execution_profile(task.execution_type)
        claim_service = RunClaimService(db)
        attempt_key = f"comment-autopilot:{comment.id}:attempt:{action.attempts}"
        fingerprint = f"comment-autopilot:task:{task.id}:comment:{comment.id}"
        try:
            claim = claim_service.acquire(
                task.id,
                idempotency_key=attempt_key,
                fingerprint=fingerprint,
                request_scope=f"comment-autopilot:task:{task.id}",
                execution_type=task.execution_type or "manual",
                trigger_source="comment_autopilot",
                write_capable=bool(
                    set(profile.allowed_tools) & (set(WEBFLOW_TOOLS) | {"Write", "Edit"})
                ),
            )
        except (RunClaimConflict, NeedsReview) as error:
            # The task may be running from another trigger.  Keep this action
            # retryable, so it can run after that lease is released.
            action.last_error = str(error)
            action.status = "retry_exhausted" if action.attempts >= action.max_attempts else "failed"
            action.updated_at = _utcnow_iso()
            db.commit()
            return {
                "processed": True,
                "task_id": task.id,
                "comment_id": comment.id,
                "status": action.status,
                "attempts": action.attempts,
                "max_attempts": action.max_attempts,
            }

        run = db.query(AgentRunModel).filter(AgentRunModel.run_id == claim.run_id).one()
        action.run_id = run.run_id
        task.status = "in_progress"
        task.updated_at = _utcnow_iso()
        db.commit()
        add_task_comment(db, task.id, f"🤖 Started revision from comment #{comment.id}", "agent")

        workflow_prompt = build_comment_revision_prompt(task, comment.body)
        try:
            resume_session_id = _get_task_session_id(db, task.id)
            prompt_context = _resolve_prompt_context(db, run, task, [comment], workflow_prompt, profile)
            run.prompt_text = workflow_prompt
            _mark_run_started(db, run, prompt_context, profile.execution_type, resume_session_id)
            config = _build_runtime_config(profile, resume_session_id)
            async with lease_heartbeat(claim):
                execution = _normalize_execution_result(
                    await _run_agent_prompt(workflow_prompt, config, prompt_context)
                )
            validation = ValidationResult(
                status="passed" if execution.result_text and execution.result_text.strip() else "failed",
                message=None if execution.result_text and execution.result_text.strip() else "Revision output was empty.",
            )
            # Fence final writes if another worker has reclaimed an expired
            # lease while this worker was waiting for the model.
            claim_service.assert_ownership(
                task.id, claim.run_id, claim.owner_token, claim.fence_version
            )
            _finalize_run_success(
                db,
                run,
                task,
                execution.result_text,
                execution.session_id,
                validation,
                claim=claim,
            )
            _refresh_context_view(db, task_id=task.id)
            add_task_comment(
                db,
                task.id,
                f"🤖 Revision completed for comment #{comment.id}\n\n{execution.result_text}",
                "agent",
            )

            action.status = "succeeded" if validation.status == "passed" else "needs_review"
            action.acted_at = _utcnow_iso()
            action.last_error = validation.message
        except LeaseLost as error:
            # An expired worker must not publish a result or retry side effect.
            db.rollback()
            _mark_claimed_action(
                db,
                action.id,
                action_attempt,
                status="needs_review",
                last_error=str(error),
            )
            action = db.query(CommentActionModel).filter_by(id=action.id).one()
            return {
                "processed": True,
                "task_id": task.id,
                "comment_id": comment.id,
                "status": action.status,
                "attempts": action.attempts,
                "max_attempts": action.max_attempts,
            }
        except Exception as error:
            try:
                claim_service.assert_ownership(
                    task.id, claim.run_id, claim.owner_token, claim.fence_version
                )
                _finalize_run_failure(db, run, task, str(error), claim=claim)
                _refresh_context_view(db, task_id=task.id)
                add_task_failed_comment(db, task.id, f"Comment #{comment.id}: {str(error)}")
                action.last_error = str(error)
                action.status = (
                    "retry_exhausted"
                    if action.attempts >= action.max_attempts
                    else "failed"
                )
            except LeaseLost as lease_error:
                db.rollback()
                _mark_claimed_action(
                    db,
                    action.id,
                    action_attempt,
                    status="needs_review",
                    last_error=str(lease_error),
                )
                action = db.query(CommentActionModel).filter_by(id=action.id).one()
                return {
                    "processed": True,
                    "task_id": task.id,
                    "comment_id": comment.id,
                    "status": action.status,
                    "attempts": action.attempts,
                    "max_attempts": action.max_attempts,
                }

        action.updated_at = _utcnow_iso()
        db.commit()
        return {
            "processed": True,
            "task_id": task.id,
            "comment_id": comment.id,
            "status": action.status,
            "attempts": action.attempts,
            "max_attempts": action.max_attempts,
        }
    finally:
        db.close()



def _resolve_prompt_context(db, run, task, comments, workflow_prompt, profile):
    short_term = build_short_term_context(run, task, comments)
    episodic = fetch_episodic_context(db, task.id if task else None, run.execution_type or "manual", profile.episodic_limit)
    semantic = fetch_semantic_context(
        task, run.execution_type or "manual", _project_root(),
        profile.semantic_char_limit, profile=profile,
    )
    procedural = fetch_procedural_context(run.execution_type or "manual", workflow_prompt, profile)
    return compose_prompt_context(short_term, episodic, semantic, procedural)


def _utcnow_iso() -> str:
    """Naive UTC ISO timestamp (matches legacy datetime.utcnow output)."""
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
