"""
FastAPI server for Kanban UI.

App assembly layer. Routers live in ``agent/api/routers/``, shared helpers in
``agent/api/helpers.py``, models/session/schemas in ``agent/db.py``, workflow
prompts in ``agent/prompts.py``, and feedback-loop persistence in
``agent/feedback_loop.py``. Every previously public symbol is re-exported from
this module for backwards compatibility.
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text

from agent import db as db_module
from agent.api.helpers import (
    _autopilot_enabled,
    _autopilot_interval_seconds,
    comment_autopilot_lock,
    process_one_comment_action,
)
from agent.api.rate_limit import _rate_limit_value, limiter
from agent.api.routers import automation, comments, runs, tasks
from agent.db import _ensure_orchestration_handoff_column

logger = logging.getLogger(__name__)


# ============================================================================
# EXECUTION TYPE TAXONOMY
# ============================================================================

# Execution types that support autonomous agent execution via the Execute button
EXECUTABLE_TYPES = {
    "research", "rewrite_title", "rewrite_meta_desc", "rewrite_h1",
    "update_schema", "blog_write", "rewrite_blog_content",
    "webflow_publish", "internal_links", "alt_text", "seo_impact_review",
    "orchestrate_seo_campaign", "seo_audit",
    # Scalability note (#6): child campaign types intentionally expose only
    # the tools their profile needs (campaign_researcher = BASE+GSC read-only;
    # campaign_publisher = BASE+WEBFLOW write). Never grant all tools to child
    # agents — blast radius grows with each new profile. If a new child type
    # needs Webflow, add it to runtime_profiles.py with explicit WEBFLOW_TOOLS,
    # not by expanding EXECUTABLE_TYPES here.
    "campaign_researcher", "campaign_content_writer", "campaign_publisher",
    "campaign_analyst",
}

# Execution types that require Webflow CMS API access
WEBFLOW_DEPENDENT_TYPES = {
    "rewrite_title", "rewrite_meta_desc", "rewrite_h1",
    "blog_write", "rewrite_blog_content", "webflow_publish", "internal_links",
}


# ============================================================================
# FASTAPI APP
# ============================================================================


def _allowed_origins() -> list[str]:
    """CORS origins from ALLOWED_ORIGINS (comma-separated), localhost default."""
    raw = os.environ.get(
        "ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000"
    )
    return [o.strip() for o in raw.split(",") if o.strip()]


async def _comment_autopilot_loop():
    """Background loop that periodically processes one trigger comment."""
    interval = _autopilot_interval_seconds()
    while True:
        await process_one_comment_action()
        await asyncio.sleep(interval)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Start/stop the comment autopilot and apply one-off DB migrations."""
    _ensure_orchestration_handoff_column()
    task = None
    if _autopilot_enabled():
        task = asyncio.create_task(_comment_autopilot_loop())
        app.state.comment_autopilot_task = task
    yield
    if task is not None:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="SEO Bot Kanban API", lifespan=_lifespan)
app.state.comment_autopilot_lock = comment_autopilot_lock
app.state.comment_autopilot_task = None

# Rate limiting (slowapi) — applied only to endpoints that start paid runs.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Add CORS middleware — explicit origins, never "*" + credentials.
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _api_token_check(request: Request, call_next):
    """Optional bearer-token gate. Enabled only when API_TOKEN is set."""
    request.state.request_id = request.headers.get("X-Request-ID") or str(uuid4())
    token = os.environ.get("API_TOKEN")
    if token:
        expected = f"Bearer {token}"
        if request.headers.get("Authorization") != expected:
            response = JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing API token"},
            )
            response.headers["X-Request-ID"] = request.state.request_id
            return response
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


# ============================================================================
# HEALTH + KANBAN
# ============================================================================


@app.get("/health")
def health_check():
    """Fast dependency health check with safe, stable output."""
    database_status = "ok"
    db = None
    try:
        db = db_module.get_db_session()
        db.execute(text("SELECT 1"))
    except Exception:
        database_status = "unavailable"
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass

    if not _autopilot_enabled():
        worker_status = "disabled"
    else:
        worker = getattr(app.state, "comment_autopilot_task", None)
        if worker is None:
            worker_status = "not_running"
        elif worker.cancelled() or worker.done():
            worker_status = "failed"
        else:
            worker_status = "running"

    healthy_worker = worker_status in {"running", "disabled"}
    overall_status = "ok" if database_status == "ok" and healthy_worker else "degraded"
    return {
        "status": overall_status,
        "service": "seo-bot-kanban",
        "database": {"status": database_status},
        "worker": {"status": worker_status},
    }


KANBAN_HTML_PATH = Path(__file__).parent / "static" / "kanban.html"


@app.get("/kanban", response_class=HTMLResponse)
def get_kanban():
    """Serve the Kanban board HTML."""
    if KANBAN_HTML_PATH.exists():
        return FileResponse(KANBAN_HTML_PATH)
    return HTMLResponse(
        content="<h1>kanban.html not found</h1>",
        status_code=500,
    )


# ============================================================================
# ROUTERS
# ============================================================================

app.include_router(tasks.router)
app.include_router(comments.router)
app.include_router(runs.router)
app.include_router(automation.router)


# ============================================================================
# BACKWARDS-COMPAT RE-EXPORTS (tests/orchestrator import these from here)
# ============================================================================

from agent.api.helpers import (  # noqa: E402,F401
    add_google_doc_comment,
    add_subtasks_created_comment,
    add_task_comment,
    add_task_completed_comment,
    add_task_failed_comment,
    add_task_started_comment,
    build_comment_revision_prompt,
    build_post_tool_use_hook,
    extract_agent_comment_instruction,
    is_agent_trigger_comment,
    process_one_comment_action,
    _acquire_next_comment_action,
    _agent_execution_timeout_seconds,
    _autopilot_enabled,
    _autopilot_interval_seconds,
    _build_runtime_config,
    _campaign_timeout_seconds,
    _create_run,
    _execute_campaign_with_timeout,
    _finalize_run_failure,
    _finalize_run_success,
    _get_task_session_id,
    _log_run_event,
    _mark_run_started,
    _normalize_execution_result,
    _project_root,
    _refresh_context_view,
    _resolve_prompt_context,
    _run_agent_prompt,
    _run_response,
    _serialize_prompt_context,
    _task_response,
    _upsert_task_session,
)

from agent.db import (  # noqa: E402,F401
    AgentRunModel,
    Base,
    CommentActionModel,
    CommentCreate,
    CommentModel,
    CommentResponse,
    OrchestrationStateModel,
    RunEventModel,
    RunResponse,
    SeoAuditRequest,
    SessionLocal,
    TaskCreate,
    TaskListResponse,
    TaskMemoryResponse,
    TaskModel,
    TaskResponse,
    TaskSessionModel,
    TaskStatus,
    TaskUpdate,
    engine,
    get_db,
    get_db_session,
    resolve_database_url,
)

from agent.feedback_loop import (  # noqa: E402,F401
    CMS_CHANGE_FIELD_MAP,
    SEO_CHANGES_MD_PATH,
    SEO_CHANGES_PATH,
    SEO_LEARNINGS_MD_PATH,
    SEO_LEARNINGS_PATH,
    SEO_REVIEW_BATCH_SIZE,
    VALID_REVIEW_STATUSES,
    _atomic_json_write,
    _build_change_id,
    _change_log_block_instruction,
    _load_seo_changes,
    _load_seo_learnings,
    _md_write,
    _parse_change_log_block,
    _refresh_markdown_views,
    _render_changes_markdown,
    _render_learnings_markdown,
    _write_change_log_entry,
)

from agent.prompts import build_execution_prompt  # noqa: E402,F401
