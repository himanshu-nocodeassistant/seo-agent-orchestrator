"""Parse the exact Webflow proposal emitted by a proposal-only run."""

from __future__ import annotations

import json
import re
from typing import Any


_JSON_BLOCK = re.compile(r"```json\s*(.*?)\s*```", re.IGNORECASE | re.DOTALL)
_OPERATIONS = {"create", "update", "publish"}


def extract_webflow_proposal(output: str) -> dict[str, Any] | None:
    """Return a complete proposal block, or ``None`` for invalid output.

    The parser does not trim or cap payload values. Invalid output is rejected so
    an incomplete model response cannot become an approved Webflow write.
    """
    if not isinstance(output, str):
        return None
    for match in _JSON_BLOCK.finditer(output):
        try:
            document = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        proposal = document.get("webflow_proposal") if isinstance(document, dict) else None
        if not isinstance(proposal, dict):
            continue
        operation = proposal.get("operation")
        if operation not in _OPERATIONS:
            continue
        if operation in {"update", "publish"} and not proposal.get("resource_id"):
            continue
        if not isinstance(proposal.get("snapshot"), dict):
            continue
        if not isinstance(proposal.get("payload"), dict):
            continue
        return proposal
    return None


__all__ = ["extract_webflow_proposal"]
