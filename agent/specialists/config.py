"""
Tool Whitelist Configuration for Specialist Agents.

Defines strict tool sets per specialist based on least-privilege principle.
Each agent should only have access to tools necessary for its specific function.
"""

from typing import Final

# Strict tool sets per specialist - each agent gets minimum required tools
SPECIALIST_TOOLS: Final[dict[str, list[str]]] = {
    # ResearchAgent: Read-only web access for keyword research and SERP analysis
    "ResearchAgent": [
        "WebSearch",
        "WebFetch",
        "Read",
    ],
    # ContentAgent: File operations, skills, and optional Google Docs
    "ContentAgent": [
        "Read",
        "Write",
        "Edit",
        "Glob",
        "Grep",
        "Skill",
    ],
    # AnalyticsAgent: Read-only + localhost API calls for GSC data
    "AnalyticsAgent": [
        "Read",
        "WebFetch",
        "Bash",
    ],
    # TechnicalSEOAgent: Web fetch, file ops, and schema-markup skill
    "TechnicalSEOAgent": [
        "WebFetch",
        "Read",
        "Write",
        "Edit",
        "Skill",
    ],
}

# Google Docs MCP tools (added when Google Docs is configured)
GOOGLE_DOCS_TOOLS: list[str] = [
    "mcp__google_docs__create_google_doc",
    "mcp__google_docs__get_google_doc",
    "mcp__google_docs__append_to_google_doc",
    "mcp__google_docs__update_google_doc_title",
]


def get_allowed_tools_for_specialist(
    specialist_name: str, include_google_docs: bool = False
) -> list[str]:
    """
    Get the allowed tools for a specific specialist.

    Args:
        specialist_name: Name of the specialist agent.
        include_google_docs: Whether to include Google Docs MCP tools.

    Returns:
        List of allowed tool names.
    """
    tools = SPECIALIST_TOOLS.get(specialist_name, []).copy()

    if include_google_docs:
        tools.extend(GOOGLE_DOCS_TOOLS)

    return tools


def validate_tool_access(specialist_name: str, requested_tools: list[str]) -> tuple[bool, list[str]]:
    """
    Validate that requested tools are within the specialist's allowed tools.

    Args:
        specialist_name: Name of the specialist agent.
        requested_tools: List of tools requested by the agent.

    Returns:
        Tuple of (is_valid, disallowed_tools).
    """
    allowed = set(get_allowed_tools_for_specialist(specialist_name))
    requested = set(requested_tools)

    disallowed = list(requested - allowed)
    return len(disallowed) == 0, disallowed