"""Task endpoints.

Extracted from the former agent/api/main.py monolith (see git history).
"""

import hashlib
import json
import logging
import os
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request

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
    _log_run_event,
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
    WebflowProposalCreate,
    WebflowProposalModel,
    WebflowProposalReject,
    WebflowProposalResponse,
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
from agent.webflow.approvals import Operation, compare_snapshot, requires_approval
from agent.webflow.proposal_parser import extract_webflow_proposal
from agent.webflow.tools import get_client

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
    run.request_id = getattr(request.state, "request_id", None)
    db.commit()
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


def _webflow_proposal_response(proposal: WebflowProposalModel) -> dict:
    """Serialize a stored proposal without shortening its content."""
    return {
        "id": proposal.id,
        "task_id": proposal.task_id,
        "run_id": proposal.run_id,
        "operation": proposal.operation,
        "resource_id": proposal.resource_id,
        "idempotency_key": proposal.idempotency_key,
        "snapshot": json.loads(proposal.snapshot_json),
        "payload": json.loads(proposal.payload_json),
        "status": proposal.status,
        "rejection_reason": proposal.rejection_reason,
        "result": json.loads(proposal.result_json) if proposal.result_json else None,
        "approved_at": proposal.approved_at,
        "approved_by": proposal.approved_by,
        "applied_at": proposal.applied_at,
        "created_at": proposal.created_at,
        "updated_at": proposal.updated_at,
    }


def _proposal_payload(proposal: WebflowProposalModel) -> dict:
    return json.loads(proposal.payload_json)


def _proposal_snapshot(proposal: WebflowProposalModel) -> dict:
    return json.loads(proposal.snapshot_json)


def _webflow_current_snapshot(item: dict) -> dict:
    """Return the complete fetched item for optimistic concurrency checks."""
    return item


def _update_field_data(payload: dict) -> dict:
    """Accept the stored API shape while keeping the approved fields exact."""
    return payload.get("fieldData", payload.get("field_data", payload))


def _log_proposal_event(db, proposal: WebflowProposalModel, event_type: str, details=None) -> None:
    """Log proposal lifecycle metadata without copying the full content."""
    if proposal.run_id:
        _log_run_event(
            db,
            proposal.run_id,
            event_type,
            {"proposal_id": proposal.id, "operation": proposal.operation, **(details or {})},
        )


def _claim_webflow_proposal(db, proposal, actor: str) -> bool:
    """Atomically claim a proposal before any external Webflow call."""
    expected_status = proposal.status
    if expected_status not in {"pending_approval", "partial_failed"}:
        return False
    now = _utcnow_iso()
    values = {"status": "approved", "updated_at": now}
    if expected_status == "pending_approval":
        values.update({"approved_at": now, "approved_by": actor})
    updated = (
        db.query(WebflowProposalModel)
        .filter(
            WebflowProposalModel.id == proposal.id,
            WebflowProposalModel.status == expected_status,
        )
        .update(values, synchronize_session=False)
    )
    if updated != 1:
        db.rollback()
        return False
    db.commit()
    db.refresh(proposal)
    return True

# ============================================================================
# TASK ENDPOINTS
# ============================================================================

@router.get("/tasks", response_model=TaskListResponse)
def list_tasks(limit: int = Query(200, ge=1, le=200)):
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


@router.post(
    "/tasks/{task_id}/webflow-proposals",
    response_model=WebflowProposalResponse,
    status_code=201,
)
def create_webflow_proposal(task_id: int, proposal: WebflowProposalCreate):
    """Create a pending proposal. This endpoint never writes to Webflow."""
    try:
        operation = Operation(proposal.operation.lower())
    except (AttributeError, ValueError):
        raise HTTPException(
            status_code=422,
            detail="operation must be create, update, or publish",
        )

    if not requires_approval(operation):
        raise HTTPException(status_code=422, detail="Webflow reads do not need proposals")
    if operation in {Operation.UPDATE, Operation.PUBLISH} and not proposal.resource_id:
        raise HTTPException(status_code=422, detail="resource_id is required for this operation")

    db = get_db_session()
    try:
        task = db.query(TaskModel).filter(TaskModel.id == task_id).first()
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        if proposal.idempotency_key:
            existing = (
                db.query(WebflowProposalModel)
                .filter(
                    WebflowProposalModel.task_id == task_id,
                    WebflowProposalModel.idempotency_key == proposal.idempotency_key,
                )
                .first()
            )
            if existing:
                return _webflow_proposal_response(existing)

        now = _utcnow_iso()
        stored = WebflowProposalModel(
            task_id=task_id,
            run_id=proposal.run_id,
            operation=operation.value,
            resource_id=proposal.resource_id,
            idempotency_key=proposal.idempotency_key,
            snapshot_json=json.dumps(proposal.snapshot, ensure_ascii=False),
            payload_json=json.dumps(proposal.payload, ensure_ascii=False),
            status="pending_approval",
            created_at=now,
            updated_at=now,
        )
        db.add(stored)
        db.commit()
        db.refresh(stored)
        _log_proposal_event(db, stored, "webflow_proposal_created")
        return _webflow_proposal_response(stored)
    finally:
        db.close()


@router.get(
    "/tasks/{task_id}/webflow-proposals",
    response_model=list[WebflowProposalResponse],
)
def list_webflow_proposals(task_id: int):
    """List complete proposals for a task."""
    db = get_db_session()
    try:
        if not db.query(TaskModel).filter(TaskModel.id == task_id).first():
            raise HTTPException(status_code=404, detail="Task not found")
        proposals = (
            db.query(WebflowProposalModel)
            .filter(WebflowProposalModel.task_id == task_id)
            .order_by(WebflowProposalModel.id.asc())
            .all()
        )
        return [_webflow_proposal_response(item) for item in proposals]
    finally:
        db.close()


@router.post(
    "/tasks/{task_id}/webflow-proposals/{proposal_id}/reject",
    response_model=WebflowProposalResponse,
)
def reject_webflow_proposal(
    task_id: int,
    proposal_id: int,
    decision: WebflowProposalReject | None = None,
):
    """Reject a pending proposal without calling Webflow."""
    db = get_db_session()
    try:
        proposal = (
            db.query(WebflowProposalModel)
            .filter(
                WebflowProposalModel.id == proposal_id,
                WebflowProposalModel.task_id == task_id,
            )
            .first()
        )
        if not proposal:
            raise HTTPException(status_code=404, detail="Webflow proposal not found")
        if proposal.status != "pending_approval":
            raise HTTPException(status_code=409, detail="Proposal is no longer pending approval")

        proposal.status = "rejected"
        proposal.rejection_reason = decision.reason if decision else None
        proposal.updated_at = _utcnow_iso()
        db.commit()
        db.refresh(proposal)
        _log_proposal_event(db, proposal, "webflow_proposal_rejected")
        return _webflow_proposal_response(proposal)
    finally:
        db.close()


@router.post(
    "/tasks/{task_id}/webflow-proposals/{proposal_id}/approve",
    response_model=WebflowProposalResponse,
)
async def approve_webflow_proposal(request: Request, task_id: int, proposal_id: int):
    """Approve and apply exactly one stored proposal."""
    db = get_db_session()
    try:
        proposal = (
            db.query(WebflowProposalModel)
            .filter(
                WebflowProposalModel.id == proposal_id,
                WebflowProposalModel.task_id == task_id,
            )
            .first()
        )
        if not proposal:
            raise HTTPException(status_code=404, detail="Webflow proposal not found")
        task = db.query(TaskModel).filter(TaskModel.id == task_id).first()
        if proposal.status == "applied":
            return _webflow_proposal_response(proposal)
        retrying_batch = proposal.status == "partial_failed"
        if proposal.status not in {"pending_approval", "partial_failed"}:
            raise HTTPException(status_code=409, detail="Proposal is not pending approval")

        operation = Operation(proposal.operation)
        payload = _proposal_payload(proposal)
        batch_items = payload.get("items") if operation is Operation.UPDATE else None
        previous_result = json.loads(proposal.result_json) if proposal.result_json else None
        if retrying_batch and batch_items:
            failed_ids = {
                item["id"]
                for item in (previous_result or {}).get("items", [])
                if item.get("status") == "failed"
            }
            batch_items = [item for item in batch_items if item.get("id") in failed_ids]
        client = get_client()
        if operation in {Operation.UPDATE, Operation.PUBLISH}:
            expected_snapshot = _proposal_snapshot(proposal)
            if batch_items:
                expected_items = expected_snapshot.get("items", {})
                for item in batch_items:
                    item_id = item.get("id")
                    current = _webflow_current_snapshot(await client.get_item(item_id))
                    if compare_snapshot(expected_items.get(item_id, {}), current):
                        proposal.status = "stale"
                        proposal.updated_at = _utcnow_iso()
                        db.commit()
                        _log_proposal_event(db, proposal, "webflow_proposal_stale", {"item_id": item_id})
                        raise HTTPException(
                            status_code=409,
                            detail="Proposal is stale. Create a new proposal.",
                        )
            else:
                current = _webflow_current_snapshot(await client.get_item(proposal.resource_id))
                if compare_snapshot(expected_snapshot, current):
                    proposal.status = "stale"
                    proposal.updated_at = _utcnow_iso()
                    db.commit()
                    _log_proposal_event(db, proposal, "webflow_proposal_stale")
                    raise HTTPException(
                        status_code=409,
                        detail="Proposal is stale. Create a new proposal.",
                    )

        actor = request.headers.get("X-Actor", "operator")
        if not _claim_webflow_proposal(db, proposal, actor):
            db.refresh(proposal)
            if proposal.status == "applied":
                return _webflow_proposal_response(proposal)
            raise HTTPException(status_code=409, detail="Proposal is already being applied")
        if not retrying_batch:
            _log_proposal_event(db, proposal, "webflow_proposal_approved")
        else:
            _log_proposal_event(db, proposal, "webflow_proposal_retry")

        if operation is Operation.UPDATE:
            if batch_items:
                item_results = []
                for item in batch_items:
                    item_id = item.get("id")
                    try:
                        await client.update_item(item_id, _update_field_data(item))
                        item_results.append({"id": item_id, "status": "applied"})
                    except Exception as error:
                        item_results.append({"id": item_id, "status": "failed", "error": str(error)})
                if retrying_batch and previous_result:
                    updated_by_id = {item["id"]: item for item in item_results}
                    merged_items = [
                        updated_by_id.get(item.get("id"), item)
                        for item in previous_result.get("items", [])
                    ]
                    result = {"items": merged_items}
                else:
                    result = {"items": item_results}
            else:
                result = await client.update_item(
                    proposal.resource_id,
                    _update_field_data(payload),
                )
        elif operation is Operation.PUBLISH:
            result = await client.publish_item(proposal.resource_id)
        else:
            field_data = payload.get("fieldData", payload.get("field_data", payload))
            slug = field_data.get("slug") if isinstance(field_data, dict) else None
            if slug:
                existing = await client.list_items(limit=100, offset=0)
                if any(
                    (item.get("fieldData") or item).get("slug") == slug
                    for item in existing.get("items", [])
                ):
                    proposal.status = "failed"
                    proposal.rejection_reason = f"Duplicate Webflow slug: {slug}"
                    proposal.updated_at = _utcnow_iso()
                    db.commit()
                    _log_proposal_event(db, proposal, "webflow_proposal_duplicate")
                    raise HTTPException(
                        status_code=409,
                        detail="Duplicate Webflow slug. Create a new proposal.",
                    )
            result = await client.create_item(
                field_data=field_data,
                is_draft=payload.get("isDraft", payload.get("is_draft", False)),
                is_archived=payload.get("isArchived", payload.get("is_archived", False)),
            )

        proposal.status = (
            "partial_failed"
            if operation is Operation.UPDATE
            and batch_items
            and any(item["status"] == "failed" for item in result["items"])
            else "applied"
        )
        proposal.result_json = json.dumps(result, ensure_ascii=False)
        proposal.applied_at = _utcnow_iso()
        proposal.updated_at = proposal.applied_at
        if task is not None:
            task.status = "completed" if proposal.status == "applied" else "blocked"
            if task.active_run_id == proposal.run_id:
                task.active_run_id = None
            task.last_run_id = proposal.run_id or task.last_run_id
            task.updated_at = proposal.updated_at
        if proposal.run_id:
            approved_run = db.query(AgentRunModel).filter(
                AgentRunModel.run_id == proposal.run_id
            ).first()
            if approved_run is not None:
                approved_run.status = "completed"
                approved_run.validator_status = "passed"
                approved_run.finished_at = proposal.applied_at
        db.commit()
        db.refresh(proposal)
        _log_proposal_event(db, proposal, "webflow_proposal_applied")
        return _webflow_proposal_response(proposal)
    except HTTPException:
        raise
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error))
    except Exception as error:
        if "proposal" in locals() and proposal is not None:
            proposal.status = "failed"
            proposal.rejection_reason = str(error)
            proposal.updated_at = _utcnow_iso()
            db.commit()
            _log_proposal_event(db, proposal, "webflow_proposal_failed")
        raise HTTPException(status_code=502, detail=f"Webflow apply failed: {error}")
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
        latest_task_run = (
            db.query(AgentRunModel)
            .filter(AgentRunModel.task_id == task.id)
            .order_by(AgentRunModel.id.desc())
            .first()
        )

        # ── Orchestration branch ──────────────────────────────────────────────
        if task.execution_type == "orchestrate_seo_campaign":
            if not resume:
                latest_campaign_run = (
                    db.query(AgentRunModel)
                    .filter(
                        AgentRunModel.task_id == task.id,
                        AgentRunModel.execution_type == "orchestrate_seo_campaign",
                    )
                    .order_by(AgentRunModel.id.desc())
                    .first()
                )
                latest_campaign_state = None
                if latest_campaign_run is not None:
                    latest_campaign_state = db.query(OrchestrationStateModel).filter(
                        OrchestrationStateModel.orchestrator_run_id
                        == latest_campaign_run.run_id
                    ).first()
                safe_failed_retry = bool(
                    latest_campaign_run is not None
                    and latest_campaign_run.status == "failed"
                    and latest_campaign_state is not None
                    and latest_campaign_state.status == "error"
                )
                review_gate = bool(
                    latest_campaign_run is not None
                    and latest_campaign_run.status in {"review_required", "needs_review"}
                )
                if (
                    task.status in {"review_required"}
                    or (task.status == "blocked" and not safe_failed_retry)
                    or review_gate
                ):
                    if latest_campaign_run is None:
                        raise HTTPException(
                            status_code=409,
                            detail="Campaign is blocked pending explicit review resolution.",
                        )
                    return _run_response(latest_campaign_run)
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
                if not helpers_module._add_owned_task_comment(
                    db,
                    task_id,
                    run.run_id,
                    "🤖 Campaign resuming saved state"
                    if state.status != "awaiting_approval"
                    else "🤖 Campaign resuming after approval",
                ):
                    db.refresh(run)
                    return _run_response(run)
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

        claim_service, claim, run, profile = _claim_task_run(
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
            resume_session_id = _get_task_session_id(db, task.id)
            prompt_context = _resolve_prompt_context(db, run, task, task_comments, workflow_prompt, profile)
            run.prompt_text = workflow_prompt
            _mark_run_started(db, run, prompt_context, profile.execution_type, resume_session_id)
            config = _build_runtime_config(
                profile, resume_session_id, db=db, run_id=run.run_id
            )
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
            if profile.requires_webflow_approval and os.environ.get("WEBFLOW_ACCESS_TOKEN"):
                proposal_data = extract_webflow_proposal(execution.result_text)
                if proposal_data is None:
                    validation = ValidationResult(
                        status="failed",
                        message="Agent did not return a complete Webflow proposal.",
                    )
                elif validation.status == "passed":
                    now = _utcnow_iso()
                    stored_webflow_proposal = WebflowProposalModel(
                        task_id=task.id,
                        run_id=run.run_id,
                        operation=proposal_data["operation"],
                        resource_id=proposal_data.get("resource_id"),
                        idempotency_key=run.run_id,
                        snapshot_json=json.dumps(proposal_data["snapshot"], ensure_ascii=False),
                        payload_json=json.dumps(proposal_data["payload"], ensure_ascii=False),
                        status="pending_approval",
                        created_at=now,
                        updated_at=now,
                    )
                    db.add(stored_webflow_proposal)
                    db.commit()
            owns_task = _finalize_run_success(
                db, run, task, execution.result_text, execution.session_id, validation
            )
            if not owns_task:
                db.refresh(run)
                return _run_response(run)
            def post_success_side_effects():
                _refresh_context_view(db, task_id=task.id)
                if stored_webflow_proposal is not None:
                    task.status = "blocked"
                    task.updated_at = _utcnow_iso()
                    run.status = "awaiting_approval"
                    run.validator_status = "pending_approval"
                    add_task_comment(
                        db,
                        task_id,
                        "⏳ Webflow proposal ready for approval. No live write was made.",
                        "agent",
                        commit=False,
                    )
                    return
                if webflow_access_missing:
                    run.status = "needs_review"
                    run.recovery_state = "none"

                # Deterministic application-layer change logging (guaranteed, not prompt-dependent)
                if task.execution_type in CMS_CHANGE_FIELD_MAP:
                    try:
                        _write_change_log_entry(task, execution.result_text, task_comments)
                    except Exception as log_err:
                        add_task_comment(
                            db,
                            task_id,
                            f"⚠️ Change log write failed: {log_err}",
                            "agent",
                            commit=False,
                        )

                if validation.status == "passed":
                    add_task_completed_comment(
                        db, task_id, execution.result_text, commit=False
                    )
                else:
                    add_task_comment(
                        db,
                        task_id,
                        f"⚠️ Run completed but failed validation: {validation.message}",
                        "agent",
                        commit=False,
                    )

            if not helpers_module._run_post_finalize_side_effects(
                db, task.id, run.run_id, post_success_side_effects
            ):
                db.refresh(run)
                return _run_response(run)
        except helpers_module.RunOwnershipLost:
            # The heartbeat fenced this worker. Do not finalize or clear state
            # for a run that may now belong to another worker.
            db.refresh(run)
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
