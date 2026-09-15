"""Phase 1 tests: task execution claims are idempotent."""

from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from agent.api.helpers import _create_run
from agent.api.main import AgentRunModel, Base, TaskModel, get_db_session


def test_execute_persists_and_returns_request_id(client):
    task = client.post(
        "/tasks", json={"title": "Request traced", "execution_type": "research"}
    ).json()
    request_id = "req-phase1-123"

    with patch(
        "agent.api.helpers._run_agent_prompt",
        new=AsyncMock(
            return_value=SimpleNamespace(result_text="done", session_id=None)
        ),
    ):
        response = client.post(
            f"/tasks/{task['id']}/execute",
            headers={"X-Request-ID": request_id},
        )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == request_id
    assert response.json()["request_id"] == request_id

    db = get_db_session()
    try:
        run = db.query(AgentRunModel).filter_by(run_id=response.json()["run_id"]).one()
        assert run.request_id == request_id
    finally:
        db.close()


def test_duplicate_active_execute_returns_existing_run_without_agent_call(client):
    task_data = client.post(
        "/tasks", json={"title": "Already running", "execution_type": "research"}
    ).json()
    db = get_db_session()
    try:
        task = db.query(TaskModel).filter_by(id=task_data["id"]).one()
        existing = _create_run(db, task, "manual_execute", "research", request_id="first")
        existing_id = existing.run_id
    finally:
        db.close()

    with patch("agent.api.helpers._run_agent_prompt", new=AsyncMock()) as run_agent:
        response = client.post(f"/tasks/{task_data['id']}/execute")

    assert response.status_code == 200
    assert response.json()["run_id"] == existing_id
    run_agent.assert_not_awaited()


def test_two_sessions_claim_one_task_run_atomically(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'phase1.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    setup_db = session_factory()
    task = TaskModel(
        title="Concurrent claim",
        execution_type="research",
        status="pending",
        priority=0,
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
    )
    setup_db.add(task)
    setup_db.commit()
    task_id = task.id
    setup_db.close()

    def claim(request_id):
        db = session_factory()
        try:
            task = db.query(TaskModel).filter_by(id=task_id).one()
            run = _create_run(
                db, task, "manual_execute", "research", request_id=request_id
            )
            return run.run_id, getattr(run, "_claim_created", True)
        finally:
            db.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claim, ["one", "two"]))

    assert len({run_id for run_id, _ in results}) == 1
    assert sum(created for _, created in results) == 1

    db = session_factory()
    try:
        runs = db.query(AgentRunModel).filter_by(task_id=task_id).all()
        assert len(runs) == 1
    finally:
        db.close()
