"""Phase 6 tests: comment autopilot claims survive crashes."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from agent.api.helpers import (
    _acquire_next_comment_action,
    _utcnow_iso,
    process_one_comment_action,
)
from agent.api.main import CommentActionModel, CommentModel, TaskModel, get_db_session


def _old_timestamp(minutes=16):
    return (datetime.utcnow() - timedelta(minutes=minutes)).isoformat()


def _create_trigger(client, execution_type="research"):
    task = client.post(
        "/tasks", json={"title": "Comment task", "execution_type": execution_type}
    ).json()
    comment = client.post(
        f"/tasks/{task['id']}/comments",
        json={"author": "user", "body": "@agent update this"},
    ).json()
    return task, comment


def test_comment_action_claim_has_lease_and_is_single_use(client):
    task_data, comment_data = _create_trigger(client)
    db = get_db_session()
    try:
        first = _acquire_next_comment_action(db)
        second = _acquire_next_comment_action(db)

        assert first is not None
        assert first.comment_id == comment_data["id"]
        assert first.heartbeat_at
        assert first.lease_expires_at
        assert second is None
    finally:
        db.close()


def test_stale_read_only_action_is_reclaimed(client):
    task_data, comment_data = _create_trigger(client)
    db = get_db_session()
    try:
        action = _acquire_next_comment_action(db)
        action.heartbeat_at = _old_timestamp()
        action.lease_expires_at = _old_timestamp()
        db.commit()

        reclaimed = _acquire_next_comment_action(db)

        assert reclaimed is not None
        assert reclaimed.id == action.id
        assert reclaimed.attempts == 2
        assert reclaimed.recovery_state == "running"
    finally:
        db.close()


def test_stale_write_action_requires_review(client):
    task_data, comment_data = _create_trigger(client, execution_type="rewrite_title")
    db = get_db_session()
    try:
        action = _acquire_next_comment_action(db)
        action.heartbeat_at = _old_timestamp()
        action.lease_expires_at = _old_timestamp()
        db.commit()

        assert _acquire_next_comment_action(db) is None
        db.refresh(action)
        assert action.status == "review_required"
        assert action.recovery_state == "review_required"
        assert action.last_error
    finally:
        db.close()


@pytest.mark.asyncio
async def test_worker_cycle_survives_unexpected_error():
    with patch(
        "agent.api.helpers.process_one_comment_action",
        new=AsyncMock(side_effect=RuntimeError("unexpected worker error")),
    ), patch("agent.api.helpers.logger.exception") as log:
        from agent.api.helpers import run_comment_autopilot_cycle

        result = await run_comment_autopilot_cycle()

    assert result["processed"] is False
    assert result["reason"] == "worker_error"
    log.assert_called_once()
