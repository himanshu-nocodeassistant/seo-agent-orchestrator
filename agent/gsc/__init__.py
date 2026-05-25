"""Google Search Console integration for the SEO Agent."""

from .client import GoogleSearchConsoleClient, GoogleSearchConsoleError
from .config import GoogleSearchConsoleConfig

__all__ = [
    "GoogleSearchConsoleClient",
    "GoogleSearchConsoleError",
    "GoogleSearchConsoleConfig",
]
