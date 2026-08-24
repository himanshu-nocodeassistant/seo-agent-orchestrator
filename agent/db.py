"""Database models, session factory, and API schemas.

Extracted from the former agent/api/main.py monolith (see git history).
"""

import os
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Mapping, Optional

from pydantic import BaseModel
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    Text,
    create_engine,
    event,
)
from sqlalchemy.orm import declarative_base, sessionmaker

logger = logging.getLogger(__name__)



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
# Scalability note (#2): SQLite works for single-user and portfolio use. For production
# with concurrent workers, set DATABASE_URL to a PostgreSQL connection string — SQLAlchemy
# and the schema require no other changes. Add connection pooling via pool_size/max_overflow.
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, connection_record):
    """Enable WAL + busy timeout for SQLite so long agent runs don't lock
    the DB against concurrent API requests or campaign phases."""
    if not DATABASE_URL.startswith("sqlite"):
        return
    try:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()
    except Exception:  # pragma: no cover - pragmas are best-effort
        pass

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
    last_run_id = Column(String(64), nullable=True)
    active_run_id = Column(String(64), nullable=True)
    created_at = Column(String(20), default=lambda: _utcnow_iso())
    updated_at = Column(String(20), default=lambda: _utcnow_iso())


class CommentModel(Base):
    """Comment database model."""
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, nullable=False)
    author = Column(String(50), default="user")
    body = Column(Text, nullable=False)
    created_at = Column(String(20), default=lambda: _utcnow_iso())


class CommentActionModel(Base):
    """Tracks agent actions for triggered user comments."""
    __tablename__ = "comment_actions"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, nullable=False, index=True)
    comment_id = Column(Integer, nullable=False, unique=True, index=True)
    run_id = Column(String(64), nullable=True, index=True)
    status = Column(String(30), nullable=False, default="pending")
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=2)
    last_error = Column(Text, nullable=True)
    heartbeat_at = Column(String(20), nullable=True)
    lease_expires_at = Column(String(20), nullable=True)
    recovery_state = Column(String(30), nullable=False, default="none")
    write_capable = Column(Boolean, nullable=False, default=False)
    created_at = Column(String(20), default=lambda: _utcnow_iso())
    updated_at = Column(String(20), default=lambda: _utcnow_iso())
    acted_at = Column(String(20), nullable=True)


class AgentRunModel(Base):
    """Tracks each agent execution run."""
    __tablename__ = "agent_runs"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(String(64), nullable=False, unique=True, index=True)
    request_id = Column(String(128), nullable=True, index=True)
    heartbeat_at = Column(String(20), nullable=True)
    lease_expires_at = Column(String(20), nullable=True)
    recovery_state = Column(String(30), nullable=False, default="none")
    recovery_attempts = Column(Integer, nullable=False, default=0)
    write_capable = Column(Boolean, nullable=False, default=False)
    task_id = Column(Integer, nullable=True, index=True)
    parent_run_id = Column(String(64), nullable=True, index=True)
    status = Column(String(30), nullable=False, default="queued")
    execution_type = Column(String(50), nullable=True)
    trigger_source = Column(String(50), nullable=False, default="manual_execute")
    session_id = Column(String(255), nullable=True)
    validator_status = Column(String(30), nullable=True)
    profile_name = Column(String(50), nullable=True)
    prompt_text = Column(Text, nullable=True)
    prompt_context_json = Column(Text, nullable=True)
    result_summary = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    source_comment_id = Column(Integer, nullable=True, index=True)
    started_at = Column(String(20), default=lambda: _utcnow_iso())
    finished_at = Column(String(20), nullable=True)


class RunEventModel(Base):
    """Append-only event log for agent runs."""
    __tablename__ = "run_events"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(String(64), nullable=False, index=True)
    request_id = Column(String(128), nullable=True, index=True)
    session_id = Column(String(255), nullable=True)
    event_type = Column(String(50), nullable=False)
    payload = Column(Text, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    outcome = Column(String(30), nullable=True)
    created_at = Column(String(20), default=lambda: _utcnow_iso())


class TaskSessionModel(Base):
    """Maps a task to its most recent reusable Claude session."""
    __tablename__ = "task_sessions"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, nullable=False, unique=True, index=True)
    session_id = Column(String(255), nullable=False)
    last_run_id = Column(String(64), nullable=True)
    updated_at = Column(String(20), default=lambda: _utcnow_iso())


class OrchestrationStateModel(Base):
    """Tracks state for a multi-agent campaign orchestration run."""
    __tablename__ = "orchestration_states"

    id = Column(Integer, primary_key=True, index=True)
    orchestrator_run_id = Column(String(64), nullable=False, unique=True, index=True)
    campaign_goal = Column(Text, nullable=False)
    plan_json = Column(Text, nullable=True)
    current_phase = Column(String(50), nullable=True)
    phase_outputs_json = Column(Text, nullable=True)
    child_run_ids_json = Column(Text, nullable=True)
    status = Column(String(30), nullable=False, default="planning")
    error = Column(Text, nullable=True)
    handoff_degraded_json = Column(Text, nullable=True)
    created_at = Column(String(20), default=lambda: _utcnow_iso())
    updated_at = Column(String(20), default=lambda: _utcnow_iso())


# Create tables
Base.metadata.create_all(bind=engine)


def _ensure_orchestration_handoff_column() -> None:
    """Add handoff_degraded_json to pre-existing SQLite DBs.

    Fresh DBs get the column from the model via create_all; existing DBs
    need an ALTER TABLE. Best-effort so an old kanban.db never blocks startup.
    """
    if not DATABASE_URL.startswith("sqlite"):
        return
    try:
        with engine.connect() as conn:
            existing = [
                row[1]
                for row in conn.exec_driver_sql("PRAGMA table_info(orchestration_states)")
            ]
            if "handoff_degraded_json" not in existing:
                conn.exec_driver_sql(
                    "ALTER TABLE orchestration_states "
                    "ADD COLUMN handoff_degraded_json TEXT"
                )
            run_columns = {
                row[1]
                for row in conn.exec_driver_sql("PRAGMA table_info(agent_runs)")
            }
            if "request_id" not in run_columns:
                conn.exec_driver_sql(
                    "ALTER TABLE agent_runs ADD COLUMN request_id VARCHAR(128)"
                )
            run_column_defs = {
                "heartbeat_at": "VARCHAR(20)",
                "lease_expires_at": "VARCHAR(20)",
                "recovery_state": "VARCHAR(30) DEFAULT 'none'",
                "recovery_attempts": "INTEGER DEFAULT 0",
                "write_capable": "BOOLEAN DEFAULT 0",
            }
            for column, column_type in run_column_defs.items():
                if column not in run_columns:
                    conn.exec_driver_sql(
                        f"ALTER TABLE agent_runs ADD COLUMN {column} {column_type}"
                    )
            action_columns = {
                row[1]
                for row in conn.exec_driver_sql("PRAGMA table_info(comment_actions)")
            }
            action_column_defs = {
                "heartbeat_at": "VARCHAR(20)",
                "lease_expires_at": "VARCHAR(20)",
                "recovery_state": "VARCHAR(30) DEFAULT 'none'",
                "write_capable": "BOOLEAN DEFAULT 0",
            }
            for column, column_type in action_column_defs.items():
                if column not in action_columns:
                    conn.exec_driver_sql(
                        f"ALTER TABLE comment_actions ADD COLUMN {column} {column_type}"
                    )
            event_columns = {
                row[1]
                for row in conn.exec_driver_sql("PRAGMA table_info(run_events)")
            }
            event_column_defs = {
                "request_id": "VARCHAR(128)",
                "session_id": "VARCHAR(255)",
                "duration_ms": "INTEGER",
                "outcome": "VARCHAR(30)",
            }
            for column, column_type in event_column_defs.items():
                if column not in event_columns:
                    conn.exec_driver_sql(
                        f"ALTER TABLE run_events ADD COLUMN {column} {column_type}"
                    )
            conn.commit()
    except Exception as e:  # pragma: no cover - best-effort migration
        logger.warning("Could not ensure handoff_degraded_json column: %s", e)


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
    last_run_id: Optional[str]
    active_run_id: Optional[str]
    created_at: str
    updated_at: str
    resume_available: bool = False


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


class RunResponse(BaseModel):
    run_id: str
    request_id: Optional[str]
    heartbeat_at: Optional[str]
    lease_expires_at: Optional[str]
    recovery_state: Optional[str]
    recovery_attempts: Optional[int]
    write_capable: bool = False
    task_id: Optional[int]
    status: str
    execution_type: Optional[str]
    trigger_source: str
    session_id: Optional[str]
    validator_status: Optional[str]
    profile_name: Optional[str]
    error: Optional[str]
    started_at: str
    finished_at: Optional[str]


class TaskMemoryResponse(BaseModel):
    task_id: int
    run_id: Optional[str]
    execution_type: Optional[str]
    memory: dict


class SeoAuditRequest(BaseModel):
    """Body for POST /runs/{run_id}/seo-audit."""

    days: int = 28


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



def _utcnow_iso() -> str:
    """Naive UTC ISO timestamp (matches legacy datetime.utcnow output)."""
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
