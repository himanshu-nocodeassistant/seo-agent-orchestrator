"""Task endpoints.

Extracted from the former agent/api/main.py monolith (see git history).
"""

import hashlib
import json
import logging
import os
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request

from agent.api import helpers as helpers_module
from agent.api.helpers import (
    add_task_comment,
    add_task_completed_comment,
    add_task_failed_comment,
    add_task_started_comment,
    _build_runtime_config,
    _execute_campaign_with_timeout,
    _finalize_run_failure,
    _finalize_run_success,
    _get_task_session_id,
    _mark_run_started,
    _normalize_execution_result,
    _refresh_context_view,
    _resolve_prompt_context,
    _run_response,
    _task_response,
    _utcnow_iso,
)
from agent.api.rate_limit import _rate_limit_value, limiter
from agent.db import (
    AgentRunModel,
    CommentModel,
    ExecuteRequestModel,
    OrchestrationStateModel,
    RunResponse,
    TaskCreate,
    TaskListResponse,
    TaskMemoryResponse,
    TaskModel,
    TaskResponse,
    TaskUpdate,
    get_db_session,
)
from agent.feedback_loop import CMS_CHANGE_FIELD_MAP, _write_change_log_entry
from agent.prompts import build_execution_prompt
from agent.run_claims import (
    IdempotencyConflict,
    LeaseLost,
    NeedsReview,
    RunClaimConflict,
    RunClaimService,
    lease_heartbeat,
)
from agent.runtime_profiles import WEBFLOW_TOOLS, get_execution_profile

router = APIRouter()
logger = logging.getLogger(__name__)


def _request_idempotency_key(request: Request) -> str:
    """Read the public request key, with an explicit test-only escape hatch."""
    key = request.headers.get("Idempotency-Key", "").strip()
    if key:
        return key
    # Existing local callers can opt into the old behaviour while migrating.
    # Production remains strict: a missing key is a client error by default.
    if os.environ.get("ALLOW_MISSING_IDEMPOTENCY_KEY", "false").lower() in {
        "1", "true", "yes", "on"
    }:
        return f"compat-{uuid4()}"
    raise HTTPException(status_code=422, detail="Idempotency-Key header is required")


def _request_fingerprint(*, task_id: int, execution_type: str | None, resume: bool,
                         acknowledge_stale: bool) -> str:
    payload = {
        "task_id": task_id,
        "execution_type": execution_type or "manual",
        "resume": resume,
        "acknowledge_stale": acknowledge_stale,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _is_write_capable(profile) -> bool:
    """Conservatively identify runs whose stale result may have side effects."""
    return bool(profile and set(profile.allowed_tools) & (set(WEBFLOW_TOOLS) | {"Write", "Edit"}))


def _claim_http_error(error: Exception) -> HTTPException:
    if isinstance(error, IdempotencyConflict):
        return HTTPException(
            status_code=409,
            detail={"code": "idempotency_conflict", "message": str(error)},
        )
    if isinstance(error, NeedsReview):
        return HTTPException(
            status_code=409,
            detail={
                "code": "needs_review",
                "active_run_id": error.active_run_id,
                "status": error.status,
                "message": str(error),
            },
        )
    if isinstance(error, RunClaimConflict):
        return HTTPException(
            status_code=409,
            detail={
                "code": "run_in_progress",
                "active_run_id": error.active_run_id,
                "status": error.status,
                "message": str(error),
            },
        )
    return HTTPException(status_code=400, detail=str(error))


def _claim_task_run(
    db,
    task,
    *,
    request: Request,
    resume: bool,
    acknowledge_stale: bool,
):
    """Claim a task before producing comments, runs, or agent work."""
    key = _request_idempotency_key(request)
    try:
        profile = get_execution_profile(task.execution_type)
    except ValueError:
        # Preserve the existing API behaviour: an unknown type gets a failed
        # run record, rather than failing before a run can be audited.
        profile = None
    fingerprint = _request_fingerprint(
        task_id=task.id,
        execution_type=task.execution_type,
        resume=resume,
        acknowledge_stale=acknowledge_stale,
    )
    service = RunClaimService(db)
    try:
        claim = service.acquire(
            task.id,
            idempotency_key=key,
            fingerprint=fingerprint,
            execution_type=task.execution_type or "manual",
            trigger_source="manual_execute",
            write_capable=_is_write_capable(profile),
            acknowledge_stale=acknowledge_stale,
        )
    except (IdempotencyConflict, NeedsReview, RunClaimConflict, ValueError) as error:
        raise _claim_http_error(error) from error
    run = db.query(AgentRunModel).filter(AgentRunModel.run_id == claim.run_id).one()
    return service, claim, run, profile


def _campaign_ownership_guard(claim):
    """Build a guard that checks the parent lease with an isolated session."""
    def _guard():
        guard_db = get_db_session()
        try:
            RunClaimService(guard_db).assert_ownership(
                claim.task_id,
                claim.run_id,
                claim.owner_token,
                claim.fence_version,
            )
        finally:
            guard_db.close()

    return _guard

# ============================================================================
# TASK ENDPOINTS
# ============================================================================

@router.get("/tasks", response_model=TaskListResponse)
def list_tasks(limit: int = 200):
    """List all tasks with counts."""
    db = get_db_session()
    try:
        tasks = (
            db.query(TaskModel)
            .order_by(TaskModel.updated_at.desc())
            .limit(limit)
            .all()
        )
        
        # Convert to response format
        task_list = [_task_response(task) for task in tasks]
        
        # Calculate counts
        pending_count = sum(1 for t in tasks if t.status == "pending")
        in_progress_count = sum(1 for t in tasks if t.status == "in_progress")
        completed_count = sum(1 for t in tasks if t.status == "completed")
        blocked_count = sum(1 for t in tasks if t.status == "blocked")
        
        return {
            "tasks": task_list,
            "total": len(tasks),
            "pending_count": pending_count,
            "in_progress_count": in_progress_count,
            "completed_count": completed_count,
            "blocked_count": blocked_count,
        }
    finally:
        db.close()


@router.post("/tasks", response_model=TaskResponse)
def create_task(task: TaskCreate):
    """Create a new task."""
    db = get_db_session()
    try:
        now = _utcnow_iso()
        db_task = TaskModel(
            title=task.title,
            description=task.description,
            status=task.status,
            priority=task.priority,
            assignee=task.assignee,
            due_date=task.due_date,
            execution_type=task.execution_type,
            requires_approval=task.requires_approval,
            created_at=now,
            updated_at=now,
        )
        db.add(db_task)
        db.commit()
        db.refresh(db_task)
        return _task_response(db_task)
    finally:
        db.close()


@router.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(task_id: int):
    """Get a single task by ID."""
    db = get_db_session()
    try:
        task = db.query(TaskModel).filter(TaskModel.id == task_id).first()
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        
        return _task_response(task)
    finally:
        db.close()


@router.patch("/tasks/{task_id}", response_model=TaskResponse)
def update_task(task_id: int, task: TaskUpdate):
    """Update a task."""
    db = get_db_session()
    try:
        db_task = db.query(TaskModel).filter(TaskModel.id == task_id).first()
        if not db_task:
            raise HTTPException(status_code=404, detail="Task not found")
        
        # Update fields
        update_data = task.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(db_task, key, value)
        
        db_task.updated_at = _utcnow_iso()
        db.commit()
        db.refresh(db_task)
        
        return _task_response(db_task)
    finally:
        db.close()


@router.delete("/tasks/{task_id}")
def delete_task(task_id: int):
    """Delete a task."""
    db = get_db_session()
    try:
        task = db.query(TaskModel).filter(TaskModel.id == task_id).first()
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        
        db.delete(task)
        db.commit()
        
        return {"message": "Task deleted"}
    finally:
        db.close()



@router.post("/tasks/{task_id}/execute", response_model=RunResponse)
@limiter.limit(lambda: _rate_limit_value())
async def execute_task(
    request: Request,
    task_id: int,
    resume: bool = False,
    acknowledge_stale: bool = False,
):
    """Execute a task via SEOAgent and return the run record."""
    db = get_db_session()
    try:
        task = db.query(TaskModel).filter(TaskModel.id == task_id).first()
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        # ── Orchestration branch ──────────────────────────────────────────────
        if task.execution_type == "orchestrate_seo_campaign":
            if resume:
                # Resume a campaign paused at the approval gate: reuse the
                # existing orchestrator run and its saved orchestration state.
                run = (
                    db.query(AgentRunModel)
                    .filter(
                        AgentRunModel.task_id == task.id,
                        AgentRunModel.execution_type == "orchestrate_seo_campaign",
                    )
                    .order_by(AgentRunModel.id.desc())
                    .first()
                )
                if run is None:
                    raise HTTPException(
                        status_code=400,
                        detail="No existing campaign run to resume.",
                    )
                key = _request_idempotency_key(request)
                fingerprint = _request_fingerprint(
                    task_id=task.id,
                    execution_type=task.execution_type,
                    resume=True,
                    acknowledge_stale=acknowledge_stale,
                )
                claim_service = RunClaimService(db)
                # A retry must replay even after the campaign has finished.
                # Check the durable request first, before validating the
                # current approval state.
                prior_request = db.query(ExecuteRequestModel).filter_by(
                    request_scope=f"task:{task.id}", idempotency_key=key
                ).one_or_none()
                if prior_request is None:
                    state = db.query(OrchestrationStateModel).filter(
                        OrchestrationStateModel.orchestrator_run_id == run.run_id
                    ).first()
                    if state is None or state.status != "awaiting_approval":
                        raise HTTPException(
                            status_code=400,
                            detail="Campaign is not paused awaiting approval.",
                        )
                    if not task.approved_at:
                        raise HTTPException(
                            status_code=400,
                            detail="Task not approved yet — set approved_at first.",
                        )
                try:
                    claim = claim_service.acquire_resume(
                        task.id,
                        run.run_id,
                        idempotency_key=key,
                        fingerprint=fingerprint,
                    )
                except (IdempotencyConflict, NeedsReview, RunClaimConflict, ValueError) as error:
                    raise _claim_http_error(error) from error

                run = db.query(AgentRunModel).filter(AgentRunModel.run_id == claim.run_id).one()
                if claim.replayed:
                    db.refresh(run)
                    return _run_response(run)
                task.status = "in_progress"
                task.updated_at = _utcnow_iso()
                db.commit()
                add_task_comment(
                    db, task_id, "🤖 Campaign resuming after approval", "agent"
                )
                try:
                    async with lease_heartbeat(claim):
                        await _execute_campaign_with_timeout(
                            db,
                            task,
                            run,
                            resume=True,
                            ownership_guard=_campaign_ownership_guard(claim),
                            run_claim=claim,
                        )
                except Exception as e:
                    try:
                        claim_service.assert_ownership(
                            claim.task_id, claim.run_id,
                            claim.owner_token, claim.fence_version,
                        )
                        _finalize_run_failure(db, run, task, str(e), claim=claim)
                        _refresh_context_view(db, task_id=task.id)
                        add_task_failed_comment(db, task_id, str(e))
                    except LeaseLost:
                        logger.warning("Resume worker lost lease for run %s", run.run_id)
                else:
                    state = db.query(OrchestrationStateModel).filter(
                        OrchestrationStateModel.orchestrator_run_id == run.run_id
                    ).first()
                    try:
                        if state is not None and state.status == "awaiting_approval":
                            claim_service.pause(
                                claim.task_id, claim.run_id,
                                claim.owner_token, claim.fence_version,
                            )
                        else:
                            claim_service.release(
                                claim.task_id, claim.run_id,
                                claim.owner_token, claim.fence_version,
                            )
                    except LeaseLost:
                        logger.warning("Resume worker lost lease while closing run %s", run.run_id)
                db.refresh(run)
                return _run_response(run)

            claim_service, claim, run, _ = _claim_task_run(
                db,
                task,
                request=request,
                resume=False,
                acknowledge_stale=acknowledge_stale,
            )
            if claim.replayed:
                db.refresh(run)
                return _run_response(run)
            task.status = "in_progress"
            task.updated_at = _utcnow_iso()
            db.commit()
            add_task_started_comment(db, task_id, task.title)

            try:
                async with lease_heartbeat(claim):
                    await _execute_campaign_with_timeout(
                        db,
                        task,
                        run,
                        ownership_guard=_campaign_ownership_guard(claim),
                        run_claim=claim,
                    )
            except Exception as e:
                try:
                    claim_service.assert_ownership(
                        claim.task_id, claim.run_id,
                        claim.owner_token, claim.fence_version,
                    )
                    _finalize_run_failure(db, run, task, str(e), claim=claim)
                    _refresh_context_view(db, task_id=task.id)
                    add_task_failed_comment(db, task_id, str(e))
                except LeaseLost:
                    logger.warning("Campaign worker lost lease for run %s", run.run_id)
            else:
                state = db.query(OrchestrationStateModel).filter(
                    OrchestrationStateModel.orchestrator_run_id == run.run_id
                ).first()
                try:
                    if state is not None and state.status == "awaiting_approval":
                        claim_service.pause(
                            claim.task_id, claim.run_id,
                            claim.owner_token, claim.fence_version,
                        )
                    else:
                        claim_service.release(
                            claim.task_id, claim.run_id,
                            claim.owner_token, claim.fence_version,
                        )
                except LeaseLost:
                    logger.warning("Campaign worker lost lease while closing run %s", run.run_id)
            db.refresh(run)
            return _run_response(run)
        # ── End orchestration branch ──────────────────────────────────────────

        claim_service, claim, run, _ = _claim_task_run(
            db,
            task,
            request=request,
            resume=False,
            acknowledge_stale=acknowledge_stale,
        )
        if claim.replayed:
            db.refresh(run)
            return _run_response(run)
        task.status = "in_progress"
        task.updated_at = _utcnow_iso()
        db.commit()
        add_task_started_comment(db, task_id, task.title)

        try:
            task_comments = db.query(CommentModel).filter(CommentModel.task_id == task_id).order_by(CommentModel.created_at).all()
            workflow_prompt = build_execution_prompt(task, comments=task_comments)
            profile = get_execution_profile(task.execution_type)
            resume_session_id = _get_task_session_id(db, task.id)
            prompt_context = _resolve_prompt_context(db, run, task, task_comments, workflow_prompt, profile)
            run.prompt_text = workflow_prompt
            _mark_run_started(db, run, prompt_context, profile.execution_type, resume_session_id)
            config = _build_runtime_config(profile, resume_session_id)
            async with lease_heartbeat(claim):
                execution = _normalize_execution_result(
                    await helpers_module._run_agent_prompt(
                        workflow_prompt, config, prompt_context
                    )
                )
            validation = profile.validator(execution.result_text)
            claim_service.assert_ownership(
                claim.task_id, claim.run_id,
                claim.owner_token, claim.fence_version,
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

            # Deterministic application-layer change logging (guaranteed, not prompt-dependent)
            if task.execution_type in CMS_CHANGE_FIELD_MAP:
                try:
                    _write_change_log_entry(task, execution.result_text, task_comments)
                except Exception as log_err:
                    add_task_comment(db, task_id, f"⚠️ Change log write failed: {log_err}", "agent")

            if validation.status == "passed":
                add_task_completed_comment(db, task_id, execution.result_text)
            else:
                add_task_comment(
                    db,
                    task_id,
                    f"⚠️ Run completed but failed validation: {validation.message}",
                    "agent",
                )
        except Exception as e:
            try:
                claim_service.assert_ownership(
                    claim.task_id, claim.run_id,
                    claim.owner_token, claim.fence_version,
                )
                _finalize_run_failure(db, run, task, str(e), claim=claim)
                _refresh_context_view(db, task_id=task.id)
                add_task_failed_comment(db, task_id, str(e))
            except LeaseLost:
                logger.warning("Worker lost lease for run %s", run.run_id)
        db.refresh(run)
        return _run_response(run)
    finally:
        db.close()


@router.get("/tasks/{task_id}/memory", response_model=TaskMemoryResponse)
def get_task_memory(task_id: int):
    db = get_db_session()
    try:
        task = db.query(TaskModel).filter(TaskModel.id == task_id).first()
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        run = None
        if task.last_run_id:
            run = db.query(AgentRunModel).filter(AgentRunModel.run_id == task.last_run_id).first()
        if run is None:
            run = AgentRunModel(
                run_id="preview",
                task_id=task.id,
                execution_type=task.execution_type or "manual",
                trigger_source="memory_debug",
                session_id=_get_task_session_id(db, task.id),
                validator_status="preview",
            )
        comments = db.query(CommentModel).filter(CommentModel.task_id == task.id).order_by(CommentModel.created_at).all()
        workflow_prompt = build_execution_prompt(task, comments=comments)
        profile = get_execution_profile(task.execution_type)
        prompt_context = _resolve_prompt_context(db, run, task, comments, workflow_prompt, profile)
        return {
            "task_id": task.id,
            "run_id": getattr(run, "run_id", None),
            "execution_type": task.execution_type,
            "memory": prompt_context.as_dict(),
        }
    finally:
        db.close()


# ============================================================================
# COMMENT ENDPOINTS
# ============================================================================
