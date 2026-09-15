"""
Google Search Console MCP server factory for Claude Agent SDK.
"""

import logging

from claude_agent_sdk import create_sdk_mcp_server

from .client import GscAPIClient
from .config import GscConfig
from .tools import GSC_TOOLS, set_client

logger = logging.getLogger(__name__)


def create_gsc_server(config: GscConfig):
    """
    Create an MCP server with read-only GSC tools.

    Args:
        config: GscConfig with site_url and credentials_path.

    Returns:
        MCP server instance ready for AgentConfig.mcp_servers.
    """
    client = GscAPIClient(config)
    set_client(client)

    server = create_sdk_mcp_server(
        name="gsc",
        version="1.0.0",
        tools=GSC_TOOLS,
    )

    logger.info("Created GSC MCP server (site=%s)", config.site_url)
    return server


async def create_gsc_server_async(config: GscConfig):
    """
    Async variant — returns (server, client) tuple.
    """
    client = GscAPIClient(config)
    set_client(client)

    server = create_sdk_mcp_server(
        name="gsc",
        version="1.0.0",
        tools=GSC_TOOLS,
    )

    logger.info("Created GSC MCP server (site=%s)", config.site_url)
    return server, client
