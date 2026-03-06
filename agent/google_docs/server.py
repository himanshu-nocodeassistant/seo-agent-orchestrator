"""
Google Docs MCP server factory for Claude Agent SDK.

This module provides the create_google_docs_server function that
creates an MCP server with Google Docs tools.
"""

import logging

from claude_agent_sdk import create_sdk_mcp_server

from .client import GoogleDocsAPIClient
from .config import GoogleDocsConfig
from .tools import GOOGLE_DOCS_TOOLS, set_client

logger = logging.getLogger(__name__)


def create_google_docs_server(config: GoogleDocsConfig):
    """
    Create an MCP server with Google Docs tools.

    Args:
        config: GoogleDocsConfig with credentials_path

    Returns:
        MCP server instance to pass to Claude Agent SDK
    """
    # Create the API client
    client = GoogleDocsAPIClient(config)

    # Set the global client for tools to use
    set_client(client)

    # Create the MCP server with all Google Docs tools
    server = create_sdk_mcp_server(
        name="google-docs",
        version="1.0.0",
        tools=GOOGLE_DOCS_TOOLS,
    )

    logger.info(
        f"Created Google Docs MCP server"
    )

    return server


async def create_google_docs_server_async(config: GoogleDocsConfig):
    """
    Create an MCP server with Google Docs tools (async version).

    This also initializes the client connection.

    Args:
        config: GoogleDocsConfig with credentials_path

    Returns:
        Tuple of (MCP server, API client)
    """
    # Create the API client
    client = GoogleDocsAPIClient(config)

    # Set the global client for tools to use
    set_client(client)

    # Create the MCP server with all Google Docs tools
    server = create_sdk_mcp_server(
        name="google-docs",
        version="1.0.0",
        tools=GOOGLE_DOCS_TOOLS,
    )

    logger.info(
        f"Created Google Docs MCP server"
    )

    return server, client
