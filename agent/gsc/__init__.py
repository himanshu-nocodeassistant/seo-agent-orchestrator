"""
Google Search Console integration for the SEO Agent.

Provides read-only access to Search Console data: search analytics,
URL inspection, and sitemap listing.
"""

from .config import GscConfig
from .client import GscAPIClient, GscAPIError
from .tools import GSC_TOOLS, set_client, get_client
from .server import create_gsc_server

__all__ = [
    "GscConfig",
    "GscAPIClient",
    "GscAPIError",
    "GSC_TOOLS",
    "set_client",
    "get_client",
    "create_gsc_server",
]
