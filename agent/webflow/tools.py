"""
Webflow custom tools for Claude Agent SDK.

This module provides the @tool decorated functions that expose
Webflow CMS operations as MCP tools to the Claude Agent.
"""

import json
import logging
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Optional

from claude_agent_sdk import tool

from .client import WebflowAPIClient, WebflowAPIError

logger = logging.getLogger(__name__)

# Global client instance (set when server is created)
_webflow_client: Optional[WebflowAPIClient] = None
_authorized_write_proposal: ContextVar[Optional[str]] = ContextVar(
    "webflow_write_proposal", default=None
)


@contextmanager
def authorize_webflow_write(proposal_id: str):
    """Temporarily authorize writes while applying an approved proposal."""
    token = _authorized_write_proposal.set(proposal_id)
    try:
        yield
    finally:
        _authorized_write_proposal.reset(token)


def _require_write_authorization() -> None:
    if not _authorized_write_proposal.get():
        raise PermissionError("Webflow write requires approval for an approved proposal.")


def set_client(client: WebflowAPIClient):
    """Set the global Webflow client instance."""
    global _webflow_client
    _webflow_client = client


def get_client() -> WebflowAPIClient:
    """Get the global Webflow client instance."""
    if _webflow_client is None:
        raise RuntimeError("Webflow client not initialized. Call set_client() first.")
    return _webflow_client


# =============================================================================
# CMS Collection Item Tools
# =============================================================================


@tool(
    "list_cms_items",
    "List all items in the Webflow CMS collection. Returns items with pagination info.",
    {
        "limit": int,
        "offset": int,
        "sort_by": str,
        "sort_order": str,
    },
)
async def list_cms_items(args: dict[str, Any]) -> dict[str, Any]:
    """
    List all items in the CMS collection.

    Args:
        limit: Number of items to return (max 100)
        offset: Offset for pagination
        sort_by: Field to sort by (e.g., "_createdOn", "name")
        sort_order: Sort direction ("asc" or "desc")

    Returns:
        JSON string with items array and pagination
    """
    try:
        client = get_client()
        result = await client.list_items(
            limit=args.get("limit", 100),
            offset=args.get("offset", 0),
            sort_by=args.get("sort_by"),
            sort_order=args.get("sort_order"),
        )
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(result, indent=2),
                }
            ]
        }
    except WebflowAPIError as e:
        return {"content": [{"type": "text", "text": f"Error: {str(e)}"}]}
    except Exception as e:
        logger.exception("Failed to list CMS items")
        return {"content": [{"type": "text", "text": f"Unexpected error: {str(e)}"}]}


@tool(
    "get_cms_item",
    "Get a single CMS item by its ID.",
    {"item_id": str},
)
async def get_cms_item(args: dict[str, Any]) -> dict[str, Any]:
    """
    Get a single CMS item by ID.

    Args:
        item_id: The unique identifier of the item

    Returns:
        JSON string with item data
    """
    try:
        client = get_client()
        result = await client.get_item(args["item_id"])
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(result, indent=2),
                }
            ]
        }
    except WebflowAPIError as e:
        return {"content": [{"type": "text", "text": f"Error: {str(e)}"}]}
    except Exception as e:
        logger.exception("Failed to get CMS item")
        return {"content": [{"type": "text", "text": f"Unexpected error: {str(e)}"}]}


@tool(
    "create_cms_item",
    "Create a new item in the Webflow CMS collection.",
    {
        "name": str,
        "slug": str,
        "content": str,
        "is_draft": bool,
    },
)
async def create_cms_item(args: dict[str, Any]) -> dict[str, Any]:
    """
    Create a new CMS item.

    Args:
        name: Title/name of the item
        slug: URL slug for the item
        content: Main content/body of the item
        is_draft: Whether to create as draft (default False)

    Returns:
        JSON string with created item data
    """
    try:
        _require_write_authorization()
        client = get_client()
        field_data = {
            "name": args["name"],
            "slug": args["slug"],
            "content": args.get("content", ""),
        }
        result = await client.create_item(
            field_data=field_data,
            is_draft=args.get("is_draft", False),
        )
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(result, indent=2),
                }
            ]
        }
    except WebflowAPIError as e:
        return {"content": [{"type": "text", "text": f"Error: {str(e)}"}]}
    except PermissionError as e:
        return {"content": [{"type": "text", "text": f"Error: {str(e)}"}]}
    except Exception as e:
        logger.exception("Failed to create CMS item")
        return {"content": [{"type": "text", "text": f"Unexpected error: {str(e)}"}]}


@tool(
    "update_cms_item",
    "Update an existing CMS item with new field values.",
    {
        "item_id": str,
        "name": str,
        "slug": str,
        "content": str,
    },
)
async def update_cms_item(args: dict[str, Any]) -> dict[str, Any]:
    """
    Update an existing CMS item.

    Args:
        item_id: The unique identifier of the item to update
        name: New title/name for the item
        slug: New URL slug
        content: New content/body

    Returns:
        JSON string with updated item data
    """
    try:
        _require_write_authorization()
        client = get_client()
        field_data = {}
        if "name" in args:
            field_data["name"] = args["name"]
        if "slug" in args:
            field_data["slug"] = args["slug"]
        if "content" in args:
            field_data["content"] = args["content"]

        result = await client.update_item(
            item_id=args["item_id"],
            field_data=field_data,
        )
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(result, indent=2),
                }
            ]
        }
    except WebflowAPIError as e:
        return {"content": [{"type": "text", "text": f"Error: {str(e)}"}]}
    except PermissionError as e:
        return {"content": [{"type": "text", "text": f"Error: {str(e)}"}]}
    except Exception as e:
        logger.exception("Failed to update CMS item")
        return {"content": [{"type": "text", "text": f"Unexpected error: {str(e)}"}]}


@tool(
    "publish_cms_item",
    "Publish a CMS item to make it live on the website.",
    {"item_id": str},
)
async def publish_cms_item(args: dict[str, Any]) -> dict[str, Any]:
    """
    Publish a CMS item to live site.

    Args:
        item_id: The unique identifier of the item to publish

    Returns:
        JSON string with publish result
    """
    try:
        _require_write_authorization()
        client = get_client()
        result = await client.publish_item(args["item_id"])
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(result, indent=2),
                }
            ]
        }
    except WebflowAPIError as e:
        return {"content": [{"type": "text", "text": f"Error: {str(e)}"}]}
    except PermissionError as e:
        return {"content": [{"type": "text", "text": f"Error: {str(e)}"}]}
    except Exception as e:
        logger.exception("Failed to publish CMS item")
        return {"content": [{"type": "text", "text": f"Unexpected error: {str(e)}"}]}


# =============================================================================
# Collection Info Tools
# =============================================================================


@tool(
    "get_collection_info",
    "Get information about the CMS collection including field schema.",
    {},
)
async def get_collection_info(args: dict[str, Any]) -> dict[str, Any]:
    """
    Get collection details and field schema.

    Returns:
        JSON string with collection info
    """
    try:
        client = get_client()
        result = await client.get_collection()
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(result, indent=2),
                }
            ]
        }
    except WebflowAPIError as e:
        return {"content": [{"type": "text", "text": f"Error: {str(e)}"}]}
    except Exception as e:
        logger.exception("Failed to get collection info")
        return {"content": [{"type": "text", "text": f"Unexpected error: {str(e)}"}]}


# List of all available tools
WEBFLOW_TOOLS = [
    list_cms_items,
    get_cms_item,
    create_cms_item,
    update_cms_item,
    publish_cms_item,
    get_collection_info,
]
