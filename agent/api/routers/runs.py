"""Run and orchestration endpoints.

Extracted from the former agent/api/main.py monolith (see git history).
"""

import json

from fastapi import APIRouter, HTTPException

from agent.api import helpers as helpers_module
from agent.api.helpers import (
    add_task_completed_comment,
    add_task_failed_comment,
    add_task_started_comment,
    _build_runtime_config,
    _create_run,
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
    OrchestrationStateModel,
    RunResponse,
    SeoAuditRequest,
    TaskModel,
    get_db_session,
)
from agent.prompts import build_execution_prompt
from agent.runtime_profiles import get_execution_profile

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
async def run_seo_audit(run_id: str, payload: SeoAuditRequest = SeoAuditRequest()):
    """Run an SEO audit through the standard profile pipeline.

    Creates a task + run of type ``seo_audit`` and executes it with the same
    profile machinery as every other task (timeouts, validator, audit log).
    No Bash tool, no agent-driven localhost task creation.
    """
    db = get_db_session()
    try:
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
        db.commit()
        run = _create_run(db, task, "seo_audit", "seo_audit")
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
            execution = _normalize_execution_result(
                await helpers_module._run_agent_prompt(
                    workflow_prompt, config, prompt_context
                )
            )
            validation = profile.validator(execution.result_text)
            _finalize_run_success(
                db, run, task, execution.result_text, execution.session_id, validation
            )
            _refresh_context_view(db, task_id=task.id)
            add_task_completed_comment(db, task.id, execution.result_text)
        except Exception as e:
            _finalize_run_failure(db, run, task, str(e))
            _refresh_context_view(db, task_id=task.id)
            add_task_failed_comment(db, task.id, str(e))

        db.refresh(run)
        return {"message": "Audit complete", "task_id": task.id, "run_id": run.run_id}
    finally:
        db.close()


# ============================================================================
# KANBAN HTML
# ============================================================================
