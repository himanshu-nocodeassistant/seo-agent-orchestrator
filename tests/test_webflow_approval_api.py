"""API tests for the Webflow proposal and approval flow."""

from types import SimpleNamespace
from unittest.mock import AsyncMock


class FakeWebflowClient:
    def __init__(self, current=None):
        self.current = current or {"id": "item-1", "version": 1, "fieldData": {"name": "Old"}}
        self.update_item = AsyncMock(return_value={"id": "item-1", "updated": True})
        self.create_item = AsyncMock(return_value={"id": "created-1"})
        self.publish_item = AsyncMock(return_value={"published": True})

    async def get_item(self, item_id):
        return self.current

    async def list_items(self, **kwargs):
        return {"items": []}


def test_webflow_profiles_are_proposal_only():
    from agent.runtime_profiles import PROFILE_REGISTRY, WEBFLOW_TOOLS

    for name in (
        "rewrite_title", "rewrite_meta_desc", "rewrite_h1", "blog_write",
        "rewrite_blog_content", "webflow_publish", "internal_links",
        "campaign_publisher",
    ):
        profile = PROFILE_REGISTRY[name]
        assert profile.requires_webflow_approval is True
        assert not set(profile.allowed_tools).intersection(
            {tool for tool in WEBFLOW_TOOLS if tool.endswith(("create_cms_item", "update_cms_item", "publish_cms_item"))}
        )


def _task(client):
    response = client.post(
        "/tasks",
        json={"title": "Update Webflow title", "execution_type": "rewrite_title"},
    )
    assert response.status_code == 200
    return response.json()["id"]


def _proposal(client, task_id):
    response = client.post(
        f"/tasks/{task_id}/webflow-proposals",
        json={
            "operation": "update",
            "resource_id": "item-1",
            "snapshot": {"id": "item-1", "version": 1, "fieldData": {"name": "Old"}},
            "payload": {"fieldData": {"name": "New title"}},
        },
    )
    assert response.status_code == 201
    return response.json()


def test_create_proposal_returns_full_pending_preview(client):
    task_id = _task(client)

    proposal = _proposal(client, task_id)

    assert proposal["status"] == "pending_approval"
    assert proposal["operation"] == "update"
    assert proposal["payload"] == {"fieldData": {"name": "New title"}}
    assert proposal["snapshot"]["fieldData"]["name"] == "Old"


def test_approval_applies_exact_stored_payload(client, monkeypatch):
    task_id = _task(client)
    proposal = _proposal(client, task_id)
    fake = FakeWebflowClient()
    monkeypatch.setattr("agent.api.routers.tasks.get_client", lambda: fake)

    response = client.post(f"/tasks/{task_id}/webflow-proposals/{proposal['id']}/approve")

    assert response.status_code == 200
    assert response.json()["status"] == "applied"
    fake.update_item.assert_awaited_once_with("item-1", {"name": "New title"})
    assert client.get(f"/tasks/{task_id}").json()["status"] == "completed"


def test_stale_proposal_never_writes(client, monkeypatch):
    task_id = _task(client)
    proposal = _proposal(client, task_id)
    fake = FakeWebflowClient(current={"id": "item-1", "version": 2, "fieldData": {"name": "Human edit"}})
    monkeypatch.setattr("agent.api.routers.tasks.get_client", lambda: fake)

    response = client.post(f"/tasks/{task_id}/webflow-proposals/{proposal['id']}/approve")

    assert response.status_code == 409
    assert response.json()["detail"] == "Proposal is stale. Create a new proposal."
    fake.update_item.assert_not_awaited()


def test_rejection_prevents_apply(client, monkeypatch):
    task_id = _task(client)
    proposal = _proposal(client, task_id)
    fake = FakeWebflowClient()
    monkeypatch.setattr("agent.api.routers.tasks.get_client", lambda: fake)

    rejected = client.post(
        f"/tasks/{task_id}/webflow-proposals/{proposal['id']}/reject",
        json={"reason": "Keep the current title."},
    )
    approved = client.post(f"/tasks/{task_id}/webflow-proposals/{proposal['id']}/approve")

    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert approved.status_code == 409
    fake.update_item.assert_not_awaited()


def test_repeated_approval_is_idempotent(client, monkeypatch):
    task_id = _task(client)
    proposal = _proposal(client, task_id)
    fake = FakeWebflowClient()
    monkeypatch.setattr("agent.api.routers.tasks.get_client", lambda: fake)

    first = client.post(f"/tasks/{task_id}/webflow-proposals/{proposal['id']}/approve")
    second = client.post(f"/tasks/{task_id}/webflow-proposals/{proposal['id']}/approve")

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["status"] == "applied"
    fake.update_item.assert_awaited_once()


def test_proposal_claim_only_succeeds_once(client):
    from agent.api.routers.tasks import _claim_webflow_proposal
    from agent.db import WebflowProposalModel, get_db_session

    task_id = _task(client)
    proposal = _proposal(client, task_id)
    db = get_db_session()
    try:
        row = db.query(WebflowProposalModel).filter_by(id=proposal["id"]).first()
        assert _claim_webflow_proposal(db, row, "operator") is True
        assert _claim_webflow_proposal(db, row, "operator") is False
    finally:
        db.close()


def test_webflow_execute_stores_agent_proposal_without_writing(client, monkeypatch):
    task_id = _task(client)
    output = '''Final draft title\nBackup\nKeyword rationale\nWebflow update status: pending approval\n<!-- CHANGE_LOG\n{"change_id":"test","change_type":"title","before":"Old","after":"New"}\nCHANGE_LOG -->
```json
{"webflow_proposal":{"operation":"update","resource_id":"item-1","snapshot":{"version":1},"payload":{"fieldData":{"name":"New"}}}}
```'''
    monkeypatch.setenv("WEBFLOW_ACCESS_TOKEN", "token")
    monkeypatch.setattr("agent.api.routers.tasks._build_runtime_config", lambda *args, **kwargs: object())
    monkeypatch.setattr(
        "agent.api.helpers._run_agent_prompt",
        AsyncMock(return_value=SimpleNamespace(result_text=output, session_id="session-1")),
    )

    response = client.post(f"/tasks/{task_id}/execute")

    assert response.status_code == 200
    assert response.json()["status"] == "awaiting_approval"
    task = client.get(f"/tasks/{task_id}").json()
    assert task["status"] == "blocked"
    proposals = client.get(f"/tasks/{task_id}/webflow-proposals").json()
    assert len(proposals) == 1
    assert proposals[0]["status"] == "pending_approval"
    assert proposals[0]["payload"]["fieldData"]["name"] == "New"


def test_webflow_execute_fails_closed_without_access(client, monkeypatch):
    task_id = _task(client)
    monkeypatch.delenv("WEBFLOW_ACCESS_TOKEN", raising=False)
    monkeypatch.setattr(
        "agent.api.helpers._run_agent_prompt",
        AsyncMock(return_value=SimpleNamespace(result_text="Draft only", session_id=None)),
    )

    response = client.post(f"/tasks/{task_id}/execute")

    assert response.status_code == 200
    assert response.json()["status"] == "needs_review"
    assert client.get(f"/tasks/{task_id}").json()["status"] == "blocked"


def test_approved_create_checks_slug_and_applies_once(client, monkeypatch):
    task = client.post("/tasks", json={"title": "Create blog", "execution_type": "blog_write"}).json()
    proposal = client.post(
        f"/tasks/{task['id']}/webflow-proposals",
        json={
            "operation": "create",
            "payload": {"fieldData": {"name": "New post", "slug": "new-post", "content": "Full content"}},
        },
    ).json()
    fake = FakeWebflowClient()
    monkeypatch.setattr("agent.api.routers.tasks.get_client", lambda: fake)

    response = client.post(f"/tasks/{task['id']}/webflow-proposals/{proposal['id']}/approve")

    assert response.status_code == 200
    fake.create_item.assert_awaited_once_with(
        field_data={"name": "New post", "slug": "new-post", "content": "Full content"},
        is_draft=False,
        is_archived=False,
    )


def test_approved_create_blocks_duplicate_slug(client, monkeypatch):
    task = client.post("/tasks", json={"title": "Duplicate blog", "execution_type": "blog_write"}).json()
    proposal = client.post(
        f"/tasks/{task['id']}/webflow-proposals",
        json={"operation": "create", "payload": {"fieldData": {"slug": "same-slug"}}},
    ).json()
    fake = FakeWebflowClient()
    fake.list_items = AsyncMock(return_value={"items": [{"fieldData": {"slug": "same-slug"}}]})
    monkeypatch.setattr("agent.api.routers.tasks.get_client", lambda: fake)

    response = client.post(f"/tasks/{task['id']}/webflow-proposals/{proposal['id']}/approve")

    assert response.status_code == 409
    assert "duplicate" in response.json()["detail"].lower()
    fake.create_item.assert_not_awaited()
