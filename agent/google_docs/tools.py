"""
Google Docs custom tools for Claude Agent SDK.

This module provides the @tool decorated functions that expose
Google Docs operations as MCP tools to the Claude Agent.

NOTE: No delete tool - documents cannot be deleted by design.
"""

import json
import logging
from typing import Any, Optional

from claude_agent_sdk import tool

from .client import GoogleDocsAPIClient, GoogleDocsAPIError

logger = logging.getLogger(__name__)

# Global client instance (set when server is created)
_google_docs_client: Optional[GoogleDocsAPIClient] = None


def set_client(client: GoogleDocsAPIClient):
    """Set the global Google Docs client instance."""
    global _google_docs_client
    _google_docs_client = client


def get_client() -> GoogleDocsAPIClient:
    """Get the global Google Docs client instance."""
    if _google_docs_client is None:
        raise RuntimeError("Google Docs client not initialized. Call set_client() first.")
    return _google_docs_client


# =============================================================================
# Document Tools (NO DELETE - by design)
# =============================================================================


@tool(
    "create_google_doc",
    "Create a new Google Doc with a title and optional content. Returns the document ID.",
    {
        "title": str,
        "content": str,
    },
)
async def create_document(args: dict[str, Any]) -> dict[str, Any]:
    """
    Create a new Google Doc.

    Args:
        title: Title for the document
        content: Initial content/body of the document

    Returns:
        JSON string with document ID and details
    """
    try:
        client = get_client()
        result = await client.create_document(
            title=args.get("title", "Untitled Document"),
            content=args.get("content", ""),
        )
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(result, indent=2),
                }
            ]
        }
    except GoogleDocsAPIError as e:
        return {"content": [{"type": "text", "text": f"Error: {str(e)}"}]}
    except Exception as e:
        logger.exception("Failed to create document")
        return {"content": [{"type": "text", "text": f"Unexpected error: {str(e)}"}]}


@tool(
    "get_google_doc",
    "Get a Google Doc by its document ID.",
    {"document_id": str},
)
async def get_document(args: dict[str, Any]) -> dict[str, Any]:
    """
    Get a Google Doc by ID.

    Args:
        document_id: The unique identifier of the document

    Returns:
        JSON string with document content
    """
    try:
        client = get_client()
        result = await client.get_document(args["document_id"])
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(result, indent=2),
                }
            ]
        }
    except GoogleDocsAPIError as e:
        return {"content": [{"type": "text", "text": f"Error: {str(e)}"}]}
    except Exception as e:
        logger.exception("Failed to get document")
        return {"content": [{"type": "text", "text": f"Unexpected error: {str(e)}"}]}


@tool(
    "append_to_google_doc",
    "Append text content to an existing Google Doc.",
    {
        "document_id": str,
        "text": str,
    },
)
async def append_content(args: dict[str, Any]) -> dict[str, Any]:
    """
    Append text to a Google Doc.

    Args:
        document_id: The unique identifier of the document
        text: Text to append

    Returns:
        JSON string with operation result
    """
    try:
        client = get_client()
        result = await client.append_content(
            document_id=args["document_id"],
            text=args["text"],
        )
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(result, indent=2),
                }
            ]
        }
    except GoogleDocsAPIError as e:
        return {"content": [{"type": "text", "text": f"Error: {str(e)}"}]}
    except Exception as e:
        logger.exception("Failed to append content")
        return {"content": [{"type": "text", "text": f"Unexpected error: {str(e)}"}]}


@tool(
    "update_google_doc_title",
    "Update the title of an existing Google Doc.",
    {
        "document_id": str,
        "title": str,
    },
)
async def update_title(args: dict[str, Any]) -> dict[str, Any]:
    """
    Update a Google Doc's title.

    Args:
        document_id: The unique identifier of the document
        title: New title

    Returns:
        JSON string with updated document
    """
    try:
        client = get_client()
        result = await client.update_title(
            document_id=args["document_id"],
            title=args["title"],
        )
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(result, indent=2),
                }
            ]
        }
    except GoogleDocsAPIError as e:
        return {"content": [{"type": "text", "text": f"Error: {str(e)}"}]}
    except Exception as e:
        logger.exception("Failed to update title")
        return {"content": [{"type": "text", "text": f"Unexpected error: {str(e)}"}]}


# List of all available tools (NO delete tool - by design)
GOOGLE_DOCS_TOOLS = [
    create_document,
    get_document,
    append_content,
    update_title,
]
