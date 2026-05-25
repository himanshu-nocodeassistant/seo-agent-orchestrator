"""
FastAPI server for Kanban UI.

Provides REST API for task management and serves the kanban HTML.
"""

import asyncio
import json
import os
import re
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Mapping, Optional
from uuid import uuid4

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# ============================================================================
# EXECUTION TYPE TAXONOMY
# ============================================================================

# Execution types that support autonomous agent execution via the Execute button
EXECUTABLE_TYPES = {
    "research", "rewrite_title", "rewrite_meta_desc", "rewrite_h1",
    "update_schema", "blog_write", "rewrite_blog_content",
    "internal_links", "alt_text", "seo_impact_review",
}

# Single registry: execution types that mutate live CMS content and should be change-logged.
# All feedback-loop logic derives from this map — do not hardcode elsewhere.
CMS_CHANGE_FIELD_MAP = {
    "rewrite_title":        "title tag",
    "rewrite_meta_desc":    "meta description",
    "rewrite_h1":           "heading structure",
    "blog_write":           "content",
    "rewrite_blog_content": "content",
    "internal_links":       "internal linking",
}

# Valid statuses for seo-changes.json entries. Enforced on write.
VALID_REVIEW_STATUSES = {
    "pending-review",
    "reviewed-positive",
    "reviewed-negative",
    "reviewed-neutral",
    "reviewed-inconclusive",
}

# Paths for SEO feedback loop persistence.
# Relative to cwd (project root). Single uvicorn worker assumed; add file lock if multi-worker.
SEO_CHANGES_PATH = Path("memory/seo-changes.json")
SEO_LEARNINGS_PATH = Path("memory/seo-learnings.json")
SEO_CHANGES_MD_PATH = Path(".claude/seo-changes-log.md")
SEO_LEARNINGS_MD_PATH = Path(".claude/seo-learnings.md")
SEO_REVIEW_BATCH_SIZE = int(os.environ.get("SEO_REVIEW_BATCH_SIZE", "20"))


def _get_gsc_client():
    """Lazy-load GSC client using service account credentials.

    Returns None if GOOGLE_APPLICATION_CREDENTIALS or GSC_SITE_URL is not set,
    so the server starts cleanly even without GSC configured.
    """
    try:
        from agent.gsc import GoogleSearchConsoleConfig, GoogleSearchConsoleClient
        config = GoogleSearchConsoleConfig.from_env()
        if config is None:
            return None
        return GoogleSearchConsoleClient(config)
    except Exception:
        return None


# Database setup
def resolve_database_url(env: Mapping[str, str] | None = None) -> str:
    """Resolve database URL using explicit DATABASE_URL or APP_ENV defaults."""
    env_map = env if env is not None else os.environ

    explicit_url = env_map.get("DATABASE_URL")
    if explicit_url:
        return explicit_url

    app_env = env_map.get("APP_ENV", "production").strip().lower()
    if app_env == "staging":
        return "sqlite:///./kanban.staging.db"

    return "sqlite:///./kanban.db"


DATABASE_URL = resolve_database_url()
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ========================================================================= MODELS
#===
# DATABASE ============================================================================

class TaskStatus(str, Enum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    blocked = "blocked"


class TaskModel(Base):
    """Task database model."""
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(50), default="pending")
    priority = Column(Integer, default=0)
    assignee = Column(String(200), nullable=True)
    due_date = Column(String(20), nullable=True)
    execution_type = Column(String(50), nullable=True)
    requires_approval = Column(Boolean, default=False)
    approved_at = Column(String(20), nullable=True)
    notes = Column(Text, nullable=True)
    model = Column(String(50), nullable=True)
    parent_task_id = Column(Integer, nullable=True)
    comment_count = Column(Integer, default=0)
    created_at = Column(String(20), default=lambda: datetime.utcnow().isoformat())
    updated_at = Column(String(20), default=lambda: datetime.utcnow().isoformat())


class CommentModel(Base):
    """Comment database model."""
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, nullable=False)
    author = Column(String(50), default="user")
    body = Column(Text, nullable=False)
    created_at = Column(String(20), default=lambda: datetime.utcnow().isoformat())


class CommentActionModel(Base):
    """Tracks agent actions for triggered user comments."""
    __tablename__ = "comment_actions"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, nullable=False, index=True)
    comment_id = Column(Integer, nullable=False, unique=True, index=True)
    status = Column(String(30), nullable=False, default="pending")
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=2)
    last_error = Column(Text, nullable=True)
    created_at = Column(String(20), default=lambda: datetime.utcnow().isoformat())
    updated_at = Column(String(20), default=lambda: datetime.utcnow().isoformat())
    acted_at = Column(String(20), nullable=True)


# Create tables
Base.metadata.create_all(bind=engine)


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class TaskCreate(BaseModel):
    """Task creation schema."""
    title: str
    description: Optional[str] = None
    priority: int = 0
    status: str = "pending"
    assignee: Optional[str] = None
    due_date: Optional[str] = None
    execution_type: Optional[str] = None
    requires_approval: bool = False


class TaskUpdate(BaseModel):
    """Task update schema."""
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[int] = None
    assignee: Optional[str] = None
    due_date: Optional[str] = None
    execution_type: Optional[str] = None
    requires_approval: Optional[bool] = None
    approved_at: Optional[str] = None
    notes: Optional[str] = None
    model: Optional[str] = None


class TaskResponse(BaseModel):
    """Task response schema."""
    id: int
    title: str
    description: Optional[str]
    status: str
    priority: int
    assignee: Optional[str]
    due_date: Optional[str]
    execution_type: Optional[str]
    requires_approval: bool
    approved_at: Optional[str]
    notes: Optional[str]
    model: Optional[str]
    parent_task_id: Optional[int]
    comment_count: int
    created_at: str
    updated_at: str


class TaskListResponse(BaseModel):
    """Task list response schema."""
    tasks: list
    total: int
    pending_count: int
    in_progress_count: int
    completed_count: int
    blocked_count: int


class CommentCreate(BaseModel):
    """Comment creation schema."""
    author: str = "user"
    body: str


class CommentResponse(BaseModel):
    """Comment response schema."""
    id: int
    task_id: int
    author: str
    body: str
    created_at: str


# ============================================================================
# DATABASE HELPERS
# ============================================================================

def get_db():
    """Get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db_session():
    """Get a database session (for sync operations)."""
    return SessionLocal()


# ============================================================================
# COMMENT HELPER FUNCTIONS
# ============================================================================

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
    
    now = datetime.utcnow().isoformat()
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
    comment_body = f"🤖 Task started by agent"
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


async def _run_agent_prompt(prompt: str) -> str:
    """Execute a freeform prompt via SEOAgent (used by comment autopilot)."""
    from agent.seo_agent import SEOAgent
    from agent.config import AgentConfig

    os.environ.pop("CLAUDECODE", None)

    config = AgentConfig.from_env()
    config.cwd = str(Path(__file__).parent.parent.parent)
    config.setting_sources = []
    config.system_prompt = (
        "You are an autonomous SEO agent. Execute the given task completely "
        "and autonomously. Use the tools available to you. Report what you did "
        "and the outcome clearly at the end."
    )
    timeout = _agent_execution_timeout_seconds()
    try:
        return await asyncio.wait_for(SEOAgent.create_and_run(prompt, config), timeout=timeout)
    except asyncio.TimeoutError as e:
        raise RuntimeError(f"Agent execution timed out after {timeout}s") from e
    except BaseException as e:
        # Python 3.11+ TaskGroup wraps sub-exceptions in ExceptionGroup — unwrap to expose root cause
        if isinstance(e, BaseExceptionGroup) and e.exceptions:
            sub = e.exceptions[0]
            raise RuntimeError(f"Agent error: {type(sub).__name__}: {sub}") from sub
        raise


async def _run_orchestrated_task(task, db, task_comments) -> str:
    """Execute a task via OrchestratorAgent with specialist routing and progress comments."""
    from agent.config import AgentConfig
    from agent.orchestrator import OrchestratorAgent

    os.environ.pop("CLAUDECODE", None)

    config = AgentConfig.from_env()
    config.cwd = str(Path(__file__).parent.parent.parent)
    config.setting_sources = []

    def add_comment(body: str) -> None:
        add_task_comment(db, task.id, body, "agent")

    orchestrator = OrchestratorAgent(config, add_comment)
    timeout = _agent_execution_timeout_seconds()
    try:
        return await asyncio.wait_for(orchestrator.run(task, task_comments), timeout=timeout)
    except asyncio.TimeoutError as e:
        raise RuntimeError(f"Agent execution timed out after {timeout}s") from e
    except BaseException as e:
        if isinstance(e, BaseExceptionGroup) and e.exceptions:
            sub = e.exceptions[0]
            raise RuntimeError(f"Agent error: {type(sub).__name__}: {sub}") from sub
        raise


def _task_response(task) -> dict:
    """Serialize task model into API response shape."""
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
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


def _acquire_next_comment_action(db) -> Optional[CommentActionModel]:
    """Find or create the next action candidate and mark it as running."""
    now = datetime.utcnow().isoformat()

    action = (
        db.query(CommentActionModel)
        .filter(
            CommentActionModel.status.in_(["pending", "failed"]),
            CommentActionModel.attempts < CommentActionModel.max_attempts,
        )
        .order_by(CommentActionModel.id.asc())
        .first()
    )

    if action is None:
        comments = db.query(CommentModel).order_by(CommentModel.id.asc()).all()
        for comment in comments:
            if not is_agent_trigger_comment(comment.author, comment.body):
                continue

            # Skip if the task was already executed after this comment was posted
            task = db.query(TaskModel).filter(TaskModel.id == comment.task_id).first()
            if task and task.updated_at and task.updated_at > comment.created_at:
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
        else:
            return None

    action.status = "running"
    action.attempts += 1
    action.updated_at = now
    db.commit()
    db.refresh(action)
    return action


async def process_one_comment_action() -> dict:
    """Process exactly one pending trigger comment action."""
    async with app.state.comment_autopilot_lock:
        db = get_db_session()
        try:
            action = _acquire_next_comment_action(db)
            if action is None:
                return {"processed": False, "reason": "no_pending_trigger_comments"}

            task = db.query(TaskModel).filter(TaskModel.id == action.task_id).first()
            comment = db.query(CommentModel).filter(CommentModel.id == action.comment_id).first()
            if not task or not comment:
                action.status = "retry_exhausted"
                action.last_error = "Task or comment no longer exists."
                action.updated_at = datetime.utcnow().isoformat()
                db.commit()
                return {
                    "processed": True,
                    "task_id": action.task_id,
                    "comment_id": action.comment_id,
                    "status": action.status,
                    "attempts": action.attempts,
                }

            task.status = "in_progress"
            task.updated_at = datetime.utcnow().isoformat()
            db.commit()
            add_task_comment(db, task.id, f"🤖 Started revision from comment #{comment.id}", "agent")

            prompt = build_comment_revision_prompt(task, comment.body)
            try:
                revised_result = await _run_agent_prompt(prompt)
                task.status = "completed"
                task.notes = revised_result
                task.updated_at = datetime.utcnow().isoformat()
                db.commit()

                add_task_comment(
                    db,
                    task.id,
                    f"🤖 Revision completed for comment #{comment.id}\n\n{revised_result}",
                    "agent",
                )

                action.status = "succeeded"
                action.acted_at = datetime.utcnow().isoformat()
                action.last_error = None
            except Exception as e:
                task.status = "blocked"
                task.notes = f"Error: {str(e)}"
                task.updated_at = datetime.utcnow().isoformat()
                db.commit()
                add_task_failed_comment(db, task.id, f"Comment #{comment.id}: {str(e)}")

                action.last_error = str(e)
                if action.attempts >= action.max_attempts:
                    action.status = "retry_exhausted"
                else:
                    action.status = "failed"

            action.updated_at = datetime.utcnow().isoformat()
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


async def _comment_autopilot_loop():
    """Background loop that periodically processes one trigger comment."""
    interval = _autopilot_interval_seconds()
    while True:
        await process_one_comment_action()
        await asyncio.sleep(interval)


# ============================================================================
# FASTAPI APP
# ============================================================================

app = FastAPI(title="SEO Bot Kanban API")
app.state.comment_autopilot_lock = asyncio.Lock()
app.state.comment_autopilot_task = None

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_comment_autopilot():
    """Start comment autopilot loop when enabled."""
    if not _autopilot_enabled():
        return
    if app.state.comment_autopilot_task is None or app.state.comment_autopilot_task.done():
        app.state.comment_autopilot_task = asyncio.create_task(_comment_autopilot_loop())


@app.on_event("shutdown")
async def shutdown_comment_autopilot():
    """Stop background autopilot loop cleanly."""
    task = app.state.comment_autopilot_task
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "seo-bot-kanban"}


# ============================================================================
# GSC ENDPOINTS
# ============================================================================

def _gsc_client_or_503():
    client = _get_gsc_client()
    if client is None:
        raise HTTPException(
            status_code=503,
            detail="GSC not configured. Set GOOGLE_APPLICATION_CREDENTIALS and GSC_SITE_URL.",
        )
    return client


@app.get("/gsc/page-metrics")
async def get_gsc_page_metrics(url: str, change_date: str):
    """
    Fetch before/after GSC Search Analytics metrics for a URL around a change date.

    Query params:
        url:         Full page URL (e.g. https://www.example.com/page)
        change_date: ISO date of the SEO change (e.g. 2026-03-06)

    Returns JSON with before/after clicks, impressions, CTR, position and computed deltas.
    """
    client = _gsc_client_or_503()
    try:
        return await client.get_page_metrics_range(url=url, change_date=change_date)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/gsc/inspect")
async def inspect_url(url: str):
    """
    Inspect a single URL using the GSC URL Inspection API.

    Query params:
        url: Full page URL to inspect.

    Returns indexed status, coverage state, canonical URLs, last crawl time,
    mobile usability verdict, and rich results verdict.
    """
    client = _gsc_client_or_503()
    try:
        from agent.gsc import GoogleSearchConsoleError
        return await client.inspect_url(url)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/gsc/index-audit")
async def gsc_index_audit(sitemap_url: str = ""):
    """
    Fetch all URLs from a sitemap and check their indexing status in GSC.

    Deduplicates URLs, normalises to trailing-slash canonical form, then inspects
    each one via the URL Inspection API. Returns a grouped report with:
      - indexed: PASS in GSC
      - not_indexed: crawled but not indexed (thin content / quality signal)
      - redirect: non-canonical URL redirecting elsewhere
      - unknown: not yet seen by Google
      - errors: API failures

    Query params:
        sitemap_url: Sitemap XML URL. Falls back to TARGET_SITEMAP_URL env var if not provided.
    """
    import xml.etree.ElementTree as ET
    import httpx

    # Resolve sitemap URL: query param → env var → 400 error
    resolved_sitemap_url = sitemap_url or os.environ.get("TARGET_SITEMAP_URL", "")
    if not resolved_sitemap_url:
        raise HTTPException(
            status_code=400,
            detail="sitemap_url query parameter is required (or set TARGET_SITEMAP_URL env var).",
        )

    client = _gsc_client_or_503()

    # Fetch and parse sitemap
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15) as http:
            resp = await http.get(resolved_sitemap_url)
            resp.raise_for_status()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch sitemap: {exc}")

    try:
        root = ET.fromstring(resp.text)
        ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        # Handle sitemap index (sitemap of sitemaps)
        sitemap_locs = root.findall("sm:sitemap/sm:loc", ns)
        if sitemap_locs:
            # Fetch first-level child sitemaps and collect all URLs
            all_urls: list[str] = []
            async with httpx.AsyncClient(follow_redirects=True, timeout=15) as http:
                for loc in sitemap_locs:
                    try:
                        child_resp = await http.get(loc.text.strip())
                        child_root = ET.fromstring(child_resp.text)
                        for url_el in child_root.findall("sm:url/sm:loc", ns):
                            all_urls.append(url_el.text.strip())
                    except Exception:
                        continue
        else:
            all_urls = [el.text.strip() for el in root.findall("sm:url/sm:loc", ns)]
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to parse sitemap: {exc}")

    if not all_urls:
        raise HTTPException(status_code=404, detail="No URLs found in sitemap.")

    resolved_sitemap_url = resolved_sitemap_url  # used in return value below

    # Deduplicate, strip anchors, and separate en (primary) from i18n URLs
    seen: set[str] = set()
    primary_urls: list[str] = []
    i18n_urls: list[str] = []
    i18n_prefixes = ("/es/", "/fr/", "/de/", "/zh/")

    for url in all_urls:
        clean = url.split("#")[0]
        if clean in seen:
            continue
        seen.add(clean)
        site_domain = os.environ.get("TARGET_SITE_URL", "").replace("https://", "").replace("http://", "").rstrip("/")
        if site_domain and any((site_domain + p) in clean for p in i18n_prefixes):
            i18n_urls.append(clean)
        else:
            primary_urls.append(clean)

    # Inspect primary English URLs only — i18n pages are excluded by default for speed.
    # The URL Inspection API is slow (~0.5s/req) so we cap at 75 to stay under 60s.
    urls = primary_urls[:75]

    results = await client.inspect_urls(urls, concurrency=10)

    grouped: dict[str, list[dict]] = {
        "indexed": [],
        "not_indexed": [],
        "redirect": [],
        "unknown": [],
        "error": [],
    }

    for r in results:
        state = r.get("coverage_state", "")
        verdict = r.get("verdict", "")
        entry = {
            "url": r["url"],
            "coverage_state": state,
            "verdict": verdict,
            "last_crawl_time": r.get("last_crawl_time"),
            "google_canonical": r.get("google_canonical"),
        }
        if verdict == "ERROR":
            grouped["error"].append(entry)
        elif verdict == "PASS":
            grouped["indexed"].append(entry)
        elif "redirect" in state.lower():
            grouped["redirect"].append(entry)
        elif "unknown" in state.lower():
            grouped["unknown"].append(entry)
        else:
            grouped["not_indexed"].append(entry)

    return {
        "sitemap_url": resolved_sitemap_url,
        "total_in_sitemap": len(all_urls),
        "total_inspected": len(urls),
        "summary": {k: len(v) for k, v in grouped.items()},
        "results": grouped,
    }


@app.post("/gsc/inspect-bulk")
async def inspect_urls_bulk(body: dict):
    """
    Inspect multiple URLs using the GSC URL Inspection API (sequential).

    Request body:
        { "urls": ["https://...", "https://..."] }

    Returns a list of inspection results. Failed URLs are included with verdict=ERROR.
    The URL Inspection API has a quota of 2,000 requests/day — use sparingly.
    """
    urls = body.get("urls", [])
    if not urls:
        raise HTTPException(status_code=400, detail="urls list is required and must not be empty.")
    if len(urls) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 URLs per request.")
    client = _gsc_client_or_503()
    try:
        results = await client.inspect_urls(urls)
        indexed = [r for r in results if r.get("is_indexed")]
        not_indexed = [r for r in results if not r.get("is_indexed") and r.get("verdict") != "ERROR"]
        errors = [r for r in results if r.get("verdict") == "ERROR"]
        return {
            "total": len(results),
            "indexed_count": len(indexed),
            "not_indexed_count": len(not_indexed),
            "error_count": len(errors),
            "results": results,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ============================================================================
# TASK ENDPOINTS
# ============================================================================

@app.get("/tasks", response_model=TaskListResponse)
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
        task_list = []
        for task in tasks:
            task_dict = {
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
                "created_at": task.created_at,
                "updated_at": task.updated_at,
            }
            task_list.append(task_dict)
        
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


@app.post("/tasks", response_model=TaskResponse)
def create_task(task: TaskCreate):
    """Create a new task."""
    db = get_db_session()
    try:
        now = datetime.utcnow().isoformat()
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
        
        return {
            "id": db_task.id,
            "title": db_task.title,
            "description": db_task.description,
            "status": db_task.status,
            "priority": db_task.priority,
            "assignee": db_task.assignee,
            "due_date": db_task.due_date,
            "execution_type": db_task.execution_type,
            "requires_approval": db_task.requires_approval,
            "approved_at": db_task.approved_at,
            "notes": db_task.notes,
            "model": db_task.model,
            "parent_task_id": db_task.parent_task_id,
            "comment_count": db_task.comment_count,
            "created_at": db_task.created_at,
            "updated_at": db_task.updated_at,
        }
    finally:
        db.close()


@app.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(task_id: int):
    """Get a single task by ID."""
    db = get_db_session()
    try:
        task = db.query(TaskModel).filter(TaskModel.id == task_id).first()
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        
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
            "created_at": task.created_at,
            "updated_at": task.updated_at,
        }
    finally:
        db.close()


@app.patch("/tasks/{task_id}", response_model=TaskResponse)
def update_task(task_id: int, task: TaskUpdate):
    """Update a task."""
    db = get_db_session()
    try:
        db_task = db.query(TaskModel).filter(TaskModel.id == task_id).first()
        if not db_task:
            raise HTTPException(status_code=404, detail="Task not found")
        
        # Update fields
        update_data = task.dict(exclude_unset=True)
        for key, value in update_data.items():
            setattr(db_task, key, value)
        
        db_task.updated_at = datetime.utcnow().isoformat()
        db.commit()
        db.refresh(db_task)
        
        return {
            "id": db_task.id,
            "title": db_task.title,
            "description": db_task.description,
            "status": db_task.status,
            "priority": db_task.priority,
            "assignee": db_task.assignee,
            "due_date": db_task.due_date,
            "execution_type": db_task.execution_type,
            "requires_approval": db_task.requires_approval,
            "approved_at": db_task.approved_at,
            "notes": db_task.notes,
            "model": db_task.model,
            "parent_task_id": db_task.parent_task_id,
            "comment_count": db_task.comment_count,
            "created_at": db_task.created_at,
            "updated_at": db_task.updated_at,
        }
    finally:
        db.close()


@app.delete("/tasks/{task_id}")
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


def _append_user_notes(prompt: str, comments) -> str:
    """Append a User Notes section to a prompt if there are any user comments."""
    if not comments:
        return prompt
    user_comments = [c for c in comments if c.author == "user"]
    if not user_comments:
        return prompt
    comment_block = "\n".join(f"- {c.body}" for c in user_comments)
    return prompt + f"\n\n## User Notes\nThe user has left the following notes on this task. Factor these into your work:\n{comment_block}"


# ============================================================================
# SEO FEEDBACK LOOP — APPLICATION-LAYER PERSISTENCE
# ============================================================================

def _atomic_json_write(path: Path, data: dict) -> None:
    """Write JSON to path atomically via temp file + os.replace().

    Single uvicorn worker assumed. Add a file lock here if multi-worker is needed.
    Creates parent directories if they don't exist.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    os.replace(tmp, path)


def _load_seo_changes() -> dict:
    """Load memory/seo-changes.json. Returns empty structure if file missing."""
    if not SEO_CHANGES_PATH.exists():
        return {"version": 1, "entries": []}
    return json.loads(SEO_CHANGES_PATH.read_text())


def _load_seo_learnings() -> dict:
    """Load memory/seo-learnings.json. Returns empty structure if file missing."""
    if not SEO_LEARNINGS_PATH.exists():
        return {"version": 1, "learnings": {}}
    return json.loads(SEO_LEARNINGS_PATH.read_text())


def _parse_change_log_block(agent_output: str) -> dict:
    """Extract and parse the structured CHANGE_LOG block from agent output.

    The agent is instructed to emit a block of the form:
        <!-- CHANGE_LOG
        { ... json ... }
        -->
    as the very last thing in its response.

    Returns a dict with extraction_status="ok" on success, or
    extraction_status="failed" with a failure_reason on any failure.

    failure_reason values:
        "missing_block"           — CHANGE_LOG comment not found
        "invalid_json"            — block found but JSON parse failed
        "missing_required_fields" — url, field, and after are all null
        "field_mismatch"          — field value present but empty string

    Never raises.
    """
    _null = {"extraction_status": "failed", "url": None, "field": None,
             "before": None, "after": None, "webflow_item_id": None,
             "webflow_status": None, "failure_reason": None}

    try:
        match = re.search(r'<!--\s*CHANGE_LOG\s*\n(.*?)\n-->', agent_output, re.DOTALL)
        if not match:
            return {**_null, "failure_reason": "missing_block"}

        raw = match.group(1).strip()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return {**_null, "failure_reason": "invalid_json"}

        # Check that at least one of url/field/after has a usable value
        url = payload.get("url") or None
        field = payload.get("field") or None
        after = payload.get("after") or None
        if url is None and field is None and after is None:
            return {**_null, "failure_reason": "missing_required_fields"}

        # field present but empty string
        if field is not None and field.strip() == "":
            return {**_null, "failure_reason": "field_mismatch"}

        return {
            "extraction_status": "ok",
            "failure_reason": None,
            "url": url,
            "field": field,
            "before": payload.get("before") or None,
            "after": after,
            "webflow_item_id": payload.get("webflow_item_id") or None,
            "webflow_status": payload.get("webflow_status") or None,
        }
    except Exception:
        return {**_null, "failure_reason": "missing_block"}


def _build_change_id(task_id: int, execution_type: str, url: str | None) -> str:
    """Build a deterministic, idempotent change ID for a task execution.

    Format: "{task_id}-{execution_type}-{url_slug}"
    Slug is derived from the URL path, lowercased, non-alphanumeric replaced with hyphens,
    truncated to 40 chars. Falls back to "unknown" when url is None.
    """
    raw = (url or "unknown").lower()
    # Strip scheme and domain, keep path
    raw = raw.split("//")[-1]  # remove https://
    slug = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")[:40]
    return f"{task_id}-{execution_type}-{slug}"


def _write_change_log_entry(task, agent_output: str, user_comments: list) -> None:
    """Parse agent output for a CHANGE_LOG block and persist a change entry.

    - If execution_type is not in CMS_CHANGE_FIELD_MAP: no-op.
    - Parses the structured block from agent_output deterministically.
    - If block is absent/invalid: writes entry with extraction_status="failed" and failure_reason.
    - Upserts by change ID: on re-execution, increments attempts and preserves review state.
    - Writes atomically and refreshes markdown views.

    Args:
        task: TaskModel instance (id, title, execution_type)
        agent_output: Full string output from the agent
        user_comments: List of CommentModel instances (author, body)
    """
    if task.execution_type not in CMS_CHANGE_FIELD_MAP:
        return

    payload = _parse_change_log_block(agent_output)
    change_id = _build_change_id(task.id, task.execution_type, payload.get("url"))

    data = _load_seo_changes()
    existing_index = {e["id"]: i for i, e in enumerate(data["entries"])}

    entry = {
        "id": change_id,
        "task_id": task.id,
        "task_title": task.title,
        "execution_type": task.execution_type,
        "change_type": CMS_CHANGE_FIELD_MAP[task.execution_type],
        "url": payload.get("url"),
        "webflow_item_id": payload.get("webflow_item_id"),
        "before": payload.get("before"),
        "after": payload.get("after"),
        "extraction_status": payload["extraction_status"],
        "failure_reason": payload.get("failure_reason"),
        "is_backfilled": False,
        "user_notes": [
            {"author": c.author, "body": c.body}
            for c in user_comments
            if c.author == "user"
        ],
        "logged_at": datetime.utcnow().isoformat() + "Z",
        "attempts": 1,
        "status": "pending-review",
        "review_notes": None,
        "reviewed_at": None,
        "learning_ids": [],
    }

    if change_id in existing_index:
        old = data["entries"][existing_index[change_id]]
        entry["attempts"] = old.get("attempts", 1) + 1
        entry["status"] = old.get("status", "pending-review")
        entry["review_notes"] = old.get("review_notes")
        entry["reviewed_at"] = old.get("reviewed_at")
        entry["learning_ids"] = old.get("learning_ids", [])
        entry["logged_at"] = old.get("logged_at", entry["logged_at"])
        data["entries"][existing_index[change_id]] = entry
    else:
        data["entries"].append(entry)

    _atomic_json_write(SEO_CHANGES_PATH, data)
    _refresh_markdown_views()


def _render_changes_markdown(entries: list) -> str:
    """Render seo-changes.json entries to human/agent-readable markdown.

    Groups entries by status. Each entry shows key fields in a compact block.
    Returns a string suitable for writing to .claude/seo-changes-log.md.
    """
    if not entries:
        return "# SEO Changes Log\n\n_No entries yet._\n"

    # Group by status
    groups: dict[str, list] = {}
    for e in entries:
        groups.setdefault(e.get("status", "unknown"), []).append(e)

    # Order: pending first, then reviewed-*, then others
    status_order = [
        "pending-review",
        "reviewed-positive",
        "reviewed-negative",
        "reviewed-neutral",
        "reviewed-inconclusive",
    ]
    lines = ["# SEO Changes Log\n"]
    for status in status_order + [s for s in groups if s not in status_order]:
        if status not in groups:
            continue
        lines.append(f"\n## {status} ({len(groups[status])})\n")
        for e in sorted(groups[status], key=lambda x: x.get("logged_at", "")):
            lines.append(f"### {e.get('logged_at', '')[:10]} — {e.get('task_title', 'Untitled')}")
            lines.append(f"- **ID:** `{e.get('id', '')}`")
            lines.append(f"- **Page:** {e.get('url', 'unknown')}")
            lines.append(f"- **Change type:** {e.get('change_type', '')}")
            lines.append(f"- **Before:** {e.get('before', 'null')}")
            lines.append(f"- **After:** {e.get('after', 'null')}")
            lines.append(f"- **Extraction:** {e.get('extraction_status', '')} / {e.get('failure_reason', 'n/a')}")
            if e.get("review_notes"):
                lines.append(f"- **Review notes:** {e['review_notes']}")
            if e.get("user_notes"):
                notes = "; ".join(n["body"] for n in e["user_notes"])
                lines.append(f"- **User notes:** {notes}")
            lines.append("")

    return "\n".join(lines)


def _render_learnings_markdown(learnings: dict) -> str:
    """Render seo-learnings.json to human/agent-readable markdown.

    Sorted by confidence (high → medium → low). Returns a string suitable
    for writing to .claude/seo-learnings.md.
    """
    if not learnings:
        return "# SEO Learnings\n\n_No learnings extracted yet._\n"

    conf_order = {"high": 0, "medium": 1, "low": 2}
    sorted_items = sorted(
        learnings.values(),
        key=lambda x: (conf_order.get(x.get("confidence", "low"), 2), x.get("id", ""))
    )

    site_url_label = os.environ.get("TARGET_SITE_URL", "this site")
    lines = ["# SEO Learnings\n",
             f"_Principles extracted from measured ranking changes on {site_url_label}._\n"]
    for l in sorted_items:
        lines.append(f"## {l.get('id', 'unknown')} [{l.get('confidence', '?')} confidence, {l.get('hit_count', 0)} hits]")
        lines.append(f"- **Discovered:** {l.get('discovered', '')}")
        lines.append(f"- **Principle:** {l.get('principle', '')}")
        lines.append(f"- **Evidence:** {l.get('evidence', '')}")
        lines.append(f"- **Applicable when:** {l.get('applicable_when', '')}")
        lines.append(f"- **Not applicable when:** {l.get('not_applicable_when', '')}")
        lines.append("")

    return "\n".join(lines)


def _refresh_markdown_views() -> None:
    """Regenerate .claude/seo-changes-log.md and .claude/seo-learnings.md from JSON sources.

    Called after every JSON write to keep markdown views in sync.
    """
    changes = _load_seo_changes()
    learnings = _load_seo_learnings()

    changes_md = _render_changes_markdown(changes["entries"])
    learnings_md = _render_learnings_markdown(learnings["learnings"])

    SEO_CHANGES_MD_PATH.parent.mkdir(parents=True, exist_ok=True)
    _atomic_json_write.__wrapped__ = None  # type hint only
    # Use plain write for markdown (not JSON, so _atomic_json_write not applicable)
    _md_write(SEO_CHANGES_MD_PATH, changes_md)
    _md_write(SEO_LEARNINGS_MD_PATH, learnings_md)


def _md_write(path: Path, content: str) -> None:
    """Write markdown atomically via temp file + os.replace()."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def _change_log_block_instruction(execution_type: str) -> str:
    """Return the per-type CHANGE_LOG block instruction to append to agent prompts.

    Returns "" for non-CMS types. Each type specifies exactly which fields to
    populate and where to find them in the workflow output — no ambiguity.
    """
    if execution_type not in CMS_CHANGE_FIELD_MAP:
        return ""

    field = CMS_CHANGE_FIELD_MAP[execution_type]

    per_type_guidance = {
        "rewrite_title": (
            "Set url = the page URL. "
            "Set before = the current title (from your research/fetch). "
            "Set after = the final title you produced."
        ),
        "rewrite_meta_desc": (
            "Set url = the page URL. "
            "Set before = the current meta description (or null if not found). "
            "Set after = the final meta description you produced."
        ),
        "rewrite_h1": (
            "Set url = the page URL. "
            "Set before = the old H1 from your WebFetch. "
            "Set after = the final H1 you produced."
        ),
        "blog_write": (
            "Set url = the planned live URL of the new post (slug-based). "
            "Set before = null (new post). "
            "Set after = the SEO title of the new post."
        ),
        "rewrite_blog_content": (
            "Set url = the page URL. "
            "Set before = old SEO title or slug. "
            "Set after = new SEO title if changed, or 'content updated'."
        ),
        "internal_links": (
            "Set url = comma-separated list of all URLs updated. "
            "Set before = null. "
            "Set after = 'N links added: [anchor text → target URL, ...]'."
        ),
    }

    guidance = per_type_guidance.get(execution_type, "Populate all fields from your work above.")

    return f"""

---
**Required: append this block as the very last content in your response.**
{guidance}

<!-- CHANGE_LOG
{{
  "url": "<page URL>",
  "field": "{field}",
  "before": "<previous value, or null>",
  "after": "<new value>",
  "webflow_item_id": null,
  "webflow_status": "manual-only"
}}
-->"""


def build_execution_prompt(task, comments=None, config=None) -> str:
    """
    Build a workflow-aware prompt for the agent based on the task's execution_type.

    Returns a rich prompt with step-by-step workflow instructions tailored
    to the execution type so the agent can act end-to-end autonomously.
    Used by: legacy fallback path and comment autopilot.

    Args:
        task: TaskModel database object with title, description, execution_type
        comments: Optional list of comment objects (with .author and .body). User
            comments are appended as a "User Notes" section so the agent factors
            them in during execution.
        config: Optional AgentConfig for site_name/site_url substitution.

    Returns:
        Complete prompt string with context and ordered workflow steps
    """
    from agent.config import AgentConfig as _AgentConfig
    _config = config or _AgentConfig.from_env()
    site_name = _config.site_name
    site_url = _config.site_url

    base = f"Task: {task.title}\n"
    if task.description:
        base += f"Details: {task.description}\n"

    etype = task.execution_type

    if etype == "rewrite_title":
        _prompt = base + f"""
You are executing an SEO task: research keywords and rewrite the page/post title.

WORKFLOW — execute every step in order:

Step 1 — Keyword research
Use WebSearch to find SEO keywords for this topic:
- Search: "best keywords for [topic] [current year]"
- Search: "[topic] site keyword competition"
- Review top competitor titles from search results
Identify: primary keyword (highest commercial intent), secondary keywords, competitor title formats.

Step 2 — Generate 3 title options
Rules:
- 50–60 characters including spaces
- Primary keyword near the beginning
- Brand name at the end: "Keyword Phrase | {site_name}"
- Direct and clear — no filler qualifiers ("Trusted", "Best", "Leading")

Step 3 — Finalize draft
Pick the strongest title and present clearly:
- Final title draft
- 2 backup options
- Keyword rationale (search intent, competitive context)

Step 4 — Report:
- Final draft title: [final draft]
- Backup options: [2]
- Keyword rationale
"""
        _prompt += _change_log_block_instruction(etype)
        return _append_user_notes(_prompt, comments)

    elif etype == "rewrite_meta_desc":
        _prompt = base + f"""
You are executing an SEO task: research and rewrite the meta description for a page.

WORKFLOW — execute every step in order:

Step 1 — Research
Use WebSearch to understand what competitors use in meta descriptions for this topic:
- Search: "[topic] [page type] meta description examples"
- Identify: primary keyword, user intent, strongest value propositions.

Step 2 — Write the meta description
Rules:
- 150–160 characters exactly (count carefully)
- Primary keyword appears naturally in the first half
- Clear value proposition
- Ends with an implicit or explicit call to action
- No keyword stuffing; reads naturally

Step 3 — Finalize draft
Present:
- Final meta description draft
- Character count
- Primary keyword used

Step 4 — Report:
- Final draft: [meta description]
- Character count: [exact count]
- Primary keyword: [keyword]
"""
        _prompt += _change_log_block_instruction(etype)
        return _append_user_notes(_prompt, comments)

    elif etype == "rewrite_h1":
        _prompt = base + f"""
You are executing an SEO task: rewrite the H1 heading for a page.

WORKFLOW — execute every step in order:

Step 1 — Fetch the current page
Use WebFetch on the URL referenced in the task to see the current H1.

Step 2 — Research search intent
Use WebSearch: "what do people search for [topic]" and "[topic] user intent"
The H1 must match the expectation a user has after clicking from the SERP.

Step 3 — Write 2 H1 options
Rules:
- Under 70 characters
- Contains the primary keyword
- Specific to this page (not reusable across other pages)
- Direct and clear — no filler

Step 4 — Finalize draft
Pick the strongest option and present:
- Final H1 draft
- Backup H1 option
- Rationale

Step 5 — Report:
- Old H1: [what it was]
- Final draft H1: [selected draft]
- Keyword + intent rationale
"""
        _prompt += _change_log_block_instruction(etype)
        return _append_user_notes(_prompt, comments)

    elif etype == "blog_write":
        _prompt = base + f"""
You are executing an SEO task: research and write a new blog post.

WORKFLOW — execute every step in order:

Step 1 — Keyword research
Use WebSearch to identify:
- The primary keyword and monthly search volume for this topic
- The top 5 ranking pages (their titles, H1s, approximate word counts)
- Secondary keywords and related questions (People Also Ask)
Search: "[topic] keyword research", "[topic] how to", "[topic] guide"

Step 2 — Outline
Create a full post outline:
- SEO title (50-60 chars, keyword-first, ends with "| {site_name}")
- Meta description (150-160 chars)
- H1 (matches or is very close to the SEO title)
- H2 sections with supporting H3s where needed
- Target word count: 800-1500 words

Step 3 — Write the post
Use the Skill tool to invoke the copywriting skill.
Write the full post following the outline. Must include:
- Primary keyword in first 100 words
- Keyword density ~1-2% (natural usage)
- 2-3 internal links to other {site_url} pages
- CTA at the end pointing to the site's services

Step 4 — Finalize draft
Present clearly:
- SEO title
- Meta description
- Slug suggestion
- Full post content
- Excerpt

Step 5 — Report:
- Title: [title]
- URL slug: [slug]
- Word count: [count]
- Primary keyword targeted: [keyword]
"""
        _prompt += _change_log_block_instruction(etype)
        return _append_user_notes(_prompt, comments)

    elif etype == "rewrite_blog_content":
        _prompt = base + f"""
You are executing an SEO task: rewrite existing blog content for better SEO.

WORKFLOW — execute every step in order:

Step 1 — Audit the current content
Use WebFetch on the live page URL to see how it renders.
Analyze: current keyword targeting, word count, structure, missing sections, outdated info.

Step 2 — Keyword research
Use WebSearch to find what's ranking for this topic now.
Confirm or update the keyword target.

Step 3 — Rewrite
Use the Skill tool: invoke "copy-editing" skill for targeted improvements, or "copywriting"
skill for a full rewrite if the content is poor.
Apply: better keyword targeting, improved structure, updated information, internal links.

Step 4 — Finalize revised draft
Present clearly:
- Revised title (if changed)
- Revised SEO title/meta description
- Revised excerpt
- Full revised content

Step 5 — Report:
- What changed: content, title, meta desc
- Old keyword target vs new keyword target
- Key improvements made
"""
        _prompt += _change_log_block_instruction(etype)
        return _append_user_notes(_prompt, comments)

    elif etype == "internal_links":
        _prompt = base + f"""
You are executing an SEO task: create an internal link plan between pages on {site_url}.

WORKFLOW — execute every step in order:

Step 1 — Research site structure
Use WebFetch on the site URL or sitemap to understand what pages exist.
Build a map of each key page: title, URL, topic/theme.

Step 2 — Identify link opportunities
For the page(s) mentioned in the task, identify which other site pages are topically related
and would benefit from a link to or from this page.
Prioritize: pages with overlapping topics, service pages, case studies relevant to the post.

Step 3 — Produce the link plan
For each recommended internal link, specify:
- Source page URL
- Target page URL
- Suggested anchor text
- Where to insert in the source page (section/paragraph hint)

Step 4 — Report:
- Link plan: [table of source → target, anchor text, insertion point]
- Priority links (most impactful 3-5): highlighted
- Manual implementation instructions
"""
        _prompt += _change_log_block_instruction(etype)
        return _append_user_notes(_prompt, comments)

    elif etype == "research":
        _prompt = base + f"""
You are executing an SEO research task. This is research-only — no CMS changes.

WORKFLOW — execute every step in order:

Step 1 — Understand the research question
Parse the task title and description to identify what needs researching
(keywords, competitors, content gaps, audience intent, etc.)

Step 2 — Conduct research
Use WebSearch and WebFetch to gather data:
- Keyword research: search volume, difficulty, intent
- Competitor analysis: who ranks, what they cover, their titles and structure
- Industry sources: relevant data points, statistics, trends
Search broadly first, then narrow in on the most relevant findings.

Step 3 — Synthesize findings
Produce a structured report with:
- Primary keyword recommendations (with estimated search volume if findable)
- Competitor analysis (who ranks, why they rank, gaps you can exploit)
- Specific actionable recommendations for {site_url}
- Suggested next tasks with their execution types (e.g., rewrite_title, blog_write)

Step 4 — Save findings to task notes.
No CMS changes needed for this task type."""
        return _append_user_notes(_prompt, comments)

    elif etype == "alt_text":
        _prompt = base + """
You are executing an SEO task: write descriptive alt text for images on a page.

This task produces copy-paste-ready alt text recommendations for manual implementation.

WORKFLOW — execute every step in order:

Step 1 — Fetch the page
Use WebFetch on the URL referenced in the task.
Find all images with empty alt="" or missing alt attributes.
Categorize them: logos, testimonials/portraits, rating stars, content images, decorative.

Step 2 — Write alt text per category
Rules by image type:
- Client logos: "[Company Name] logo"
- Testimonial portraits: "[Person Name], [Job Title] at [Company Name]"
- Rating stars: "Rating X out of 5 stars" (or aria-hidden if purely decorative)
- Content images: descriptive text of what the image shows and its purpose
- Decorative dividers/backgrounds: leave as alt="" (correct) or add aria-hidden="true"

Step 3 — Produce a report
Format as a table:
| Image Description / URL | Recommended Alt Text |
|---|---|
...

Step 4 — Save report to task notes. No automated CMS changes for this task type."""
        return _append_user_notes(_prompt, comments)

    elif etype == "update_schema":
        _prompt = base + """
You are executing an SEO task: generate JSON-LD structured data for a page.

This task generates the correct JSON-LD and provides copy-paste instructions
for the site's CMS or page settings Custom Code / Head Code section.

WORKFLOW — execute every step in order:

Step 1 — Fetch the current page
Use WebFetch on the URL referenced in the task.
Check what JSON-LD schemas already exist (look for <script type="application/ld+json">).
Note the page type: blog post, service page, FAQ, homepage, etc.

Step 2 — Research the correct schema type
Based on the page type, identify the appropriate schema:
- BlogPosting or Article (blog posts)
- Service (service pages)
- FAQPage (FAQ pages)
- Organization (homepage/about)
- BreadcrumbList (navigation)
Use WebFetch to check schema.org spec: "schema.org [schema type] required properties"

Step 3 — Generate the JSON-LD
Write the complete, valid JSON-LD block.
Use https://schema.org (not http://).
Include all recommended fields (not just required).
Validate mentally against the schema.org spec.

Step 4 — Produce implementation instructions
Paste the complete JSON-LD <script> block with step-by-step instructions
for inserting it into the page's <head> section.

Step 5 — Save to task notes. No automated CMS changes."""
        return _append_user_notes(_prompt, comments)

    elif etype == "seo_impact_review":
        cms_types_list = ", ".join(sorted(CMS_CHANGE_FIELD_MAP.keys()))
        _prompt = base + f"""
You are running an SEO feedback loop impact review for {site_url}.
Execute phases in order. After each phase the system state must be valid before proceeding.

CONSTRAINTS:
- Process at most {SEO_REVIEW_BATCH_SIZE} pending-review entries per run (oldest logged_at first)
- Skip entry and mark reviewed-inconclusive if live data unavailable after 2 fetch attempts
- Never re-review entries already in a reviewed-* state
- Write JSON updates after each individual entry, not batched at the end

PHASE 1 — Backfill unlogged completed tasks
1. GET http://localhost:8000/tasks — collect all tasks with status=completed
2. Read memory/seo-changes.json — note all task_ids already present
3. For each completed task with execution_type in [{cms_types_list}] whose task_id is not in the log:
   Append a backfill entry to memory/seo-changes.json:
   {{
     "id": "<task_id>-<execution_type>-unknown",
     "task_id": <id>, "task_title": "<title>", "execution_type": "<type>",
     "change_type": "<mapped from CMS_CHANGE_FIELD_MAP>", "url": null,
     "before": null, "after": null, "extraction_status": "backfilled",
     "is_backfilled": true, "logged_at": "<task updated_at>", "attempts": 1,
     "status": "pending-review", "review_notes": null, "reviewed_at": null,
     "learning_ids": [], "failure_reason": null
   }}
4. Write memory/seo-changes.json atomically. Regenerate .claude/seo-changes-log.md.
→ State: all completed CMS tasks now have a log entry.

PHASE 2 — Load batch
1. Read memory/seo-changes.json
2. Filter entries where status = "pending-review", sort by logged_at ASC, take first {SEO_REVIEW_BATCH_SIZE}
3. Report: "Found N pending entries. Processing M (batch limit: {SEO_REVIEW_BATCH_SIZE})."
→ State: batch list defined, no mutations yet.

PHASE 3 — Evaluate each entry (sequential)
For each entry in the batch:
a. If is_backfilled=true and url=null: set status=reviewed-inconclusive,
   review_notes="backfilled — no URL to evaluate", reviewed_at=now. Write JSON. Continue.
b. WebFetch the entry url — note current value of the changed field
c. WebSearch: "site:{site_url}" + page path + change_type + "impact"
d. Classify outcome: reviewed-positive | reviewed-negative | reviewed-neutral | reviewed-inconclusive
   - positive: measurable improvement visible (ranking, snippet, field value)
   - negative: measurable regression
   - neutral: change present but no ranking signal yet
   - inconclusive: live data unavailable after 2 attempts
e. For negative: add one-line hypothesis (too soon / competitor change / intent mismatch / rolled back)
f. Set entry status, review_notes, reviewed_at=now in memory/seo-changes.json
g. Atomic write immediately after each entry — partial progress is safe on timeout

PHASE 4 — Extract learnings (positives only, skip backfilled)
For each reviewed-positive, non-backfilled entry:
1. Read memory/seo-learnings.json
2. Derive a kebab-case principle key (e.g. "buyer-intent-qualifier-in-title")
3. If key already exists: increment hit_count, add source_entry_id, update updated_at.
   Promote confidence: low→medium at 2 hits, medium→high at 4 hits.
4. If key is new: add full entry with confidence=low, hit_count=1
5. Write memory/seo-learnings.json atomically after each learning
6. Update source entry's learning_ids in memory/seo-changes.json

PHASE 5 — Refresh views
Regenerate .claude/seo-changes-log.md from memory/seo-changes.json
Regenerate .claude/seo-learnings.md from memory/seo-learnings.json

PHASE 6 — Return structured summary (becomes task result and completion comment)
Entries processed: N | Positive: N | Negative: N | Neutral: N | Inconclusive: N | Backfilled (skipped): N
New learnings: [id: principle]
Confidence updates: [id: previous→new]
Propagation opportunities: [page URL → learning to apply]
Recommended next tasks: [task title, execution_type]
"""
        return _append_user_notes(_prompt, comments)

    else:
        # Default: flat prompt for unknown or manual types
        _prompt = task.title
        if task.description:
            _prompt += f"\n\n{task.description}"
        return _append_user_notes(_prompt, comments)


@app.post("/tasks/{task_id}/execute", response_model=TaskResponse)
async def execute_task(task_id: int):
    """Execute a task via SEOAgent."""
    db = get_db_session()
    try:
        task = db.query(TaskModel).filter(TaskModel.id == task_id).first()
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        
        # Update status to in_progress
        task.status = "in_progress"
        task.updated_at = datetime.utcnow().isoformat()
        db.commit()
        
        # Add "task started" comment
        add_task_started_comment(db, task_id, task.title)
        
        # Execute the task via OrchestratorAgent (routes to specialist agents)
        try:
            task_comments = db.query(CommentModel).filter(CommentModel.task_id == task_id).order_by(CommentModel.created_at).all()
            result = await _run_orchestrated_task(task, db, task_comments)

            # Update task with result
            task.status = "completed"
            task.notes = result
            task.updated_at = datetime.utcnow().isoformat()
            db.commit()

            # Deterministic application-layer change logging (guaranteed, not prompt-dependent)
            if task.execution_type in CMS_CHANGE_FIELD_MAP:
                try:
                    _write_change_log_entry(task, result, task_comments)
                except Exception as log_err:
                    add_task_comment(db, task_id, f"⚠️ Change log write failed: {log_err}", "agent")

            # Add "task completed" comment
            add_task_completed_comment(db, task_id, result)
            
        except Exception as e:
            # Mark as blocked on error
            task.status = "blocked"
            task.notes = f"Error: {str(e)}"
            task.updated_at = datetime.utcnow().isoformat()
            db.commit()
            
            # Add "task failed" comment
            add_task_failed_comment(db, task_id, str(e))
        
        # Refresh task to get updated comment_count
        db.refresh(task)
        
        return _task_response(task)
    finally:
        db.close()


# ============================================================================
# COMMENT ENDPOINTS
# ============================================================================

@app.get("/tasks/{task_id}/comments", response_model=list[CommentResponse])
def get_comments(task_id: int):
    """Get all comments for a task."""
    db = get_db_session()
    try:
        comments = db.query(CommentModel).filter(CommentModel.task_id == task_id).all()
        
        return [
            {
                "id": c.id,
                "task_id": c.task_id,
                "author": c.author,
                "body": c.body,
                "created_at": c.created_at,
            }
            for c in comments
        ]
    finally:
        db.close()


@app.post("/tasks/{task_id}/comments", response_model=CommentResponse)
def create_comment(task_id: int, comment: CommentCreate):
    """Add a comment to a task."""
    db = get_db_session()
    try:
        task = db.query(TaskModel).filter(TaskModel.id == task_id).first()
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        
        now = datetime.utcnow().isoformat()
        db_comment = CommentModel(
            task_id=task_id,
            author=comment.author,
            body=comment.body,
            created_at=now,
        )
        db.add(db_comment)
        
        # Increment comment count
        task.comment_count += 1
        
        db.commit()
        db.refresh(db_comment)
        
        return {
            "id": db_comment.id,
            "task_id": db_comment.task_id,
            "author": db_comment.author,
            "body": db_comment.body,
            "created_at": db_comment.created_at,
        }
    finally:
        db.close()


@app.post("/automation/comments/process-one")
async def process_one_comment_action_endpoint():
    """Process one pending @agent trigger comment action."""
    return await process_one_comment_action()


# ============================================================================
# SEO AUDIT ENDPOINT
# ============================================================================

@app.post("/runs/{run_id}/seo-audit")
async def run_seo_audit(run_id: str, days: int = 28, max_rows: int = 1000):
    """Run SEO audit and create tasks."""
    db = get_db_session()
    try:
        # Create SEO audit task
        now = datetime.utcnow().isoformat()
        task = TaskModel(
            title=f"SEO Audit - {run_id}",
            description=f"Run comprehensive SEO audit for the last {days} days",
            status="in_progress",
            priority=0,
            execution_type="seo_audit",
            created_at=now,
            updated_at=now,
        )
        db.add(task)
        db.commit()
        
        # Execute SEO audit
        try:
            prompt = f"Run a comprehensive SEO audit analyzing data from the last {days} days. Focus on identifying issues and opportunities."
            result = await _run_agent_prompt(prompt)

            # Update task
            task.status = "completed"
            task.notes = result
            task.updated_at = datetime.utcnow().isoformat()
            db.commit()

            # Auto-trigger task breakdown: parse audit findings into Kanban tasks
            breakdown_prompt = f"""The SEO audit has just completed. Here are the findings:

{result}

Now use the Task Breakdown skill to break these findings into actionable tasks.

After creating the task breakdown, create each task in the Kanban board by calling the local API:
- POST http://localhost:8000/tasks
- Body: {{"title": "...", "description": "...", "priority": <0=critical,1=high,2=medium,3=low>, "execution_type": "<see mapping below>"}}

Map priorities as: 🔴 Critical → 0, 🟠 High → 1, 🟡 Medium → 2, 🟢 Low → 3

Map execution_type based on the task category:
- Title tag rewrites (meta title / SEO title) → "rewrite_title"
- Meta description writes or rewrites → "rewrite_meta_desc"
- H1 heading rewrites → "rewrite_h1"
- Alt text for images → "alt_text"
- Schema markup / JSON-LD structured data → "update_schema"
- Writing new blog posts → "blog_write"
- Editing or rewriting existing blog content → "rewrite_blog_content"
- Publishing a CMS item to live → "webflow_publish"
- Adding internal links between pages → "internal_links"
- Keyword research or competitor research → "research"
- Tasks requiring Webflow Designer access (custom code, static page templates, favicon, global settings) → "manual"
- Scheduling a periodic review of SEO change outcomes (2-4 weeks after changes) → "seo_impact_review"

            Use the Bash tool to make curl requests for each task. Create one Kanban card per actionable task (not subtasks — only parent tasks or standalone tasks).
"""
            try:
                await _run_agent_prompt(breakdown_prompt)
            except Exception as e:
                print(f"Task breakdown failed: {e}")

        except Exception as e:
            task.status = "blocked"
            task.notes = f"Audit error: {str(e)}"
            task.updated_at = datetime.utcnow().isoformat()
            db.commit()

        return {"message": "Audit complete", "tasks": [task.id]}
    finally:
        db.close()


# ============================================================================
# KANBAN HTML
# ============================================================================

@app.get("/kanban", response_class=HTMLResponse)
def get_kanban():
    """Serve the kanban HTML page."""
    kanban_path = Path(__file__).parent.parent.parent / "kanban.html"
    
    if kanban_path.exists():
        return FileResponse(kanban_path)
    
    # If file doesn't exist, return embedded HTML
    return HTMLResponse(content=KANBAN_HTML, media_type="text/html")


# Embedded kanban HTML (fallback if file not found)
KANBAN_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SEO Bot — Kanban</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600;1,9..40,400&family=DM+Mono:wght@300;400;500&display=swap" rel="stylesheet">
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
        tailwind.config = {
            theme: {
                extend: {
                    fontFamily: {
                        sans: ['DM Sans', 'system-ui', 'sans-serif'],
                        mono: ['DM Mono', 'monospace'],
                    },
                    colors: {
                        blue: {
                            50: '#eff6ff', 100: '#dbeafe', 200: '#bfdbfe',
                            300: '#93c5fd', 400: '#60a5fa', 500: '#3b82f6',
                            600: '#2563eb', 700: '#1d4ed8', 800: '#1e40af', 900: '#1e3a8a',
                        }
                    }
                }
            }
        }
    </script>
    <style>
        /* Base styles from seo-agent */
        *, *::before, *::after { box-sizing: border-box; }
        body {
            font-family: 'DM Sans', system-ui, sans-serif;
            background-color: #f4f6f9;
            color: #111827;
            -webkit-font-smoothing: antialiased;
        }
        #top-accent {
            height: 3px;
            background: linear-gradient(90deg, #2563eb 0%, #3b82f6 50%, #60a5fa 100%);
            position: fixed;
            top: 0; left: 0; right: 0;
            z-index: 60;
        }
        header {
            background: #ffffff;
            border-bottom: 1px solid #e5e7eb;
            position: sticky;
            top: 3px;
            z-index: 40;
            height: 56px;
            display: flex;
            align-items: center;
        }
        .header-inner {
            max-width: 1400px;
            width: 100%;
            margin: 0 auto;
            padding: 0 24px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .logo-mark {
            width: 32px; height: 32px;
            background: #2563eb;
            border-radius: 8px;
            display: flex; align-items: center; justify-content: center;
            flex-shrink: 0;
        }
        .logo-mark svg { width: 16px; height: 16px; color: white; }
        .app-title { font-size: 15px; font-weight: 600; color: #111827; letter-spacing: -0.01em; }
        .app-subtitle { font-size: 11px; color: #9ca3af; font-weight: 400; letter-spacing: 0.02em; text-transform: uppercase; }
        
        /* Buttons */
        .btn {
            display: inline-flex; align-items: center; gap: 6px;
            padding: 6px 12px;
            border-radius: 7px;
            font-size: 13px;
            font-weight: 500;
            font-family: inherit;
            cursor: pointer;
            border: none;
            transition: all 0.15s ease;
            white-space: nowrap;
        }
        .btn svg { width: 14px; height: 14px; flex-shrink: 0; }
        .btn-ghost { background: transparent; color: #6b7280; }
        .btn-ghost:hover { background: #f4f6f9; color: #374151; }
        .btn-primary { background: #2563eb; color: #ffffff; }
        .btn-primary:hover { background: #1d4ed8; }
        .btn-success { background: #059669; color: #ffffff; }
        .btn-success:hover { background: #047857; }
        
        /* Stats Bar */
        .stats-bar {
            background: #ffffff;
            border: 1px solid #e5e7eb;
            border-radius: 12px;
            padding: 14px 24px;
            display: flex;
            align-items: center;
            gap: 0;
            margin-bottom: 20px;
        }
        .stat-item { flex: 1; text-align: center; padding: 4px 0; position: relative; }
        .stat-item + .stat-item::before {
            content: '';
            position: absolute;
            left: 0; top: 50%;
            transform: translateY(-50%);
            height: 28px;
            width: 1px;
            background: #e5e7eb;
        }
        .stat-value { font-size: 22px; font-weight: 600; line-height: 1; letter-spacing: -0.02em; margin-bottom: 3px; }
        .stat-label { font-size: 10.5px; color: #9ca3af; font-weight: 500; text-transform: uppercase; letter-spacing: 0.06em; }
        
        /* Kanban */
        .kanban-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; }
        @media (max-width: 1024px) { .kanban-grid { grid-template-columns: repeat(2, 1fr); } }
        @media (max-width: 640px) { .kanban-grid { grid-template-columns: 1fr; } }
        
        .kanban-col {
            background: #eef0f3;
            border-radius: 12px;
            padding: 12px;
            min-height: 60vh;
            display: flex;
            flex-direction: column;
        }
        .col-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; padding: 2px 0; }
        .col-title { display: flex; align-items: center; gap: 7px; font-size: 12px; font-weight: 600; color: #374151; text-transform: uppercase; letter-spacing: 0.06em; }
        .col-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
        .col-badge { font-size: 10.5px; font-weight: 600; padding: 2px 7px; border-radius: 10px; line-height: 1.4; }
        .col-tasks { display: flex; flex-direction: column; gap: 8px; flex: 1; }
        
        /* Task Card */
        .task-card {
            background: #ffffff;
            border: 1px solid #e5e7eb;
            border-radius: 9px;
            padding: 11px 12px;
            cursor: pointer;
            transition: transform 0.14s ease, box-shadow 0.14s ease, border-color 0.14s ease;
            position: relative;
            overflow: hidden;
        }
        .task-card::before {
            content: '';
            position: absolute;
            left: 0; top: 0; bottom: 0;
            width: 3px;
            border-radius: 9px 0 0 9px;
        }
        .task-card:hover {
            transform: translateY(-1.5px);
            box-shadow: 0 4px 16px rgba(0,0,0,0.07), 0 1px 4px rgba(0,0,0,0.04);
            border-color: #d1d5db;
        }
        
        .card-pending::before { background: #9ca3af; }
        .card-in_progress::before { background: #3b82f6; }
        .card-completed::before { background: #10b981; }
        .card-blocked::before { background: #ef4444; }
        
        .card-title { font-size: 13px; font-weight: 500; color: #111827; line-height: 1.4; margin-bottom: 6px; padding-left: 3px; }
        .card-meta-row { display: flex; align-items: center; justify-content: space-between; margin-bottom: 7px; padding-left: 3px; }
        .exec-label { font-size: 11px; color: #9ca3af; display: flex; align-items: center; gap: 4px; }
        .card-meta-right { display: flex; align-items: center; gap: 6px; }
        .card-date { font-size: 11px; color: #9ca3af; }
        
        .pill { display: inline-flex; align-items: center; gap: 3px; padding: 2px 7px; border-radius: 5px; font-size: 11px; font-weight: 500; }
        .pill-priority-0 { background: #fee2e2; color: #b91c1c; }
        .pill-priority-1 { background: #ffedd5; color: #c2410c; }
        .pill-priority-2 { background: #fef3c7; color: #b45309; }
        .pill-priority-3 { background: #dcfce7; color: #15803d; }
        
        /* Modal */
        .modal-backdrop {
            display: none;
            position: fixed;
            inset: 0;
            background: rgba(17,24,39,0.55);
            backdrop-filter: blur(2px);
            z-index: 50;
            align-items: flex-start;
            justify-content: center;
            padding: 40px 16px 24px;
            overflow-y: auto;
        }
        .modal-backdrop.open { display: flex; }
        
        .modal-panel {
            background: #ffffff;
            border-radius: 14px;
            width: 100%;
            box-shadow: 0 24px 60px rgba(0,0,0,0.14), 0 2px 8px rgba(0,0,0,0.06);
            max-height: calc(100vh - 64px);
            animation: modal-in 0.18s ease;
        }
        @keyframes modal-in { from { transform: translateY(8px); opacity: 0; } to { transform: translateY(0); opacity: 1; } }
        
        .modal-header { padding: 18px 22px 14px; border-bottom: 1px solid #f3f4f6; display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
        .modal-title { font-size: 16px; font-weight: 600; color: #111827; letter-spacing: -0.015em; line-height: 1.35; }
        .modal-close { width: 28px; height: 28px; background: #f4f6f9; border: none; border-radius: 7px; display: flex; align-items: center; justify-content: center; cursor: pointer; color: #6b7280; }
        .modal-close:hover { background: #e5e7eb; color: #374151; }
        
        .field-label { display: block; font-size: 11.5px; font-weight: 500; color: #6b7280; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 5px; }
        .field-input { width: 100%; padding: 8px 11px; font-size: 13.5px; font-family: inherit; color: #111827; background: #f9fafb; border: 1.5px solid #e5e7eb; border-radius: 8px; outline: none; }
        .field-input:focus { border-color: #3b82f6; background: #ffffff; box-shadow: 0 0 0 3px rgba(59,130,246,0.12); }
        textarea.field-input { resize: vertical; min-height: 88px; }
        
        .status-control { display: flex; gap: 0; background: #f4f6f9; border-radius: 8px; padding: 3px; width: fit-content; }
        .status-btn { padding: 5px 12px; font-size: 12px; font-weight: 500; font-family: inherit; border: none; border-radius: 6px; cursor: pointer; background: transparent; color: #6b7280; }
        .status-btn:hover:not(.active) { color: #374151; background: rgba(0,0,0,0.04); }
        .status-btn.active { background: #ffffff; box-shadow: 0 1px 3px rgba(0,0,0,0.1); font-weight: 600; }
        
        .notes-block { background: #0f172a; border-radius: 9px; padding: 14px 16px; font-family: 'DM Mono', monospace; font-size: 12px; line-height: 1.65; color: #94a3b8; max-height: 200px; overflow-y: auto; white-space: pre-wrap; }
        
        .tab-bar { display: flex; border-bottom: 1px solid #f3f4f6; padding: 0 22px; gap: 0; }
        .tab-btn { padding: 10px 0; margin-right: 24px; font-size: 13px; font-weight: 500; background: none; border: none; cursor: pointer; position: relative; }
        .tab-btn.active { color: #2563eb; }
        .tab-btn.active::after { content: ''; position: absolute; bottom: -1px; left: 0; right: 0; height: 2px; background: #2563eb; border-radius: 2px 2px 0 0; }
        
        .modal-body { padding: 18px 22px; overflow-y: auto; flex: 1; }
        .modal-footer { display: flex; align-items: center; justify-content: space-between; padding: 14px 22px; border-top: 1px solid #f3f4f6; }
        .modal-footer-right { display: flex; gap: 8px; }
        
        #toast {
            position: fixed; bottom: 20px; right: 20px;
            background: #111827; color: #f9fafb;
            font-size: 13px; font-family: inherit;
            padding: 10px 16px; border-radius: 9px;
            box-shadow: 0 4px 16px rgba(0,0,0,0.18);
            display: none; z-index: 9999;
            max-width: 320px;
            border-left: 3px solid #3b82f6;
        }
        #toast.toast-error { border-left-color: #ef4444; }
        #toast.toast-success { border-left-color: #10b981; }
    </style>
</head>
<body>
    <div id="top-accent"></div>
    
    <header>
        <div class="header-inner">
            <div style="display:flex;align-items:center;gap:11px;">
                <div class="logo-mark">
                    <svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"/></svg>
                </div>
                <div>
                    <div class="app-title">SEO Bot</div>
                    <div class="app-subtitle">Kanban Board</div>
                </div>
            </div>
            <div style="display:flex;align-items:center;gap:6px;">
                <button onclick="refreshTasks()" class="btn btn-ghost">
                    <svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
                    Refresh
                </button>
                <button id="audit-btn" onclick="runAudit()" class="btn btn-success">
                    <svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"/></svg>
                    <span id="audit-btn-label">Run Audit</span>
                </button>
                <button id="index-audit-btn" onclick="runIndexAudit()" class="btn" style="background:#7c3aed;color:#fff;">
                    <svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                    <span id="index-audit-btn-label">Index Audit</span>
                </button>
                <button onclick="openCreateModal()" class="btn btn-primary">
                    <svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/></svg>
                    Add Task
                </button>
            </div>
        </div>
    </header>

    <main style="max-width:1400px;margin:0 auto;padding:20px 24px 40px;">
        <div class="stats-bar">
            <div class="stat-item"><div class="stat-value" id="total-count" style="color:#111827;">0</div><div class="stat-label">Total</div></div>
            <div class="stat-item"><div class="stat-value" id="pending-count" style="color:#6b7280;">0</div><div class="stat-label">Pending</div></div>
            <div class="stat-item"><div class="stat-value" id="in-progress-count" style="color:#2563eb;">0</div><div class="stat-label">In Progress</div></div>
            <div class="stat-item"><div class="stat-value" id="completed-count" style="color:#059669;">0</div><div class="stat-label">Completed</div></div>
            <div class="stat-item"><div class="stat-value" id="blocked-count" style="color:#dc2626;">0</div><div class="stat-label">Blocked</div></div>
        </div>
        
        <div class="kanban-grid">
            <div class="kanban-col">
                <div class="col-header">
                    <div class="col-title"><div class="col-dot" style="background:#9ca3af;"></div>Pending</div>
                    <span class="col-badge" id="pending-badge" style="background:#e5e7eb;color:#6b7280;">0</span>
                </div>
                <div class="col-tasks" id="pending-tasks"></div>
            </div>
            <div class="kanban-col">
                <div class="col-header">
                    <div class="col-title"><div class="col-dot" style="background:#3b82f6;"></div>In Progress</div>
                    <span class="col-badge" id="in-progress-badge" style="background:#dbeafe;color:#1d4ed8;">0</span>
                </div>
                <div class="col-tasks" id="in-progress-tasks"></div>
            </div>
            <div class="kanban-col">
                <div class="col-header">
                    <div class="col-title"><div class="col-dot" style="background:#10b981;"></div>Completed</div>
                    <span class="col-badge" id="completed-badge" style="background:#d1fae5;color:#047857;">0</span>
                </div>
                <div class="col-tasks" id="completed-tasks"></div>
            </div>
            <div class="kanban-col">
                <div class="col-header">
                    <div class="col-title"><div class="col-dot" style="background:#ef4444;"></div>Blocked</div>
                    <span class="col-badge" id="blocked-badge" style="background:#fee2e2;color:#b91c1c;">0</span>
                </div>
                <div class="col-tasks" id="blocked-tasks"></div>
            </div>
        </div>
    </main>

    <!-- Detail Modal -->
    <div id="detail-modal" class="modal-backdrop" role="dialog" aria-modal="true">
        <div class="modal-panel" style="max-width:640px;">
            <div class="modal-header">
                <div style="flex:1;min-width:0;">
                    <div style="display:flex;align-items:center;gap:6px;margin-bottom:7px;flex-wrap:wrap;">
                        <span id="detail-priority-badge" class="pill"></span>
                    </div>
                    <div class="modal-title" id="detail-title"></div>
                </div>
                <button class="modal-close" onclick="closeDetailModal()">
                    <svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
                </button>
            </div>
            <div class="tab-bar">
                <button id="tab-details" class="tab-btn active" onclick="switchTab('details')">Details</button>
                <button id="tab-comments" class="tab-btn" onclick="switchTab('comments')">Comments <span id="comment-count-badge" class="tab-count">0</span></button>
            </div>
            <div id="tab-details-panel" class="modal-body">
                <div style="margin-bottom:16px;">
                    <div class="field-label">Status</div>
                    <div class="status-control">
                        <button class="status-btn" id="status-pending" data-status="pending" onclick="setDetailStatus('pending')">Pending</button>
                        <button class="status-btn" id="status-in_progress" data-status="in_progress" onclick="setDetailStatus('in_progress')">In Progress</button>
                        <button class="status-btn" id="status-completed" data-status="completed" onclick="setDetailStatus('completed')">Completed</button>
                        <button class="status-btn" id="status-blocked" data-status="blocked" onclick="setDetailStatus('blocked')">Blocked</button>
                    </div>
                </div>
                <div style="margin-bottom:14px;">
                    <label class="field-label" for="detail-description">Description</label>
                    <textarea id="detail-description" class="field-input" rows="4" placeholder="Add a description…"></textarea>
                </div>
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px;">
                    <div>
                        <label class="field-label" for="detail-assignee">Assignee</label>
                        <input type="text" id="detail-assignee" class="field-input" placeholder="Assign to…">
                    </div>
                    <div>
                        <label class="field-label" for="detail-due_date">Due Date</label>
                        <input type="date" id="detail-due_date" class="field-input">
                    </div>
                </div>
                <div id="detail-notes-section" style="margin-bottom:14px;display:none;">
                    <label class="field-label">Agent Result</label>
                    <div id="detail-notes" class="notes-block"></div>
                </div>
                <div id="detail-actions" style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:4px;"></div>
            </div>
            <div id="tab-comments-panel" style="display:none;flex-direction:column;flex:1;overflow:hidden;min-height:0;">
                <div id="comments-list" class="modal-body comment-wrap" style="flex:1;overflow-y:auto;max-height:55vh;"></div>
                <div class="comment-input-row" style="display:flex;gap:8px;padding:14px 22px;border-top:1px solid #f3f4f6;">
                    <textarea id="new-comment-body" rows="2" placeholder="Add a comment… (⌘↵ to post)" class="field-input" style="flex:1;"></textarea>
                    <button onclick="postComment()" class="btn btn-primary" style="align-self:flex-end;">Post</button>
                </div>
            </div>
            <div class="modal-footer" id="detail-footer">
                <button onclick="deleteDetailTask()" class="btn btn-danger-ghost" style="background:transparent;color:#dc2626;border:none;font-size:13px;padding:6px 10px;">Delete task</button>
                <div class="modal-footer-right">
                    <button onclick="closeDetailModal()" class="btn btn-ghost">Cancel</button>
                    <button onclick="saveDetailTask()" class="btn btn-primary">Save changes</button>
                </div>
            </div>
        </div>
    </div>

    <!-- Create Modal -->
    <div id="create-modal" class="modal-backdrop" role="dialog" aria-modal="true">
        <div class="modal-panel" style="max-width:480px;">
            <div class="modal-header">
                <div class="modal-title">New Task</div>
                <button class="modal-close" onclick="closeCreateModal()">
                    <svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
                </button>
            </div>
            <form id="create-form" class="modal-body" style="display:flex;flex-direction:column;gap:14px;">
                <div>
                    <label class="field-label" for="cf-title">Title <span style="color:#ef4444;">*</span></label>
                    <input type="text" id="cf-title" name="title" required class="field-input" placeholder="Task title">
                </div>
                <div>
                    <label class="field-label" for="cf-description">Description</label>
                    <textarea id="cf-description" name="description" rows="3" class="field-input" placeholder="What needs to be done?"></textarea>
                </div>
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
                    <div>
                        <label class="field-label" for="cf-priority">Priority <span style="color:#9ca3af;">(0 = highest)</span></label>
                        <input type="number" id="cf-priority" name="priority" value="0" min="0" class="field-input">
                    </div>
                    <div>
                        <label class="field-label" for="cf-status">Status</label>
                        <select id="cf-status" name="status" class="field-input">
                            <option value="pending">Pending</option>
                            <option value="in_progress">In Progress</option>
                            <option value="blocked">Blocked</option>
                        </select>
                    </div>
                </div>
                <div>
                    <label class="field-label" for="cf-execution_type">Execution Type</label>
                    <select id="cf-execution_type" name="execution_type" class="field-input">
                        <option value="manual">👤 Manual (no Execute button)</option>
                        <option value="research">🔍 Research</option>
                        <option value="rewrite_title">🏷 Rewrite Title</option>
                        <option value="rewrite_meta_desc">📝 Rewrite Meta Description</option>
                        <option value="rewrite_h1">🔡 Rewrite H1</option>
                        <option value="update_schema">🧩 Update Schema / JSON-LD</option>
                        <option value="blog_write">✍️ Write Blog Post</option>
                        <option value="rewrite_blog_content">✏️ Rewrite Blog Content</option>
                        <option value="webflow_publish">🌐 Publish to Webflow</option>
                        <option value="internal_links">🔗 Add Internal Links</option>
                        <option value="alt_text">🖼 Write Alt Text</option>
                    </select>
                </div>
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
                    <div>
                        <label class="field-label" for="cf-assignee">Assignee</label>
                        <input type="text" id="cf-assignee" name="assignee" class="field-input" placeholder="Assign to">
                    </div>
                    <div>
                        <label class="field-label" for="cf-due_date">Due Date</label>
                        <input type="date" id="cf-due_date" name="due_date" class="field-input">
                    </div>
                </div>
            </form>
            <div class="modal-footer">
                <div></div>
                <div class="modal-footer-right">
                    <button type="button" onclick="closeCreateModal()" class="btn btn-ghost">Cancel</button>
                    <button type="submit" form="create-form" class="btn btn-primary">Create task</button>
                </div>
            </div>
        </div>
    </div>

    <!-- Index Audit Modal -->
    <div id="index-audit-modal" class="modal-backdrop" role="dialog" aria-modal="true" style="display:none;">
        <div class="modal-box" style="max-width:780px;width:95%;">
            <div class="modal-header">
                <div>
                    <div class="modal-title">Index Audit</div>
                    <div id="index-audit-subtitle" style="font-size:12px;color:#6b7280;margin-top:2px;"></div>
                </div>
                <button class="modal-close" onclick="closeIndexAuditModal()">
                    <svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
                </button>
            </div>
            <div id="index-audit-body" style="padding:0 24px 8px;max-height:60vh;overflow-y:auto;">
                <div id="index-audit-loading" style="text-align:center;padding:40px;color:#6b7280;">Fetching sitemap and inspecting pages… this may take a minute.</div>
                <div id="index-audit-content" style="display:none;"></div>
            </div>
            <div class="modal-footer">
                <div></div>
                <div class="modal-footer-right">
                    <button onclick="closeIndexAuditModal()" class="btn btn-ghost">Close</button>
                </div>
            </div>
        </div>
    </div>

    <div id="toast"><span id="toast-message"></span></div>

    <script>
const API_BASE = '';
let currentTasks = [];
let detailTaskId = null;
let activeTab = 'details';

async function fetchTasks() {
    try {
        const r = await fetch(API_BASE + '/tasks?limit=200');
        if (!r.ok) throw new Error('fetch failed');
        const d = await r.json();
        currentTasks = d.tasks;
        updateStats(d);
        renderTasks(d.tasks);
    } catch(e) { showToast('Error: ' + e.message, 'error'); }
}
function refreshTasks() { fetchTasks(); }

function updateStats(d) {
    document.getElementById('total-count').textContent = d.total;
    document.getElementById('pending-count').textContent = d.pending_count;
    document.getElementById('pending-badge').textContent = d.pending_count;
    document.getElementById('in-progress-count').textContent = d.in_progress_count;
    document.getElementById('in-progress-badge').textContent = d.in_progress_count;
    document.getElementById('completed-count').textContent = d.completed_count;
    document.getElementById('completed-badge').textContent = d.completed_count;
    document.getElementById('blocked-count').textContent = d.blocked_count;
    document.getElementById('blocked-badge').textContent = d.blocked_count;
}

const EXEC_LABELS = {
    webflow_publish: '🌐 Publish',
    blog_write: '✍️ Blog Write',
    internal_links: '🔗 Int. Links',
    research: '🔍 Research',
    manual: '👤 Manual',
    seo_audit: '📊 Audit',
    rewrite_title: '🏷 Title',
    rewrite_meta_desc: '📝 Meta Desc',
    rewrite_h1: '🔡 H1',
    update_schema: '🧩 Schema',
    rewrite_blog_content: '✏️ Rewrite',
    alt_text: '🖼 Alt Text',
};
const PRIORITY_PILLS = { 0: 'pill-priority-0', 1: 'pill-priority-1', 2: 'pill-priority-2', 3: 'pill-priority-3' };
const PRIORITY_LABELS = { 0: 'P0 Critical', 1: 'P1 High', 2: 'P2 Medium', 3: 'P3 Low' };

function renderTasks(tasks) {
    const cols = { pending: document.getElementById('pending-tasks'), in_progress: document.getElementById('in-progress-tasks'), completed: document.getElementById('completed-tasks'), blocked: document.getElementById('blocked-tasks') };
    Object.values(cols).forEach(c => c.innerHTML = '');
    tasks.forEach(task => {
        const card = createTaskCard(task);
        const col = cols[task.status];
        if (col) col.appendChild(card);
    });
}

function createTaskCard(task) {
    const card = document.createElement('div');
    card.className = 'task-card card-' + task.status;
    const prioClass = PRIORITY_PILLS[task.priority] || 'pill-priority-0';
    const prioLabel = PRIORITY_LABELS[task.priority] || 'P' + task.priority;
    const execLabel = task.execution_type ? (EXEC_LABELS[task.execution_type] || task.execution_type) : '';
    const commentBadge = task.comment_count > 0 ? '<span class="comment-chip">💬 ' + task.comment_count + '</span>' : '';
    const canExecute = task.execution_type && task.execution_type !== 'manual' && task.execution_type !== 'seo_audit' && task.status !== 'completed' && task.status !== 'in_progress';
    
    card.innerHTML = '<div style="display:flex;align-items:flex-start;justify-content:space-between;gap:8px;margin-bottom:6px;"><div class="card-title" style="margin:0;flex:1;">' + escapeHtml(task.title) + '</div><span class="pill ' + prioClass + '" style="flex-shrink:0;margin-top:1px;">' + prioLabel + '</span></div><div class="card-meta-row"><div class="exec-label"><span>' + (execLabel || '—') + '</span></div><div class="card-meta-right">' + commentBadge + (task.due_date ? '<span class="card-date">' + formatDate(task.due_date) + '</span>' : '') + (task.assignee ? '<span class="card-date">' + escapeHtml(task.assignee) + '</span>' : '') + '</div></div><div class="card-actions">' + (canExecute ? '<button onclick="event.stopPropagation();executeTask(' + task.id + ')" class="btn btn-sm" style="background:#4f46e5;color:#fff;">▶ Execute</button>' : '') + '<button onclick="event.stopPropagation();openDetailModal(' + task.id + ')" class="btn btn-sm btn-ghost" style="margin-left:auto;">Open →</button></div>';
    card.addEventListener('click', () => openDetailModal(task.id));
    return card;
}

async function runAudit() {
    const btn = document.getElementById('audit-btn');
    const label = document.getElementById('audit-btn-label');
    btn.disabled = true;
    label.textContent = 'Running…';
    try {
        const r = await fetch(API_BASE + '/runs/audit-' + Date.now() + '/seo-audit', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ days: 28, max_rows: 1000 }) });
        const d = await r.json();
        if (!r.ok) throw new Error(d.detail || r.statusText);
        showToast('Audit complete', 'success');
        fetchTasks();
    } catch(e) { showToast('Error: ' + e.message, 'error'); }
    finally { btn.disabled = false; label.textContent = 'Run Audit'; }
}

async function runIndexAudit() {
    const btn = document.getElementById('index-audit-btn');
    const label = document.getElementById('index-audit-btn-label');
    btn.disabled = true;
    label.textContent = 'Auditing…';

    // Show modal in loading state
    document.getElementById('index-audit-modal').style.display = 'flex';
    document.getElementById('index-audit-loading').style.display = 'block';
    document.getElementById('index-audit-content').style.display = 'none';
    document.getElementById('index-audit-subtitle').textContent = '';

    try {
        const r = await fetch(API_BASE + '/gsc/index-audit');
        const d = await r.json();
        if (!r.ok) throw new Error(d.detail || r.statusText);
        renderIndexAuditResults(d);
    } catch(e) {
        document.getElementById('index-audit-loading').innerHTML = '<span style="color:#dc2626;">Error: ' + escapeHtml(e.message) + '</span>';
    } finally {
        btn.disabled = false;
        label.textContent = 'Index Audit';
    }
}

function renderIndexAuditResults(data) {
    const loading = document.getElementById('index-audit-loading');
    const content = document.getElementById('index-audit-content');
    const subtitle = document.getElementById('index-audit-subtitle');

    subtitle.textContent = data.sitemap_url + ' — ' + data.total_inspected + ' pages inspected';
    loading.style.display = 'none';
    content.style.display = 'block';

    const s = data.summary;
    const groups = data.results;

    const COLORS = {
        indexed:     { bg: '#f0fdf4', border: '#bbf7d0', dot: '#16a34a', label: '✅ Indexed' },
        not_indexed: { bg: '#fffbeb', border: '#fde68a', dot: '#d97706', label: '⚠️ Not Indexed' },
        redirect:    { bg: '#fef3c7', border: '#fcd34d', dot: '#b45309', label: '↪️ Page with Redirect' },
        unknown:     { bg: '#f8fafc', border: '#e2e8f0', dot: '#94a3b8', label: '❓ Unknown to Google' },
        error:       { bg: '#fef2f2', border: '#fecaca', dot: '#dc2626', label: '🔴 Error' },
    };

    // Summary pills
    let html = '<div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:20px;">';
    for (const [key, cfg] of Object.entries(COLORS)) {
        const count = s[key] || 0;
        html += `<div style="display:flex;align-items:center;gap:6px;padding:6px 12px;border-radius:20px;background:${cfg.bg};border:1px solid ${cfg.border};font-size:13px;">
            <span style="width:8px;height:8px;border-radius:50%;background:${cfg.dot};flex-shrink:0;"></span>
            <span style="font-weight:600;">${count}</span>&nbsp;${cfg.label}
        </div>`;
    }
    html += '</div>';

    // Sections — only show groups with entries, prioritise problems first
    const order = ['not_indexed', 'redirect', 'unknown', 'error', 'indexed'];
    for (const key of order) {
        const pages = groups[key] || [];
        if (!pages.length) continue;
        const cfg = COLORS[key];
        html += `<div style="margin-bottom:16px;">
            <div style="font-size:13px;font-weight:600;color:#374151;margin-bottom:6px;padding:8px 10px;background:${cfg.bg};border-radius:6px;border-left:3px solid ${cfg.dot};">
                ${cfg.label} (${pages.length})
            </div>
            <div style="display:flex;flex-direction:column;gap:2px;">`;
        for (const p of pages) {
            const path = p.url.replace(/https?:\\/\\/[^/]+/, '');
            const state = p.coverage_state || p.verdict || '';
            const crawl = p.last_crawl_time ? ' · crawled ' + p.last_crawl_time.slice(0,10) : '';
            html += `<div style="display:flex;justify-content:space-between;align-items:center;padding:6px 10px;border-radius:4px;font-size:12px;background:#f9fafb;border:1px solid #f3f4f6;">
                <a href="${escapeHtml(p.url)}" target="_blank" style="color:#2563eb;text-decoration:none;font-family:monospace;word-break:break-all;">${escapeHtml(path || '/')}</a>
                <span style="color:#6b7280;white-space:nowrap;margin-left:12px;">${escapeHtml(state)}${crawl}</span>
            </div>`;
        }
        html += '</div></div>';
    }

    content.innerHTML = html;
}

function closeIndexAuditModal() {
    document.getElementById('index-audit-modal').style.display = 'none';
}

async function openDetailModal(taskId) {
    detailTaskId = taskId;
    const task = currentTasks.find(t => t.id === taskId);
    if (!task) return;
    document.getElementById('detail-title').textContent = task.title;
    const prioClass = PRIORITY_PILLS[task.priority] || 'pill-priority-0';
    const prioLabel = PRIORITY_LABELS[task.priority] || 'P' + task.priority;
    const prioBadge = document.getElementById('detail-priority-badge');
    prioBadge.textContent = prioLabel;
    prioBadge.className = 'pill ' + prioClass;
    document.getElementById('detail-description').value = task.description || '';
    document.getElementById('detail-assignee').value = task.assignee || '';
    document.getElementById('detail-due_date').value = task.due_date || '';
    setDetailStatus(task.status);
    if (task.notes) { document.getElementById('detail-notes').textContent = task.notes; document.getElementById('detail-notes-section').style.display = ''; }
    else { document.getElementById('detail-notes-section').style.display = 'none'; }
    const actionsDiv = document.getElementById('detail-actions');
    actionsDiv.innerHTML = '';
    const canExecute = task.execution_type && task.execution_type !== 'manual' && task.execution_type !== 'seo_audit' && task.status !== 'completed' && task.status !== 'in_progress';
    if (canExecute) { const b = document.createElement('button'); b.className = 'btn'; b.style.background = '#4f46e5'; b.style.color = '#fff'; b.textContent = '▶ Execute task'; b.onclick = () => executeTask(task.id); actionsDiv.appendChild(b); }
    if (task.status !== 'completed') { const b = document.createElement('button'); b.className = 'btn btn-success'; b.textContent = '✓ Mark Complete'; b.onclick = () => completeTaskFromDetail(task.id); actionsDiv.appendChild(b); }
    switchTab('details');
    document.getElementById('detail-modal').classList.add('open');
    loadComments(taskId);
}

function closeDetailModal() { document.getElementById('detail-modal').classList.remove('open'); detailTaskId = null; }
function switchTab(tab) {
    activeTab = tab;
    const detPanel = document.getElementById('tab-details-panel');
    const comPanel = document.getElementById('tab-comments-panel');
    const tabDet = document.getElementById('tab-details');
    const tabCom = document.getElementById('tab-comments');
    const footer = document.getElementById('detail-footer');
    if (tab === 'details') { detPanel.style.display = ''; comPanel.style.display = 'none'; tabDet.classList.add('active'); tabCom.classList.remove('active'); footer.style.display = ''; }
    else { detPanel.style.display = 'none'; comPanel.style.display = 'flex'; tabDet.classList.remove('active'); tabCom.classList.add('active'); footer.style.display = 'none'; loadComments(detailTaskId); }
}

async function loadComments(taskId) {
    if (!taskId) return;
    try {
        const r = await fetch(API_BASE + '/tasks/' + taskId + '/comments');
        if (!r.ok) return;
        const comments = await r.json();
        document.getElementById('comment-count-badge').textContent = comments.length;
        const list = document.getElementById('comments-list');
        list.innerHTML = '';
        if (!comments.length) { list.innerHTML = '<p style="font-size:13px;color:#9ca3af;text-align:center;padding:32px 0;">No comments yet.</p>'; return; }
        comments.forEach(c => { const div = document.createElement('div'); div.style.background = c.author === 'agent' ? '#0f172a' : '#eff6ff'; div.style.color = c.author === 'agent' ? '#94a3b8' : '#1e3a8a'; div.style.borderRadius = '10px'; div.style.padding = '11px 14px'; div.style.marginBottom = '8px'; div.innerHTML = '<div style="margin-bottom:5px;"><span style="font-size:11px;font-weight:600;text-transform:uppercase;">' + (c.author === 'agent' ? '🤖 Agent' : '👤 You') + '</span><span style="font-size:10.5px;margin-left:6px;color:' + (c.author === 'agent' ? '#475569' : '#93c5fd') + '">' + formatDateTime(c.created_at) + '</span></div><div style="white-space:pre-wrap;font-size:' + (c.author === 'agent' ? '12.5' : '13.5') + 'px;">' + escapeHtml(c.body) + '</div>'; list.appendChild(div); });
        list.scrollTop = list.scrollHeight;
    } catch(e) { console.error('loadComments error', e); }
}

async function postComment() {
    const body = document.getElementById('new-comment-body').value.trim();
    if (!body || !detailTaskId) return;
    try {
        const r = await fetch(API_BASE + '/tasks/' + detailTaskId + '/comments', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ author: 'user', body }) });
        if (!r.ok) throw new Error('failed');
        document.getElementById('new-comment-body').value = '';
        loadComments(detailTaskId);
        const task = currentTasks.find(t => t.id === detailTaskId);
        if (task) { task.comment_count = (task.comment_count || 0) + 1; renderTasks(currentTasks); }
    } catch(e) { showToast('Error: ' + e.message, 'error'); }
}

async function saveDetailTask() {
    if (!detailTaskId) return;
    const task = currentTasks.find(t => t.id === detailTaskId);
    const activeStatusBtn = document.querySelector('.status-btn.active');
    const activeStatus = activeStatusBtn?.dataset.status || task?.status || 'pending';
    const data = { title: task?.title, description: document.getElementById('detail-description').value || null, assignee: document.getElementById('detail-assignee').value || null, due_date: document.getElementById('detail-due_date').value || null, status: activeStatus };
    try {
        const r = await fetch(API_BASE + '/tasks/' + detailTaskId, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
        if (!r.ok) throw new Error('save failed');
        showToast('Changes saved', 'success');
        closeDetailModal();
        fetchTasks();
    } catch(e) { showToast('Error: ' + e.message, 'error'); }
}

function setDetailStatus(s) { ['pending','in_progress','completed','blocked'].forEach(x => { const btn = document.getElementById('status-' + x); if (x === s) btn.classList.add('active'); else btn.classList.remove('active'); }); }

async function deleteDetailTask() {
    if (!detailTaskId) return;
    if (!confirm('Delete this task?')) return;
    try { const r = await fetch(API_BASE + '/tasks/' + detailTaskId, { method: 'DELETE' }); if (!r.ok) throw new Error('delete failed'); showToast('Task deleted'); closeDetailModal(); fetchTasks(); }
    catch(e) { showToast('Error: ' + e.message, 'error'); }
}

async function completeTaskFromDetail(id) {
    try { const r = await fetch(API_BASE + '/tasks/' + id, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status: 'completed' }) }); if (!r.ok) throw new Error('failed'); showToast('Task completed', 'success'); closeDetailModal(); fetchTasks(); }
    catch(e) { showToast('Error: ' + e.message, 'error'); }
}

async function executeTask(id) {
    if (!confirm('Run the agent on this task?')) return;
    showToast('Agent is executing…');
    currentTasks = currentTasks.map(t => t.id === id ? {...t, status:'in_progress'} : t);
    renderTasks(currentTasks);
    if (detailTaskId === id) closeDetailModal();
    try {
        const r = await fetch(API_BASE + '/tasks/' + id + '/execute', { method: 'POST' });
        const d = await r.json();
        if (!r.ok) throw new Error(d.detail || r.statusText);
        showToast('Task executed', 'success');
        fetchTasks();
    } catch(e) { showToast('Error: ' + e.message, 'error'); fetchTasks(); }
}

async function createTask(formData) {
    try { const r = await fetch(API_BASE + '/tasks', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(formData) }); if (!r.ok) throw new Error('failed'); showToast('Task created', 'success'); closeCreateModal(); fetchTasks(); }
    catch(e) { showToast('Error: ' + e.message, 'error'); }
}
function openCreateModal() { document.getElementById('create-form').reset(); document.getElementById('create-modal').classList.add('open'); }
function closeCreateModal() { document.getElementById('create-modal').classList.remove('open'); }

function showToast(msg, type = '') {
    const t = document.getElementById('toast'); const m = document.getElementById('toast-message');
    m.textContent = msg; t.className = '';
    if (type === 'error') t.className = 'toast-error';
    if (type === 'success') t.className = 'toast-success';
    t.style.display = 'block';
    clearTimeout(t._timer);
    t._timer = setTimeout(() => { t.style.display = 'none'; }, 4000);
}

function escapeHtml(text) { const d = document.createElement('div'); d.textContent = text || ''; return d.innerHTML; }
function formatDate(dateStr) { if (!dateStr) return ''; return new Date(dateStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }); }
function formatDateTime(isoStr) { if (!isoStr) return ''; const d = new Date(isoStr); return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) + ' · ' + d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }); }

document.getElementById('create-form').addEventListener('submit', function(e) { e.preventDefault(); const data = Object.fromEntries(new FormData(this)); data.priority = parseInt(data.priority) || 0; createTask(data); });
document.addEventListener('keydown', function(e) { if (e.key === 'Escape') { closeDetailModal(); closeCreateModal(); } });
document.getElementById('detail-modal').addEventListener('click', function(e) { if (e.target === this) closeDetailModal(); });
document.getElementById('create-modal').addEventListener('click', function(e) { if (e.target === this) closeCreateModal(); });
document.getElementById('new-comment-body').addEventListener('keydown', function(e) { if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') postComment(); });

fetchTasks();
    </script>
</body>
</html>
"""
