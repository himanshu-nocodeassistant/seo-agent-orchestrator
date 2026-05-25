"""
Webflow CMS integration for the SEO Agent.

This package provides modular Webflow CMS integration:
- config: Configuration dataclass
- client: Raw API client
- tools: Claude Agent SDK tools
- server: MCP server factory
"""

from .client import WebflowAPIClient, WebflowAPIError
from .config import WebflowConfig
from .server import create_webflow_server, create_webflow_server_async
from .tools import (
    WEBFLOW_TOOLS,
    create_cms_item,
    get_cms_item,
    get_collection_info,
    list_cms_items,
    publish_cms_item,
    update_cms_item,
)

__all__ = [
    # Config
    "WebflowConfig",
    # Client
    "WebflowAPIClient",
    "WebflowAPIError",
    # Server
    "create_webflow_server",
    "create_webflow_server_async",
    # Tools
    "WEBFLOW_TOOLS",
    "list_cms_items",
    "get_cms_item",
    "create_cms_item",
    "update_cms_item",
    "publish_cms_item",
    "get_collection_info",
]
