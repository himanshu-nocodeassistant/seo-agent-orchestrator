"""Tests for one approval covering several Webflow updates."""

from unittest.mock import AsyncMock


class BatchWebflowClient:
    def __init__(self, failed_id=None):
        self.failed_id = failed_id
        self.update_item = AsyncMock(side_effect=self._update)

    async def get_item(self, item_id):
        return {"id": item_id, "version": 1}

    async def _update(self, item_id, field_data):
        if item_id == self.failed_id:
            raise RuntimeError("Webflow rejected item")
        return {"id": item_id, "updated": True, "fieldData": field_data}


def _batch_proposal(client):
    task = client.post("/tasks", json={"title": "Add internal links", "execution_type": "internal_links"}).json()
    response = client.post(
        f"/tasks/{task['id']}/webflow-proposals",
        json={
            "operation": "update",
            "resource_id": "batch",
            "snapshot": {"items": {"item-1": {"id": "item-1", "version": 1}, "item-2": {"id": "item-2", "version": 1}}},
            "payload": {"items": [
                {"id": "item-1", "fieldData": {"content": "A"}},
                {"id": "item-2", "fieldData": {"content": "B"}},
            ]},
        },
    )
    assert response.status_code == 201
    return task["id"], response.json()["id"]


def test_one_approval_applies_batch_in_order_with_item_results(client, monkeypatch):
    task_id, proposal_id = _batch_proposal(client)
    fake = BatchWebflowClient()
    monkeypatch.setattr("agent.api.routers.tasks.get_client", lambda: fake)

    response = client.post(f"/tasks/{task_id}/webflow-proposals/{proposal_id}/approve")

    assert response.status_code == 200
    assert response.json()["status"] == "applied"
    assert [call.args[0] for call in fake.update_item.await_args_list] == ["item-1", "item-2"]
    assert [item["status"] for item in response.json()["result"]["items"]] == ["applied", "applied"]


def test_batch_reports_partial_failure(client, monkeypatch):
    task_id, proposal_id = _batch_proposal(client)
    fake = BatchWebflowClient(failed_id="item-2")
    monkeypatch.setattr("agent.api.routers.tasks.get_client", lambda: fake)

    response = client.post(f"/tasks/{task_id}/webflow-proposals/{proposal_id}/approve")

    assert response.status_code == 200
    assert response.json()["status"] == "partial_failed"
    assert [item["status"] for item in response.json()["result"]["items"]] == ["applied", "failed"]


def test_batch_retry_only_reapplies_failed_items(client, monkeypatch):
    task_id, proposal_id = _batch_proposal(client)
    fake = BatchWebflowClient(failed_id="item-2")
    monkeypatch.setattr("agent.api.routers.tasks.get_client", lambda: fake)
    first = client.post(f"/tasks/{task_id}/webflow-proposals/{proposal_id}/approve")
    assert first.json()["status"] == "partial_failed"

    fake.failed_id = None
    second = client.post(f"/tasks/{task_id}/webflow-proposals/{proposal_id}/approve")

    assert second.status_code == 200
    assert second.json()["status"] == "applied"
    assert [call.args[0] for call in fake.update_item.await_args_list] == ["item-1", "item-2", "item-2"]
