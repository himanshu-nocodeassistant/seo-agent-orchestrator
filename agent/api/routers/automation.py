"""Automation endpoints.

Extracted from the former agent/api/main.py monolith (see git history).
"""

from fastapi import APIRouter, Request

from agent.api.helpers import process_one_comment_action
from agent.api.rate_limit import _rate_limit_value, limiter

router = APIRouter()

@router.post("/automation/comments/process-one")
@limiter.limit(lambda: _rate_limit_value())
async def process_one_comment_action_endpoint(request: Request):
    """Process one pending @agent trigger comment action."""
    return await process_one_comment_action(
        request_id=getattr(request.state, "request_id", None)
    )


# ============================================================================
# SEO AUDIT ENDPOINT
# ============================================================================
