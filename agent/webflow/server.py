"""
Webflow MCP server factory for Claude Agent SDK.

This module provides the create_webflow_server function that
creates an MCP server with Webflow CMS tools.
"""

import logging

from claude_agent_sdk import create_sdk_mcp_server

from .client import WebflowAPIClient
from .config import WebflowConfig
from .tools import WEBFLOW_TOOLS, set_client

logger = logging.getLogger(__name__)


def create_webflow_server(config: WebflowConfig):
    """
    Create an MCP server with Webflow CMS tools.

    Args:
        config: WebflowConfig with access_token, site_id, collection_id

    Returns:
        MCP server instance to pass to Claude Agent SDK
    """
    # Create the API client
    client = WebflowAPIClient(config)

    # Set the global client for tools to use
    set_client(client)

    # Create the MCP server with all Webflow tools
    server = create_sdk_mcp_server(
        name="webflow-cms",
        version="1.0.0",
        tools=WEBFLOW_TOOLS,
    )

    logger.info(
        f"Created Webflow MCP server for collection: {config.collection_id}"
    )

    return server


async def create_webflow_server_async(config: WebflowConfig):
    """
    Create an MCP server with Webflow CMS tools (async version).

    This also initializes the client connection.

    Args:
        config: WebflowConfig with access_token, site_id, collection_id

    Returns:
        Tuple of (MCP server, API client)
    """
    # Create the API client
    client = WebflowAPIClient(config)

    # Set the global client for tools to use
    set_client(client)

    # Create the MCP server with all Webflow tools
    server = create_sdk_mcp_server(
        name="webflow-cms",
        version="1.0.0",
        tools=WEBFLOW_TOOLS,
    )

    logger.info(
        f"Created Webflow MCP server for collection: {config.collection_id}"
    )

    return server, client
