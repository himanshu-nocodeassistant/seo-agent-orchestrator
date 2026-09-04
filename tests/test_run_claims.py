"""External-behaviour tests for database-backed run claims.

These tests intentionally use a file-backed SQLite database and independent
sessions.  A process-local mutex cannot make the concurrency assertions pass.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from agent.db import AgentRunModel, Base, RunLeaseModel, TaskModel
from agent.run_claims import (
    IdempotencyConflict,
    LeaseLost,
    NeedsReview,
    RunClaimConflict,
    RunClaimService,
)


def _utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None)


@pytest.fixture
def db_sessions(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'claims.sqlite'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    first, second = Session(), Session()
    now = _utc(datetime.now(timezone.utc))
    first.add(
        TaskModel(
            title="Claim me",
            status="pending",
            execution_type="research",
            created_at=now.isoformat(),
            updated_at=now.isoformat(),
        )
    )
    first.commit()
    try:
        yield first, second, 1
    finally:
        first.close()
        second.close()
        engine.dispose()


def test_only_one_worker_can_claim_a_task(db_sessions):
    first, second, task_id = db_sessions
    def clock():
        return datetime(2026, 1, 1, tzinfo=timezone.utc)
    owner = RunClaimService(first, clock=clock).acquire(
        task_id, idempotency_key="request-a", fingerprint="execute:research"
    )

    with pytest.raises(RunClaimConflict) as error:
        RunClaimService(second, clock=clock).acquire(
            task_id, idempotency_key="request-b", fingerprint="execute:research"
        )

    assert error.value.active_run_id == owner.run_id
    assert error.value.status == "running"
    assert second.query(AgentRunModel).count() == 1


def test_same_key_replays_the_original_run_without_new_work(db_sessions):
    first, second, task_id = db_sessions
    def clock():
        return datetime(2026, 1, 1, tzinfo=timezone.utc)
    owner = RunClaimService(first, clock=clock).acquire(
        task_id, idempotency_key="request-a", fingerprint="execute:research"
    )

    replay = RunClaimService(second, clock=clock).acquire(
        task_id, idempotency_key="request-a", fingerprint="execute:research"
    )

    assert replay.replayed is True
    assert replay.run_id == owner.run_id
    assert second.query(AgentRunModel).count() == 1


def test_reusing_a_key_with_a_different_request_is_rejected(db_sessions):
    first, second, task_id = db_sessions
    service = RunClaimService(first)
    service.acquire(task_id, idempotency_key="request-a", fingerprint="execute:research")

    with pytest.raises(IdempotencyConflict):
        RunClaimService(second).acquire(
            task_id, idempotency_key="request-a", fingerprint="execute:content"
        )


def test_lease_timeout_is_configurable_and_stale_claim_can_be_replaced(db_sessions):
    first, second, task_id = db_sessions
    current = [datetime(2026, 1, 1, tzinfo=timezone.utc)]
    def clock():
        return current[0]
    owner = RunClaimService(first, lease_timeout=timedelta(seconds=300), clock=clock).acquire(
        task_id, idempotency_key="request-a", fingerprint="execute:research"
    )

    current[0] += timedelta(seconds=299)
    with pytest.raises(RunClaimConflict):
        RunClaimService(second, lease_timeout=timedelta(seconds=300), clock=clock).acquire(
            task_id, idempotency_key="request-b", fingerprint="execute:research"
        )

    current[0] += timedelta(seconds=2)
    replacement = RunClaimService(
        second, lease_timeout=timedelta(seconds=300), clock=clock
    ).acquire(task_id, idempotency_key="request-b", fingerprint="execute:research")
    assert replacement.run_id != owner.run_id
    assert second.query(AgentRunModel).filter_by(run_id=owner.run_id).one().status == "expired"


def test_heartbeat_extends_only_the_current_lease(db_sessions):
    first, second, task_id = db_sessions
    def clock():
        return datetime(2026, 1, 1, tzinfo=timezone.utc)
    owner = RunClaimService(first, clock=clock).acquire(
        task_id, idempotency_key="request-a", fingerprint="execute:research"
    )
    before = owner.expires_at

    assert RunClaimService(first, clock=lambda: datetime(2026, 1, 1, 0, 1, tzinfo=timezone.utc)).heartbeat(
        task_id, owner.run_id, owner.owner_token, owner.fence_version
    )
    assert first.query(RunLeaseModel).filter_by(task_id=task_id).one().expires_at > before
    assert not RunClaimService(second).heartbeat(
        task_id, owner.run_id, "wrong-owner", owner.fence_version
    )


def test_stale_worker_cannot_finalize_after_fenced_reclaim(db_sessions):
    first, second, task_id = db_sessions
    current = [datetime(2026, 1, 1, tzinfo=timezone.utc)]
    def clock():
        return current[0]
    old = RunClaimService(first, clock=clock).acquire(
        task_id, idempotency_key="request-a", fingerprint="execute:research"
    )
    current[0] += timedelta(minutes=6)
    new = RunClaimService(second, clock=clock).acquire(
        task_id, idempotency_key="request-b", fingerprint="execute:research"
    )

    with pytest.raises(LeaseLost):
        RunClaimService(first, clock=clock).finalize(
            task_id, old.run_id, old.owner_token, old.fence_version, status="completed"
        )
    RunClaimService(second, clock=clock).finalize(
        task_id, new.run_id, new.owner_token, new.fence_version, status="completed"
    )
    assert second.query(AgentRunModel).filter_by(run_id=new.run_id).one().status == "completed"


def test_stale_write_capable_run_requires_review_and_explicit_acknowledgement(db_sessions):
    first, second, task_id = db_sessions
    current = [datetime(2026, 1, 1, tzinfo=timezone.utc)]
    def clock():
        return current[0]
    RunClaimService(first, clock=clock).acquire(
        task_id,
        idempotency_key="request-a",
        fingerprint="execute:publish",
        write_capable=True,
    )
    current[0] += timedelta(minutes=6)

    with pytest.raises(NeedsReview):
        RunClaimService(second, clock=clock).acquire(
            task_id,
            idempotency_key="request-b",
            fingerprint="execute:publish",
            write_capable=True,
        )
    assert second.get(TaskModel, task_id).status == "blocked"

    resumed = RunClaimService(second, clock=clock).acquire(
        task_id,
        idempotency_key="request-c",
        fingerprint="execute:publish",
        write_capable=True,
        acknowledge_stale=True,
    )
    assert resumed.run_id
    assert resumed.replayed is False


def test_legacy_active_pointer_requires_explicit_review(db_sessions):
    first, _, task_id = db_sessions
    task = first.query(TaskModel).filter_by(id=task_id).one()
    task.active_run_id = "legacy-run-without-lease"
    first.commit()

    with pytest.raises(NeedsReview):
        RunClaimService(first).acquire(
            task_id,
            idempotency_key="new-request",
            fingerprint="execute:research",
        )

    claim = RunClaimService(first).acquire(
        task_id,
        idempotency_key="acknowledged-request",
        fingerprint="execute:research:acknowledged",
        acknowledge_stale=True,
    )
    assert claim.run_id


def test_expired_active_campaign_cannot_resume_as_approval_pause(db_sessions):
    first, _, task_id = db_sessions
    current = [datetime(2026, 1, 1, tzinfo=timezone.utc)]
    service = RunClaimService(first, clock=lambda: current[0])
    claim = service.acquire(
        task_id,
        idempotency_key="campaign-start",
        fingerprint="campaign:start",
        execution_type="orchestrate_seo_campaign",
        write_capable=True,
    )
    current[0] += timedelta(minutes=6)

    with pytest.raises(NeedsReview):
        service.acquire_resume(
            task_id,
            claim.run_id,
            idempotency_key="campaign-resume",
            fingerprint="campaign:resume",
        )

    assert first.query(AgentRunModel).filter_by(run_id=claim.run_id).one().status == "needs_review"
