"""Run and orchestration endpoints.

Extracted from the former agent/api/main.py monolith (see git history).
"""

import json
import os
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy.exc import IntegrityError

from agent.api import helpers as helpers_module
from agent.api.helpers import (
    add_task_completed_comment,
    add_task_failed_comment,
    add_task_started_comment,
    _build_runtime_config,
    _finalize_run_failure,
    _finalize_run_success,
    _mark_run_started,
    _normalize_execution_result,
    _refresh_context_view,
    _resolve_prompt_context,
    _run_response,
    _utcnow_iso,
)
from agent.db import (
    AgentRunModel,
    AuditRequestModel,
    ExecuteRequestModel,
    OrchestrationStateModel,
    RunResponse,
    SeoAuditRequest,
    TaskModel,
    get_db_session,
)
from agent.prompts import build_execution_prompt
from agent.runtime_profiles import get_execution_profile
from agent.run_claims import (
    IdempotencyConflict,
    LeaseLost,
    RunClaimConflict,
    RunClaimService,
    lease_heartbeat,
)

router = APIRouter()

@router.get("/runs/{run_id}", response_model=RunResponse)
def get_run(run_id: str):
    db = get_db_session()
    try:
        run = db.query(AgentRunModel).filter(AgentRunModel.run_id == run_id).first()
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        return _run_response(run)
    finally:
        db.close()


@router.get("/orchestrations/{orchestrator_run_id}")
def get_orchestration_state(orchestrator_run_id: str):
    """Get orchestration state and child task details for a campaign run."""
    db = get_db_session()
    try:
        state = db.query(OrchestrationStateModel).filter(
            OrchestrationStateModel.orchestrator_run_id == orchestrator_run_id
        ).first()
        if not state:
            raise HTTPException(status_code=404, detail="Orchestration state not found")

        child_run_ids = json.loads(state.child_run_ids_json or "[]")
        phase_outputs = json.loads(state.phase_outputs_json or "{}")

        child_tasks = []
        for run_id in child_run_ids:
            child_run = db.query(AgentRunModel).filter(AgentRunModel.run_id == run_id).first()
            if child_run and child_run.task_id:
                child_task = db.query(TaskModel).filter(TaskModel.id == child_run.task_id).first()
                if child_task:
                    child_tasks.append({
                        "run_id": run_id,
                        "task_id": child_task.id,
                        "title": child_task.title,
                        "status": child_task.status,
                        "execution_type": child_task.execution_type,
                    })

        return {
            "orchestrator_run_id": state.orchestrator_run_id,
            "campaign_goal": state.campaign_goal,
            "current_phase": state.current_phase,
            "status": state.status,
            "error": state.error,
            "phases_completed": list(phase_outputs.keys()),
            "child_tasks": child_tasks,
            "created_at": state.created_at,
            "updated_at": state.updated_at,
        }
    finally:
        db.close()



@router.post("/runs/{run_id}/seo-audit")
async def run_seo_audit(
    run_id: str,
    request: Request,
    payload: SeoAuditRequest = SeoAuditRequest(),
):
    """Run an SEO audit through the standard profile pipeline.

    Creates a task + run of type ``seo_audit`` and executes it with the same
    profile machinery as every other task (timeouts, validator, audit log).
    No Bash tool, no agent-driven localhost task creation.
    """
    idempotency_key = request.headers.get("Idempotency-Key", "").strip()
    if not idempotency_key:
        if os.environ.get("ALLOW_MISSING_IDEMPOTENCY_KEY", "false").lower() in {
            "1", "true", "yes", "on"
        }:
            idempotency_key = f"compat-{uuid4()}"
        else:
            raise HTTPException(status_code=400, detail="Idempotency-Key header is required")

    # This endpoint creates its task inside the request.  Scope the durable
    # request record by the public audit id, so retries can find the original
    # task before creating another task or calling the agent again.
    request_scope = f"seo-audit:{run_id}"
    fingerprint = f"seo_audit:days={payload.days}"
    db = get_db_session()
    try:
        audit_request = db.query(AuditRequestModel).filter_by(audit_id=run_id).one_or_none()
        if audit_request is not None:
            if (
                audit_request.idempotency_key != idempotency_key
                or audit_request.fingerprint != fingerprint
            ):
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message": "Audit identifier is already bound to another request",
                        "run_id": audit_request.run_id,
                    },
                )
            existing_run_id = audit_request.run_id
            if existing_run_id is None:
                task_row = db.query(TaskModel).filter_by(id=audit_request.task_id).one()
                existing_run_id = task_row.active_run_id or task_row.last_run_id
            existing_run = (
                db.query(AgentRunModel)
                .filter_by(run_id=existing_run_id)
                .one_or_none()
            )
            if existing_run is None:
                raise HTTPException(status_code=409, detail="Audit request is being claimed")
            return {
                "message": (
                    "Audit complete"
                    if existing_run.status in {"completed", "failed", "needs_review"}
                    else "Audit in progress"
                ),
                "task_id": audit_request.task_id,
                "run_id": existing_run.run_id,
            }

        now = _utcnow_iso()
        task = TaskModel(
            title=f"SEO Audit - {run_id}",
            description=f"Run comprehensive SEO audit for the last {payload.days} days",
            status="in_progress",
            priority=0,
            execution_type="seo_audit",
            created_at=now,
            updated_at=now,
        )
        db.add(task)
        db.flush()
        audit_request = AuditRequestModel(
            audit_id=run_id,
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            task_id=task.id,
            run_id=None,
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        db.add(audit_request)
        try:
            # The unique audit row is the database-backed scope claim. Commit
            # it before the task lease service starts its SQLite write lock.
            db.commit()
        except IntegrityError as error:
            db.rollback()
            winner = db.query(AuditRequestModel).filter_by(audit_id=run_id).one()
            if (
                winner.idempotency_key != idempotency_key
                or winner.fingerprint != fingerprint
            ):
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message": "Audit identifier is already bound to another request",
                        "run_id": winner.run_id,
                    },
                ) from error
            winner_task = db.query(TaskModel).filter_by(id=winner.task_id).one()
            winner_run_id = winner.run_id or winner_task.active_run_id or winner_task.last_run_id
            raise HTTPException(
                status_code=409,
                detail={"message": "Audit request is being claimed", "run_id": winner_run_id},
            ) from error

        try:
            claim = RunClaimService(db).acquire(
                task.id,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                request_scope=request_scope,
                execution_type="seo_audit",
                trigger_source="seo_audit",
            )
        except IdempotencyConflict:
            # A concurrent retry won the request-key race after this request
            # created its provisional task.  Remove only that provisional row,
            # then replay the committed winner.
            db.delete(task)
            db.commit()
            winner_request = (
                db.query(ExecuteRequestModel)
                .filter_by(request_scope=request_scope, idempotency_key=idempotency_key)
                .one()
            )
            winner_run = (
                db.query(AgentRunModel).filter_by(run_id=winner_request.run_id).one()
            )
            return {
                "message": (
                    "Audit complete"
                    if winner_run.status in {"completed", "failed", "needs_review"}
                    else "Audit in progress"
                ),
                "task_id": winner_request.task_id,
                "run_id": winner_run.run_id,
            }
        except RunClaimConflict as conflict:
            db.delete(task)
            db.commit()
            raise HTTPException(
                status_code=409,
                detail={"message": "Audit already running", "run_id": conflict.active_run_id},
            ) from conflict

        audit_request.run_id = claim.run_id
        db.commit()

        run = (
            db.query(AgentRunModel).filter_by(run_id=claim.run_id).one()
        )
        run.validator_status = "pending"
        task.last_run_id = run.run_id
        task.status = "in_progress"
        task.updated_at = _utcnow_iso()
        db.commit()
        add_task_started_comment(db, task.id, task.title)

        try:
            workflow_prompt = build_execution_prompt(task, comments=[])
            profile = get_execution_profile("seo_audit")
            prompt_context = _resolve_prompt_context(
                db, run, task, [], workflow_prompt, profile
            )
            run.prompt_text = workflow_prompt
            _mark_run_started(db, run, prompt_context, profile.execution_type, None)
            config = _build_runtime_config(profile, None, db=db, run_id=run.run_id)
            async with lease_heartbeat(claim):
                execution = _normalize_execution_result(
                    await helpers_module._run_agent_prompt(
                        workflow_prompt, config, prompt_context
                    )
                )
            validation = profile.validator(execution.result_text)
            RunClaimService(db).assert_ownership(
                task.id,
                claim.run_id,
                claim.owner_token,
                claim.fence_version,
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
            add_task_completed_comment(db, task.id, execution.result_text)
        except LeaseLost:
            db.rollback()
            current_run = db.query(AgentRunModel).filter_by(run_id=claim.run_id).one()
            return {
                "message": "Audit lease lost",
                "task_id": task.id,
                "run_id": current_run.run_id,
            }
        except Exception as e:
            try:
                RunClaimService(db).assert_ownership(
                    task.id,
                    claim.run_id,
                    claim.owner_token,
                    claim.fence_version,
                )
                _finalize_run_failure(db, run, task, str(e), claim=claim)
            except LeaseLost:
                db.rollback()
                current_run = db.query(AgentRunModel).filter_by(run_id=claim.run_id).one()
                return {
                    "message": "Audit lease lost",
                    "task_id": task.id,
                    "run_id": current_run.run_id,
                }
            except Exception:
                # Preserve the original execution failure.  A lease timeout
                # is handled by the claim service on the next attempt.
                pass
            _refresh_context_view(db, task_id=task.id)
            add_task_failed_comment(db, task.id, str(e))

        db.refresh(run)
        return {"message": "Audit complete", "task_id": task.id, "run_id": run.run_id}
    finally:
        db.close()


# ============================================================================
# KANBAN HTML
# ============================================================================
