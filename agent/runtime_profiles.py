"""
Execution profiles and output validation for SEO task runs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Optional


BASE_ALLOWED_TOOLS = ["Read", "Glob", "Grep", "WebSearch", "WebFetch", "Skill"]
EDIT_ALLOWED_TOOLS = BASE_ALLOWED_TOOLS + ["Write", "Edit"]
WEBFLOW_TOOLS = [
    "mcp__webflow__list_cms_items",
    "mcp__webflow__get_cms_item",
    "mcp__webflow__create_cms_item",
    "mcp__webflow__update_cms_item",
    "mcp__webflow__publish_cms_item",
    "mcp__webflow__get_collection_info",
]
# Read-only GSC tools — safe to include in any profile that reads web data
GSC_TOOLS = [
    "mcp__gsc__gsc_query_search_analytics",
    "mcp__gsc__gsc_inspect_url",
    "mcp__gsc__gsc_list_sitemaps",
]


@dataclass(frozen=True)
class ValidationResult:
    status: str
    message: Optional[str] = None


@dataclass(frozen=True)
class ExecutionProfile:
    execution_type: str
    allowed_tools: list[str]
    max_turns: int
    max_budget_usd: Optional[float]
    timeout_seconds: int
    max_thinking_tokens: Optional[int]
    episodic_limit: int
    semantic_char_limit: int
    validator: Callable[[str], ValidationResult]
    should_resume_session: bool = True
    procedural_tags: list[str] = field(default_factory=list)


def _validate_non_empty(output: str) -> ValidationResult:
    if output and output.strip():
        return ValidationResult(status="passed")
    return ValidationResult(status="failed", message="Agent returned empty output.")


_KEYWORD_TOKENS = re.compile(
    r"\b(keywords?|query|search terms?|volume|search volume|kw)\b", re.IGNORECASE
)


def _validate_research_output(output: str) -> ValidationResult:
    """Research output must contain at least one cited URL and one keyword reference.

    Catches the most common hallucination pattern — plausible-sounding recommendations
    with no web evidence — without being so strict that valid runs fail.
    """
    if not output.strip():
        return ValidationResult(status="failed", message="Agent returned empty output.")
    if not re.search(r"https?://\S+", output):
        return ValidationResult(
            status="failed",
            message="Research output contains no cited URLs — agent may not have used WebSearch.",
        )
    if not _KEYWORD_TOKENS.search(output):
        return ValidationResult(
            status="failed",
            message="Research output contains no keyword data (expected 'keyword', 'query', or 'volume').",
        )
    return ValidationResult(status="passed")


def _contains_all(output: str, required_fragments: list[str], message: str) -> ValidationResult:
    normalized = output.lower()
    for fragment in required_fragments:
        if fragment.lower() not in normalized:
            return ValidationResult(status="failed", message=message)
    return ValidationResult(status="passed")


def _validate_rewrite_title(output: str) -> ValidationResult:
    return _contains_all(
        output,
        ["final draft title", "backup", "keyword rationale"],
        "rewrite_title output must include final draft, backups, and rationale.",
    )


def _validate_rewrite_meta_desc(output: str) -> ValidationResult:
    return _contains_all(
        output,
        ["final draft", "character count", "webflow update status"],
        "rewrite_meta_desc output must include final draft, character count, and status.",
    )


def _validate_rewrite_h1(output: str) -> ValidationResult:
    return _contains_all(
        output,
        ["final draft h1", "webflow update status"],
        "rewrite_h1 output must include final H1 and Webflow status.",
    )


def _validate_blog_write(output: str) -> ValidationResult:
    return _contains_all(
        output,
        ["title:", "url slug:", "word count:", "webflow status:"],
        "blog_write output must include title, slug, word count, and Webflow status.",
    )


def _validate_change_log_when_expected(output: str) -> ValidationResult:
    if "<!-- CHANGE_LOG" in output:
        return ValidationResult(status="passed")
    return ValidationResult(status="failed", message="Expected CHANGE_LOG block in CMS mutation output.")


def _with_change_log(fallback: Callable[[str], ValidationResult]) -> Callable[[str], ValidationResult]:
    def validator(output: str) -> ValidationResult:
        fallback_result = fallback(output)
        if fallback_result.status != "passed":
            return fallback_result
        return _validate_change_log_when_expected(output)

    return validator


def _validate_orchestration_plan(output: str) -> ValidationResult:
    """Validates the orchestrator returned parseable JSON with at least one phase."""
    import json
    import re

    match = re.search(r"```json\s*(.*?)```", output, re.DOTALL)
    if not match:
        match = re.search(r'(\{[^{}]*"phases"[^{}]*\[.*?\][^{}]*\})', output, re.DOTALL)
    if not match:
        return ValidationResult(status="failed", message="Orchestrator did not return a JSON plan block.")
    try:
        plan = json.loads(match.group(1))
        if not plan.get("phases"):
            return ValidationResult(status="failed", message="Plan has no phases.")
        return ValidationResult(status="passed")
    except json.JSONDecodeError as e:
        return ValidationResult(status="failed", message=f"Plan JSON parse error: {e}")


def _profile(
    execution_type: str,
    *,
    allowed_tools: list[str],
    max_turns: int,
    max_budget_usd: Optional[float],
    timeout_seconds: int,
    max_thinking_tokens: Optional[int],
    episodic_limit: int,
    semantic_char_limit: int,
    validator: Callable[[str], ValidationResult],
    should_resume_session: bool = True,
    procedural_tags: Optional[list[str]] = None,
) -> ExecutionProfile:
    return ExecutionProfile(
        execution_type=execution_type,
        allowed_tools=allowed_tools,
        max_turns=max_turns,
        max_budget_usd=max_budget_usd,
        timeout_seconds=timeout_seconds,
        max_thinking_tokens=max_thinking_tokens,
        episodic_limit=episodic_limit,
        semantic_char_limit=semantic_char_limit,
        validator=validator,
        should_resume_session=should_resume_session,
        procedural_tags=procedural_tags or [],
    )


PROFILE_REGISTRY: dict[str, ExecutionProfile] = {
    "rewrite_title": _profile(
        "rewrite_title",
        allowed_tools=EDIT_ALLOWED_TOOLS + WEBFLOW_TOOLS,
        max_turns=10,
        max_budget_usd=1.5,
        timeout_seconds=300,
        max_thinking_tokens=4000,
        episodic_limit=3,
        semantic_char_limit=2200,
        validator=_with_change_log(_validate_rewrite_title),
        procedural_tags=["brand-voice", "title-rewrite"],
    ),
    "rewrite_meta_desc": _profile(
        "rewrite_meta_desc",
        allowed_tools=EDIT_ALLOWED_TOOLS + WEBFLOW_TOOLS,
        max_turns=10,
        max_budget_usd=1.5,
        timeout_seconds=300,
        max_thinking_tokens=4000,
        episodic_limit=3,
        semantic_char_limit=2200,
        validator=_with_change_log(_validate_rewrite_meta_desc),
        procedural_tags=["brand-voice", "meta-description"],
    ),
    "rewrite_h1": _profile(
        "rewrite_h1",
        allowed_tools=EDIT_ALLOWED_TOOLS + WEBFLOW_TOOLS,
        max_turns=10,
        max_budget_usd=1.5,
        timeout_seconds=300,
        max_thinking_tokens=4000,
        episodic_limit=3,
        semantic_char_limit=2200,
        validator=_with_change_log(_validate_rewrite_h1),
        procedural_tags=["brand-voice", "heading-rewrite"],
    ),
    "blog_write": _profile(
        "blog_write",
        allowed_tools=EDIT_ALLOWED_TOOLS + WEBFLOW_TOOLS,
        max_turns=18,
        max_budget_usd=4.0,
        timeout_seconds=900,
        max_thinking_tokens=8000,
        episodic_limit=5,
        semantic_char_limit=3500,
        validator=_with_change_log(_validate_blog_write),
        procedural_tags=["brand-voice", "copywriting", "publishable-output"],
    ),
    "rewrite_blog_content": _profile(
        "rewrite_blog_content",
        allowed_tools=EDIT_ALLOWED_TOOLS + WEBFLOW_TOOLS,
        max_turns=18,
        max_budget_usd=4.0,
        timeout_seconds=900,
        max_thinking_tokens=8000,
        episodic_limit=5,
        semantic_char_limit=3500,
        validator=_with_change_log(_validate_non_empty),
        procedural_tags=["brand-voice", "copy-editing", "content-rewrite"],
    ),
    "webflow_publish": _profile(
        "webflow_publish",
        allowed_tools=EDIT_ALLOWED_TOOLS + WEBFLOW_TOOLS,
        max_turns=8,
        max_budget_usd=1.0,
        timeout_seconds=240,
        max_thinking_tokens=3000,
        episodic_limit=2,
        semantic_char_limit=1200,
        validator=_with_change_log(_validate_non_empty),
        procedural_tags=["publish"],
    ),
    "internal_links": _profile(
        "internal_links",
        allowed_tools=EDIT_ALLOWED_TOOLS + WEBFLOW_TOOLS,
        max_turns=14,
        max_budget_usd=2.5,
        timeout_seconds=600,
        max_thinking_tokens=6000,
        episodic_limit=4,
        semantic_char_limit=2800,
        validator=_with_change_log(_validate_non_empty),
        procedural_tags=["brand-voice", "internal-linking"],
    ),
    "research": _profile(
        "research",
        allowed_tools=BASE_ALLOWED_TOOLS + GSC_TOOLS,
        max_turns=12,
        max_budget_usd=2.0,
        timeout_seconds=480,
        max_thinking_tokens=6000,
        episodic_limit=4,
        semantic_char_limit=2600,
        validator=_validate_research_output,
        procedural_tags=["brand-voice", "research", "grounding-required"],
    ),
    "alt_text": _profile(
        "alt_text",
        allowed_tools=BASE_ALLOWED_TOOLS,
        max_turns=8,
        max_budget_usd=1.0,
        timeout_seconds=240,
        max_thinking_tokens=3000,
        episodic_limit=2,
        semantic_char_limit=1600,
        validator=_validate_non_empty,
        procedural_tags=["brand-voice", "accessibility"],
    ),
    "update_schema": _profile(
        "update_schema",
        allowed_tools=BASE_ALLOWED_TOOLS,
        max_turns=10,
        max_budget_usd=1.5,
        timeout_seconds=300,
        max_thinking_tokens=4000,
        episodic_limit=2,
        semantic_char_limit=1800,
        validator=_validate_non_empty,
        procedural_tags=["schema"],
    ),
    "seo_impact_review": _profile(
        "seo_impact_review",
        allowed_tools=BASE_ALLOWED_TOOLS + GSC_TOOLS,
        max_turns=20,
        max_budget_usd=4.0,
        timeout_seconds=900,
        max_thinking_tokens=8000,
        episodic_limit=10,
        semantic_char_limit=2500,
        validator=_validate_non_empty,
        should_resume_session=False,
        procedural_tags=["feedback-loop", "impact-review"],
    ),
    "manual": _profile(
        "manual",
        allowed_tools=BASE_ALLOWED_TOOLS,
        max_turns=8,
        max_budget_usd=1.0,
        timeout_seconds=240,
        max_thinking_tokens=3000,
        episodic_limit=2,
        semantic_char_limit=1400,
        validator=_validate_non_empty,
        procedural_tags=["manual"],
    ),
    # ── Orchestration profiles ────────────────────────────────────────────────
    "orchestrate_seo_campaign": _profile(
        "orchestrate_seo_campaign",
        allowed_tools=BASE_ALLOWED_TOOLS,
        max_turns=6,
        max_budget_usd=1.0,
        timeout_seconds=180,
        max_thinking_tokens=5000,
        episodic_limit=2,
        semantic_char_limit=2000,
        validator=_validate_orchestration_plan,
        should_resume_session=False,
        procedural_tags=["orchestration"],
    ),
    "campaign_researcher": _profile(
        "campaign_researcher",
        allowed_tools=BASE_ALLOWED_TOOLS + GSC_TOOLS,
        max_turns=14,
        max_budget_usd=2.5,
        timeout_seconds=600,
        max_thinking_tokens=6000,
        episodic_limit=3,
        semantic_char_limit=2600,
        validator=_validate_research_output,
        procedural_tags=["brand-voice", "research", "campaign", "grounding-required"],
    ),
    "campaign_draft_writer": _profile(
        "campaign_draft_writer",
        allowed_tools=EDIT_ALLOWED_TOOLS,  # file edits only — no Webflow publish
        max_turns=18,
        max_budget_usd=4.0,
        timeout_seconds=900,
        max_thinking_tokens=8000,
        episodic_limit=3,
        semantic_char_limit=3500,
        validator=_validate_blog_write,
        procedural_tags=["brand-voice", "copywriting", "campaign"],
    ),
    "campaign_publisher": _profile(
        "campaign_publisher",
        allowed_tools=BASE_ALLOWED_TOOLS + WEBFLOW_TOOLS,  # read + publish; no Write/Edit
        max_turns=8,
        max_budget_usd=1.5,
        timeout_seconds=300,
        max_thinking_tokens=3000,
        episodic_limit=2,
        semantic_char_limit=1200,
        validator=_with_change_log(_validate_non_empty),
        procedural_tags=["publish", "campaign"],
    ),
    "campaign_analyst": _profile(
        "campaign_analyst",
        allowed_tools=BASE_ALLOWED_TOOLS + GSC_TOOLS,
        max_turns=16,
        max_budget_usd=3.0,
        timeout_seconds=720,
        max_thinking_tokens=8000,
        episodic_limit=5,
        semantic_char_limit=2800,
        validator=_validate_non_empty,
        should_resume_session=False,
        procedural_tags=["feedback-loop", "campaign"],
    ),
}


def get_execution_profile(execution_type: Optional[str]) -> ExecutionProfile:
    if not execution_type:
        return PROFILE_REGISTRY["manual"]
    profile = PROFILE_REGISTRY.get(execution_type)
    if profile is None:
        raise ValueError(
            f"Unknown execution_type '{execution_type}'. "
            f"Valid types: {sorted(PROFILE_REGISTRY.keys())}"
        )
    return profile
