"""API tests for durable idempotency on the SEO audit endpoint."""

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from agent.api.main import TaskModel, get_db_session
from agent.db import AuditRequestModel
from agent.run_claims import RunClaimService


def _audit_url():
    return f"/runs/audit-{uuid4().hex}/seo-audit"


def _agent_result():
    return SimpleNamespace(
        result_text="Audit complete. Source: https://example.com/audit",
        session_id=None,
    )


def test_seo_audit_requires_idempotency_key(client, monkeypatch):
    monkeypatch.setenv("ALLOW_MISSING_IDEMPOTENCY_KEY", "false")
    with patch("agent.api.helpers._run_agent_prompt", new=AsyncMock()) as agent:
        response = client.post(_audit_url(), json={"days": 28})

    assert response.status_code == 400
    assert "Idempotency-Key" in response.json()["detail"]
    agent.assert_not_awaited()


def test_seo_audit_replays_same_key_without_new_work(client):
    url = _audit_url()
    with patch(
        "agent.api.helpers._run_agent_prompt",
        new=AsyncMock(return_value=_agent_result()),
    ) as agent:
        first = client.post(url, headers={"Idempotency-Key": "audit-replay"}, json={"days": 28})
        replay = client.post(url, headers={"Idempotency-Key": "audit-replay"}, json={"days": 28})

    assert first.status_code == 200
    assert replay.status_code == 200
    assert replay.json() == first.json()
    assert agent.await_count == 1


def test_seo_audit_rejects_same_key_with_changed_days(client):
    url = _audit_url()
    with patch(
        "agent.api.helpers._run_agent_prompt",
        new=AsyncMock(return_value=_agent_result()),
    ) as agent:
        first = client.post(url, headers={"Idempotency-Key": "audit-days"}, json={"days": 28})
        changed = client.post(url, headers={"Idempotency-Key": "audit-days"}, json={"days": 7})

    assert first.status_code == 200
    assert changed.status_code == 409
    assert agent.await_count == 1


def test_seo_audit_rejects_different_key_while_same_audit_is_active(client):
    audit_id = f"audit-{uuid4().hex}"
    db = get_db_session()
    try:
        task = TaskModel(
            title="Active audit",
            status="in_progress",
            execution_type="seo_audit",
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        claim = RunClaimService(db).acquire(
            task.id,
            idempotency_key="first-key",
            fingerprint="seo_audit:days=28",
            request_scope=f"seo-audit:{audit_id}",
            execution_type="seo_audit",
        )
        db.add(
            AuditRequestModel(
                audit_id=audit_id,
                idempotency_key="first-key",
                fingerprint="seo_audit:days=28",
                task_id=task.id,
                run_id=claim.run_id,
                created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
        )
        db.commit()
    finally:
        db.close()

    with patch("agent.api.helpers._run_agent_prompt", new=AsyncMock()) as agent:
        response = client.post(
            f"/runs/{audit_id}/seo-audit",
            headers={"Idempotency-Key": "second-key"},
            json={"days": 28},
        )

    assert response.status_code == 409
    assert response.json()["detail"]["run_id"] == claim.run_id
    agent.assert_not_awaited()


def test_overlapping_audit_keys_create_one_audit(client):
    url = _audit_url()
    entered = threading.Event()
    release = threading.Event()

    async def blocked_agent(*_args, **_kwargs):
        entered.set()
        await asyncio.to_thread(release.wait, 5)
        return _agent_result()

    with patch("agent.api.helpers._run_agent_prompt", new=AsyncMock(side_effect=blocked_agent)) as agent:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first_future = pool.submit(
                client.post,
                url,
                headers={"Idempotency-Key": "audit-concurrent-a"},
                json={"days": 28},
            )
            assert entered.wait(5)
            second = client.post(
                url,
                headers={"Idempotency-Key": "audit-concurrent-b"},
                json={"days": 28},
            )
            release.set()
            first = first_future.result(timeout=5)

    assert first.status_code == 200
    assert second.status_code == 409
    assert agent.await_count == 1
