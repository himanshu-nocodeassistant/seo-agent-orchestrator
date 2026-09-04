"""Database-backed run claims.

This module is deliberately independent of the HTTP and worker layers.  It
provides one small interface for claiming work, renewing the claim, and
fencing old workers after a lease is replaced.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from agent.db import (
    AgentRunModel,
    ExecuteRequestModel,
    RunEventModel,
    RunLeaseModel,
    TaskModel,
)


Clock = Callable[[], datetime]
logger = logging.getLogger(__name__)


def _utc_naive(value: datetime) -> datetime:
    """Convert an aware or naive datetime to the DB's naive UTC format."""
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _default_clock() -> datetime:
    return datetime.now(timezone.utc)


class RunClaimConflict(RuntimeError):
    """A different request is already running for the task."""

    def __init__(self, active_run_id: str, status: str = "running") -> None:
        self.active_run_id = active_run_id
        self.status = status
        super().__init__(f"Task already has active run {active_run_id} ({status})")


class IdempotencyConflict(RuntimeError):
    """An idempotency key was reused for a different request."""


class NeedsReview(RuntimeError):
    """A stale write-capable worker may have changed an external system."""

    def __init__(self, active_run_id: str) -> None:
        self.active_run_id = active_run_id
        self.status = "needs_review"
        super().__init__(f"Stale run {active_run_id} requires review")


class LeaseLost(RuntimeError):
    """The caller no longer owns the current fenced lease."""


@dataclass(frozen=True)
class RunClaim:
    task_id: int
    run_id: str
    owner_token: str
    fence_version: int
    status: str
    expires_at: Optional[datetime]
    replayed: bool = False


class RunClaimService:
    """Acquire and mutate a task run with durable, fenced ownership."""

    def __init__(
        self,
        db,
        *,
        lease_timeout: timedelta | None = None,
        clock: Clock | None = None,
    ) -> None:
        self.db = db
        if lease_timeout is None:
            timeout_seconds = float(os.getenv("RUN_LEASE_TIMEOUT_SECONDS", "300"))
            lease_timeout = timedelta(seconds=timeout_seconds)
        if lease_timeout <= timedelta(0):
            raise ValueError("lease_timeout must be positive")
        self.lease_timeout = lease_timeout
        self.clock = clock or _default_clock

    def acquire(
        self,
        task_id: int,
        *,
        idempotency_key: str,
        fingerprint: str,
        request_scope: str | None = None,
        execution_type: str | None = None,
        trigger_source: str = "manual_execute",
        write_capable: bool = False,
        acknowledge_stale: bool = False,
    ) -> RunClaim:
        """Atomically replay, reject, or create a run claim for ``task_id``."""
        if not idempotency_key or not idempotency_key.strip():
            raise ValueError("idempotency_key is required")
        if not fingerprint:
            raise ValueError("fingerprint is required")
        scope = request_scope or f"task:{task_id}"
        now = _utc_naive(self.clock())

        # SQLite does not support row-level SELECT ... FOR UPDATE.  A short
        # write transaction gives the claim check the same serialization as
        # the row lock used by PostgreSQL, while the unique task constraint
        # remains the final guard for every database.
        bind = self.db.get_bind()
        if bind.dialect.name == "sqlite":
            # Endpoint handlers normally read the task first, which opens a
            # read transaction.  Reset it before taking SQLite's writer lock;
            # otherwise two workers can both observe an empty lease row.
            self.db.rollback()
            self.db.connection().exec_driver_sql("BEGIN IMMEDIATE")

        request = (
            self.db.query(ExecuteRequestModel)
            .filter_by(request_scope=scope, idempotency_key=idempotency_key)
            .one_or_none()
        )
        if request is not None:
            if request.task_id != task_id or request.fingerprint != fingerprint:
                raise IdempotencyConflict(
                    f"Idempotency key {idempotency_key!r} was used for another request"
                )
            run = self.db.query(AgentRunModel).filter_by(run_id=request.run_id).one()
            lease = self.db.query(RunLeaseModel).filter_by(task_id=task_id).one_or_none()
            return self._claim(run, lease, replayed=True)

        task = self.db.query(TaskModel).filter_by(id=task_id).one_or_none()
        if task is None:
            raise ValueError(f"Task {task_id} not found")
        lease_query = self.db.query(RunLeaseModel).filter_by(task_id=task_id)
        if bind.dialect.name != "sqlite":
            lease_query = lease_query.with_for_update()
        lease = lease_query.one_or_none()

        # A legacy deployment can contain an active pointer without lease
        # metadata. Do not assume that work is idle. An operator must first
        # verify external state and explicitly acknowledge recovery.
        if lease is None and task.active_run_id:
            if not acknowledge_stale:
                task.status = "blocked"
                task.updated_at = now.isoformat()
                self.db.commit()
                raise NeedsReview(task.active_run_id)
            task.active_run_id = None

        if lease is not None and lease.status == "needs_review" and not acknowledge_stale:
            raise NeedsReview(lease.run_id)

        if lease is not None and lease.status == "paused":
            run = self.db.query(AgentRunModel).filter_by(run_id=lease.run_id).one()
            raise RunClaimConflict(lease.run_id, "awaiting_approval")

        if lease is not None and lease.status == "active":
            if lease.expires_at > now:
                run = self.db.query(AgentRunModel).filter_by(run_id=lease.run_id).one()
                raise RunClaimConflict(lease.run_id, run.status)
            prior_run = (
                self.db.query(AgentRunModel).filter_by(run_id=lease.run_id).one_or_none()
            )
            if write_capable and not acknowledge_stale:
                lease.status = "needs_review"
                if prior_run is not None:
                    prior_run.status = "needs_review"
                    prior_run.finished_at = now.isoformat()
                task.status = "blocked"
                task.updated_at = now.isoformat()
                self._add_event(
                    lease.run_id,
                    "run_needs_review",
                    {"reason": "stale_write_capable_lease"},
                    now,
                )
                self.db.commit()
                raise NeedsReview(lease.run_id)
            if prior_run is not None:
                prior_run.status = "expired"
                prior_run.finished_at = now.isoformat()
                self._add_event(
                    prior_run.run_id,
                    "run_expired",
                    {"reason": "stale_lease_reclaimed"},
                    now,
                )

        run_id = uuid.uuid4().hex
        owner_token = secrets.token_urlsafe(32)
        prior_fence = lease.fence_version if lease is not None else 0
        run = AgentRunModel(
            run_id=run_id,
            task_id=task_id,
            status="running",
            execution_type=execution_type or task.execution_type,
            trigger_source=trigger_source,
            started_at=now.isoformat(),
        )
        request = ExecuteRequestModel(
            request_scope=scope,
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            task_id=task_id,
            run_id=run_id,
            created_at=now,
        )
        if lease is None:
            lease = RunLeaseModel(
                task_id=task_id,
                run_id=run_id,
                owner_token=owner_token,
                fence_version=1,
                status="active",
                acquired_at=now,
                heartbeat_at=now,
                expires_at=now + self.lease_timeout,
            )
            self.db.add(lease)
        else:
            lease.run_id = run_id
            lease.owner_token = owner_token
            lease.fence_version = prior_fence + 1
            lease.status = "active"
            lease.acquired_at = now
            lease.heartbeat_at = now
            lease.expires_at = now + self.lease_timeout
            lease.released_at = None

        self.db.add(run)
        self.db.add(request)
        self._add_event(run_id, "run_created", {"trigger_source": trigger_source}, now)
        self._add_event(
            run_id,
            "run_claimed",
            {"task_id": task_id, "fence_version": prior_fence + 1},
            now,
        )
        task.active_run_id = run_id
        task.last_run_id = run_id
        task.updated_at = now.isoformat()
        try:
            self.db.commit()
        except IntegrityError:
            # Another worker won the unique task/key race.  Its committed row
            # is now the authoritative answer for this request.
            self.db.rollback()
            winner_request = (
                self.db.query(ExecuteRequestModel)
                .filter_by(request_scope=scope, idempotency_key=idempotency_key)
                .one_or_none()
            )
            if winner_request is not None:
                if winner_request.task_id != task_id or winner_request.fingerprint != fingerprint:
                    raise IdempotencyConflict(
                        f"Idempotency key {idempotency_key!r} was used for another request"
                    )
                winner_run = (
                    self.db.query(AgentRunModel).filter_by(run_id=winner_request.run_id).one()
                )
                winner_lease = (
                    self.db.query(RunLeaseModel).filter_by(task_id=task_id).one_or_none()
                )
                return self._claim(winner_run, winner_lease, replayed=True)
            winner_lease = self.db.query(RunLeaseModel).filter_by(task_id=task_id).one_or_none()
            if winner_lease is not None and winner_lease.status == "active":
                winner_run = (
                    self.db.query(AgentRunModel).filter_by(run_id=winner_lease.run_id).one()
                )
                raise RunClaimConflict(winner_lease.run_id, winner_run.status)
            raise
        return self._claim(run, lease)

    def pause(
        self, task_id: int, run_id: str, owner_token: str, fence_version: int
    ) -> None:
        """Park an approval-paused run without allowing a fresh start."""
        now = _utc_naive(self.clock())
        result = self.db.execute(
            update(RunLeaseModel)
            .where(
                RunLeaseModel.task_id == task_id,
                RunLeaseModel.run_id == run_id,
                RunLeaseModel.owner_token == owner_token,
                RunLeaseModel.fence_version == fence_version,
                RunLeaseModel.status == "active",
                RunLeaseModel.expires_at > now,
            )
            .values(status="paused", released_at=now)
        )
        if result.rowcount != 1:
            self.db.rollback()
            raise LeaseLost(f"Run {run_id} no longer owns task {task_id}")
        self.db.commit()

    def acquire_resume(
        self,
        task_id: int,
        run_id: str,
        *,
        idempotency_key: str,
        fingerprint: str,
    ) -> RunClaim:
        """Claim the existing approval-paused run for a resume request."""
        if not idempotency_key or not idempotency_key.strip():
            raise ValueError("idempotency_key is required")
        if not fingerprint:
            raise ValueError("fingerprint is required")
        scope = f"task:{task_id}"
        now = _utc_naive(self.clock())
        if self.db.get_bind().dialect.name == "sqlite":
            self.db.rollback()
            self.db.connection().exec_driver_sql("BEGIN IMMEDIATE")
        request = (
            self.db.query(ExecuteRequestModel)
            .filter_by(request_scope=scope, idempotency_key=idempotency_key)
            .one_or_none()
        )
        if request is not None:
            if request.task_id != task_id or request.fingerprint != fingerprint:
                raise IdempotencyConflict(
                    f"Idempotency key {idempotency_key!r} was used for another request"
                )
            run = self.db.query(AgentRunModel).filter_by(run_id=request.run_id).one()
            lease = self.db.query(RunLeaseModel).filter_by(task_id=task_id).one_or_none()
            return self._claim(run, lease, replayed=True)

        run = self.db.query(AgentRunModel).filter_by(run_id=run_id, task_id=task_id).one_or_none()
        lease_query = self.db.query(RunLeaseModel).filter_by(task_id=task_id)
        if self.db.get_bind().dialect.name != "sqlite":
            lease_query = lease_query.with_for_update()
        lease = lease_query.one_or_none()
        if run is None or lease is None or lease.run_id != run_id:
            raise ValueError("Campaign run cannot be resumed")
        if lease.status == "active" and lease.expires_at > now:
            raise RunClaimConflict(run_id, run.status)
        if lease.status == "active":
            lease.status = "needs_review"
            run.status = "needs_review"
            run.finished_at = now.isoformat()
            task = self.db.query(TaskModel).filter_by(id=task_id).one()
            task.status = "blocked"
            task.updated_at = now.isoformat()
            self.db.commit()
            raise NeedsReview(run_id)
        if lease.status != "paused":
            raise ValueError("Campaign run cannot be resumed")

        owner_token = secrets.token_urlsafe(32)
        lease.run_id = run_id
        lease.owner_token = owner_token
        lease.fence_version += 1
        lease.status = "active"
        lease.acquired_at = now
        lease.heartbeat_at = now
        lease.expires_at = now + self.lease_timeout
        lease.released_at = None
        self.db.add(
            ExecuteRequestModel(
                request_scope=scope,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                task_id=task_id,
                run_id=run_id,
                created_at=now,
            )
        )
        task = self.db.query(TaskModel).filter_by(id=task_id).one()
        task.active_run_id = run_id
        task.updated_at = now.isoformat()
        self._add_event(
            run_id,
            "run_resumed",
            {"task_id": task_id, "fence_version": lease.fence_version},
            now,
        )
        self.db.commit()
        return self._claim(run, lease)

    def heartbeat(
        self, task_id: int, run_id: str, owner_token: str, fence_version: int
    ) -> bool:
        now = _utc_naive(self.clock())
        result = self.db.execute(
            update(RunLeaseModel)
            .where(
                RunLeaseModel.task_id == task_id,
                RunLeaseModel.run_id == run_id,
                RunLeaseModel.owner_token == owner_token,
                RunLeaseModel.fence_version == fence_version,
                RunLeaseModel.status == "active",
                RunLeaseModel.expires_at > now,
            )
            .values(heartbeat_at=now, expires_at=now + self.lease_timeout)
        )
        if result.rowcount != 1:
            self.db.rollback()
            return False
        self._add_event(
            run_id,
            "lease_renewed",
            {"task_id": task_id, "fence_version": fence_version},
            now,
        )
        self.db.commit()
        return True

    def assert_ownership(
        self, task_id: int, run_id: str, owner_token: str, fence_version: int
    ) -> RunLeaseModel:
        now = _utc_naive(self.clock())
        lease = (
            self.db.query(RunLeaseModel)
            .filter_by(
                task_id=task_id,
                run_id=run_id,
                owner_token=owner_token,
                fence_version=fence_version,
                status="active",
            )
            .one_or_none()
        )
        if lease is None or lease.expires_at <= now:
            raise LeaseLost(f"Run {run_id} no longer owns task {task_id}")
        return lease

    def finalize(
        self,
        task_id: int,
        run_id: str,
        owner_token: str,
        fence_version: int,
        *,
        status: str,
        result_summary: str | None = None,
        error: str | None = None,
        validator_status: str | None = None,
        session_id: str | None = None,
        task_status: str | None = None,
        task_notes: str | None = None,
    ) -> None:
        now = _utc_naive(self.clock())
        lease_result = self.db.execute(
            update(RunLeaseModel)
            .where(
                RunLeaseModel.task_id == task_id,
                RunLeaseModel.run_id == run_id,
                RunLeaseModel.owner_token == owner_token,
                RunLeaseModel.fence_version == fence_version,
                RunLeaseModel.status == "active",
                RunLeaseModel.expires_at > now,
            )
            .values(status="released", released_at=now)
        )
        if lease_result.rowcount != 1:
            self.db.rollback()
            raise LeaseLost(f"Run {run_id} no longer owns task {task_id}")
        run_values = {
            "status": status,
            "result_summary": result_summary,
            "error": error,
            "finished_at": now.isoformat(),
        }
        if validator_status is not None:
            run_values["validator_status"] = validator_status
        if session_id is not None:
            run_values["session_id"] = session_id
        self.db.execute(
            update(AgentRunModel)
            .where(AgentRunModel.run_id == run_id, AgentRunModel.task_id == task_id)
            .values(**run_values)
        )
        task_values = {
            "active_run_id": None,
            "last_run_id": run_id,
            "updated_at": now.isoformat(),
        }
        if task_status is not None:
            task_values["status"] = task_status
        if task_notes is not None:
            task_values["notes"] = task_notes
        self.db.execute(
            update(TaskModel)
            .where(TaskModel.id == task_id, TaskModel.active_run_id == run_id)
            .values(**task_values)
        )
        self._add_event(
            run_id,
            "lease_released",
            {"task_id": task_id, "fence_version": fence_version, "run_status": status},
            now,
        )
        self.db.commit()

    def release(self, task_id: int, run_id: str, owner_token: str, fence_version: int) -> None:
        now = _utc_naive(self.clock())
        result = self.db.execute(
            update(RunLeaseModel)
            .where(
                RunLeaseModel.task_id == task_id,
                RunLeaseModel.run_id == run_id,
                RunLeaseModel.owner_token == owner_token,
                RunLeaseModel.fence_version == fence_version,
                RunLeaseModel.status == "active",
                RunLeaseModel.expires_at > now,
            )
            .values(status="released", released_at=now)
        )
        if result.rowcount != 1:
            self.db.rollback()
            raise LeaseLost(f"Run {run_id} no longer owns task {task_id}")
        self.db.execute(
            update(TaskModel)
            .where(TaskModel.id == task_id, TaskModel.active_run_id == run_id)
            .values(active_run_id=None, updated_at=now.isoformat())
        )
        self._add_event(
            run_id,
            "lease_released",
            {"task_id": task_id, "fence_version": fence_version},
            now,
        )
        self.db.commit()

    def _add_event(self, run_id: str, event_type: str, payload: dict, now: datetime) -> None:
        self.db.add(
            RunEventModel(
                run_id=run_id,
                event_type=event_type,
                payload=json.dumps(payload, sort_keys=True),
                created_at=now.isoformat(),
            )
        )

    @staticmethod
    def _claim(run: AgentRunModel, lease: RunLeaseModel | None, replayed: bool = False) -> RunClaim:
        if lease is None or lease.run_id != run.run_id or lease.status != "active":
            lease = None
        return RunClaim(
            task_id=run.task_id,
            run_id=run.run_id,
            owner_token=lease.owner_token if lease else "",
            fence_version=lease.fence_version if lease else 0,
            status=run.status,
            expires_at=lease.expires_at if lease else None,
            replayed=replayed,
        )


@asynccontextmanager
async def lease_heartbeat(claim: RunClaim):
    """Renew an active lease while an awaited agent operation is running.

    Each renewal uses a separate session. The request session is never shared
    with the heartbeat task. Finalization still checks the fence token.
    """
    if claim.replayed or not claim.owner_token:
        yield
        return

    timeout_seconds = max(float(os.getenv("RUN_LEASE_TIMEOUT_SECONDS", "300")), 1.0)
    interval_seconds = max(timeout_seconds / 3.0, 1.0)
    stopped = asyncio.Event()

    async def _renew() -> None:
        while True:
            try:
                await asyncio.wait_for(stopped.wait(), timeout=interval_seconds)
                return
            except asyncio.TimeoutError:
                pass
            from agent import db as db_module

            heartbeat_db = db_module.get_db_session()
            try:
                renewed = RunClaimService(heartbeat_db).heartbeat(
                    claim.task_id,
                    claim.run_id,
                    claim.owner_token,
                    claim.fence_version,
                )
                if not renewed:
                    logger.warning("Lease heartbeat lost ownership for run %s", claim.run_id)
                    lost.set()
                    protected_task.cancel()
                    return
            finally:
                heartbeat_db.close()

    lost = asyncio.Event()
    protected_task = asyncio.current_task()
    heartbeat_task = asyncio.create_task(_renew())
    try:
        try:
            yield
        except asyncio.CancelledError as error:
            if lost.is_set():
                raise LeaseLost(f"Run {claim.run_id} lost its lease") from error
            raise
    finally:
        stopped.set()
        await heartbeat_task
