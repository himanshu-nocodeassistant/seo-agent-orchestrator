"""Task endpoints.

Extracted from the former agent/api/main.py monolith (see git history).
"""

from fastapi import APIRouter, HTTPException, Query, Request

from agent.api import helpers as helpers_module
from agent.api.helpers import (
    add_task_comment,
    add_task_completed_comment,
    add_task_failed_comment,
    add_task_started_comment,
    _build_runtime_config,
    _create_run,
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
from agent.runtime_profiles import get_execution_profile

router = APIRouter()

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



@router.post("/tasks/{task_id}/execute", response_model=RunResponse)
@limiter.limit(lambda: _rate_limit_value())
async def execute_task(request: Request, task_id: int, resume: bool = False):
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
                task.status = "in_progress"
                task.updated_at = _utcnow_iso()
                db.commit()
                add_task_comment(
                    db, task_id, "🤖 Campaign resuming after approval", "agent"
                )
                try:
                    await _execute_campaign_with_timeout(db, task, run, resume=True)
                except Exception as e:
                    _finalize_run_failure(db, run, task, str(e))
                    _refresh_context_view(db, task_id=task.id)
                    add_task_failed_comment(db, task_id, str(e))
                db.refresh(run)
                return _run_response(run)

            run = _create_run(
                db,
                task,
                "manual_execute",
                task.execution_type or "manual",
                request_id=getattr(request.state, "request_id", None),
            )
            if not getattr(run, "_claim_created", True):
                return _run_response(run)
            add_task_started_comment(db, task_id, task.title)

            try:
                await _execute_campaign_with_timeout(db, task, run)
            except Exception as e:
                _finalize_run_failure(db, run, task, str(e))
                _refresh_context_view(db, task_id=task.id)
                add_task_failed_comment(db, task_id, str(e))
            db.refresh(run)
            return _run_response(run)
        # ── End orchestration branch ──────────────────────────────────────────

        run = _create_run(
            db,
            task,
            "manual_execute",
            task.execution_type or "manual",
            request_id=getattr(request.state, "request_id", None),
        )
        if not getattr(run, "_claim_created", True):
            return _run_response(run)
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
            execution = _normalize_execution_result(
                await helpers_module._run_agent_prompt(
                    workflow_prompt, config, prompt_context
                )
            )
            validation = profile.validator(execution.result_text)
            _finalize_run_success(db, run, task, execution.result_text, execution.session_id, validation)
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
            _finalize_run_failure(db, run, task, str(e))
            _refresh_context_view(db, task_id=task.id)
            add_task_failed_comment(db, task_id, str(e))

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
