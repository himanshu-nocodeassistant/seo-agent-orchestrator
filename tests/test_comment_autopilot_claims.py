"""Database-backed concurrency tests for comment autopilot claims."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from agent.api.helpers import _acquire_next_comment_action, _mark_claimed_action
from agent.db import Base, CommentActionModel, CommentModel, TaskModel


@pytest.fixture
def action_sessions(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'autopilot.sqlite'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    first, second = Session(), Session()
    now = datetime(2026, 1, 1, 0, 0, 0)
    first.add(
        TaskModel(
            title="Revise me",
            status="completed",
            execution_type="research",
            created_at=now.isoformat(),
            updated_at=now.isoformat(),
        )
    )
    first.flush()
    first.add(
        CommentModel(
            task_id=1,
            author="user",
            body="@agent revise this",
            created_at=now.isoformat(),
        )
    )
    first.commit()
    monkeypatch.setenv("COMMENT_ACTION_STALE_SECONDS", "300")
    try:
        yield first, second, now
    finally:
        first.close()
        second.close()
        engine.dispose()


def test_independent_workers_only_claim_one_comment_action(action_sessions):
    first, second, _ = action_sessions

    owner = _acquire_next_comment_action(first)
    contender = _acquire_next_comment_action(second)

    assert owner is not None
    assert owner.status == "running"
    assert contender is None
    assert second.query(CommentActionModel).one().attempts == 1


def test_stale_running_action_is_reclaimed(action_sessions):
    first, _, now = action_sessions
    action = CommentActionModel(
        task_id=1,
        comment_id=1,
        status="running",
        attempts=1,
        max_attempts=2,
        created_at=now.isoformat(),
        updated_at=(now - timedelta(minutes=6)).isoformat(),
    )
    first.add(action)
    first.commit()

    reclaimed = _acquire_next_comment_action(first)

    assert reclaimed is not None
    assert reclaimed.status == "running"
    assert reclaimed.attempts == 2


def test_old_attempt_cannot_overwrite_reclaimed_action(action_sessions):
    first, _, now = action_sessions
    action = CommentActionModel(
        task_id=1,
        comment_id=1,
        status="running",
        attempts=2,
        max_attempts=2,
        created_at=now.isoformat(),
        updated_at=now.isoformat(),
    )
    first.add(action)
    first.commit()

    assert not _mark_claimed_action(
        first,
        action.id,
        1,
        status="needs_review",
        last_error="old worker",
    )
    first.refresh(action)
    assert action.status == "running"
    assert action.attempts == 2
