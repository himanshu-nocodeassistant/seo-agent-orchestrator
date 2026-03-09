"""
Test configuration and fixtures.

Sets up an in-memory SQLite database for all tests so the production
kanban.db is never touched during test runs.

Uses StaticPool so all connections share the same in-memory database —
without this, each new connection gets a fresh empty DB and tables vanish.
"""
import os

# Must be set before agent.api.main is imported
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["COMMENT_AUTOPILOT_ENABLED"] = "false"
os.environ["AGENT_EXECUTION_TIMEOUT_SECONDS"] = "2"

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import pytest
from fastapi.testclient import TestClient
import agent.api.main as main_module

# StaticPool ensures all connections reuse the same in-memory SQLite database
_test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_test_session_factory = sessionmaker(autocommit=False, autoflush=False, bind=_test_engine)

# Patch module-level globals
main_module.engine = _test_engine
main_module.SessionLocal = _test_session_factory

# Create all tables in the shared in-memory database
main_module.Base.metadata.create_all(bind=_test_engine)


@pytest.fixture(scope="session")
def client():
    """TestClient backed by an in-memory SQLite database."""
    from agent.api.main import app
    with TestClient(app) as c:
        yield c
