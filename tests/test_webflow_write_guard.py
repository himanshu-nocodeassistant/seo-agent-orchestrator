"""Webflow MCP writes require an explicit approved proposal context."""

import pytest

from agent.webflow.tools import authorize_webflow_write, update_cms_item


@pytest.mark.asyncio
async def test_update_tool_is_blocked_without_approval():
    result = await update_cms_item.handler({"item_id": "item-1", "name": "New"})

    assert "approval" in result["content"][0]["text"].lower()


@pytest.mark.asyncio
async def test_update_tool_can_run_only_inside_approved_context(monkeypatch):
    class Client:
        async def update_item(self, item_id, field_data):
            return {"id": item_id, "fieldData": field_data}

    monkeypatch.setattr("agent.webflow.tools._webflow_client", Client())

    with authorize_webflow_write("proposal-1"):
        result = await update_cms_item.handler({"item_id": "item-1", "name": "New"})

    assert result["content"][0]["text"].find('"name": "New"') >= 0
