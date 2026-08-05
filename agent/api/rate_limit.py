"""Shared slowapi limiter for cost-triggering endpoints."""

import os

from slowapi import Limiter
from slowapi.util import get_remote_address

def _rate_limit_value() -> str:
    """Per-minute rate limit for cost-triggering endpoints."""
    return os.environ.get("API_RATE_LIMIT_EXECUTE", "5/minute")

limiter = Limiter(key_func=get_remote_address, default_limits=[])
