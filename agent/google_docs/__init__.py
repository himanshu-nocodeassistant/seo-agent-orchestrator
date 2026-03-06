"""
Google Docs integration for the SEO Agent.

This module provides tools for creating and managing Google Docs
for SEO audit reports, blog content, and other documents.
"""

from .config import GoogleDocsConfig
from .client import GoogleDocsAPIClient, GoogleDocsAPIError
from .tools import GOOGLE_DOCS_TOOLS, set_client, get_client
from .server import create_google_docs_server

__all__ = [
    "GoogleDocsConfig",
    "GoogleDocsAPIClient", 
    "GoogleDocsAPIError",
    "GOOGLE_DOCS_TOOLS",
    "set_client",
    "get_client",
    "create_google_docs_server",
]
