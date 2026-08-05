"""
Test configuration and fixtures.

Sets up an in-memory SQLite database for all tests so the production
kanban.db is never touched during test runs.

Uses StaticPool so all connections share the same in-memory database —
without this, each new connection gets a fresh empty DB and tables vanish.
"""
import os
import json

# Must be set before agent.api.main is imported
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["COMMENT_AUTOPILOT_ENABLED"] = "false"
os.environ["AGENT_EXECUTION_TIMEOUT_SECONDS"] = "2"
# Keep cost-triggering endpoints effectively unlimited for the shared
# TestClient limiter key; the rate-limit test lowers this per-test.
os.environ["API_RATE_LIMIT_EXECUTE"] = "100000/minute"

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


@pytest.fixture
def fake_credentials_path(tmp_path):
    """Create a fake (non-functional) Google service-account JSON file.

    Config validation only checks that the file exists; tests that actually
    build a service mock out the credentials/discovery layer.
    """
    creds = {
        "type": "service_account",
        "project_id": "test-project",
        "private_key_id": "test-key-id",
        "private_key": (
            "-----BEGIN PRIVATE KEY-----\n"
            "MIIBVQIBADANBgkqhkiG9w0BAQEFAASCAT8wggE7AgEAAkEAsda5VzP1A6xQvQ9w\n"
            "-----END PRIVATE KEY-----\n"
        ),
        "client_email": "test@test-project.iam.gserviceaccount.com",
        "client_id": "123456789",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": (
            "https://www.googleapis.com/robot/v1/metadata/x509/"
            "test%40test-project.iam.gserviceaccount.com"
        ),
    }
    path = tmp_path / "test-service-account.json"
    path.write_text(json.dumps(creds))
    return path
