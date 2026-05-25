"""
ResearchAgent — SEO research specialist.

Scope: keyword research, competitor analysis, SERP analysis, content gap discovery.
Tools: WebSearch, WebFetch only. No file writes. No MCP servers.
Output: structured research report ending with <!-- RESEARCH_OUTPUT {...} -->.
"""

import logging

from claude_agent_sdk import ClaudeAgentOptions

from .base import AgentContext, AgentResult, BaseSpecialistAgent

logger = logging.getLogger(__name__)


class ResearchAgent(BaseSpecialistAgent):
    """
    SEO research analyst specialist.

    Allowed tools: WebSearch, WebFetch.
    No MCP servers — read-only web access only.
    Never modifies files or CMS content.
    """

    name = "ResearchAgent"

    SYSTEM_PROMPT = (
        "You are an SEO research analyst. Your only job is to gather data using "
        "WebSearch and WebFetch — you must never modify files, write to disk, or "
        "make CMS changes. Produce a structured research report covering: keyword "
        "intent, top 5 competitor pages (titles, word counts, structure), content "
        "gaps, and 3 concrete title/angle options. End your response with a machine-"
        "readable block: <!-- RESEARCH_OUTPUT {\"primary_keyword\": \"...\", "
        "\"competitors\": [], \"title_options\": []} -->"
    )

    def _build_options(self) -> ClaudeAgentOptions:
        """Build options with read-only web tools only."""
        return ClaudeAgentOptions(
            cwd=self.base_config.cwd,
            permission_mode=self.base_config.permission_mode,
            allowed_tools=["WebSearch", "WebFetch"],
            setting_sources=[],
            system_prompt=self.SYSTEM_PROMPT,
            model=self.base_config.model,
            max_turns=self.base_config.max_turns,
            max_budget_usd=self.base_config.max_budget_usd,
            mcp_servers={},
        )

    def _build_prompt(self, ctx: AgentContext) -> str:
        """Build research prompt from task context."""
        user_notes_block = ""
        if ctx.user_notes:
            notes = "\n".join(f"- {n}" for n in ctx.user_notes)
            user_notes_block = f"\n\n## User Notes\n{notes}"

        return f"""## SEO Research Task

**Task:** {ctx.task_title}
{f"**Details:** {ctx.task_description}" if ctx.task_description else ""}
**Site:** {ctx.site_url} ({ctx.site_name})
**Pipeline stage:** {ctx.pipeline_step + 1} of {ctx.pipeline_total}{user_notes_block}

## Research Instructions

WORKFLOW — execute every step in order:

Step 1 — Understand the research question
Parse the task title and description to identify what needs researching
(keywords, competitors, content gaps, audience intent, etc.)

Step 2 — Keyword research
Use WebSearch to identify:
- The primary keyword and its estimated monthly search volume
- The top 5 ranking pages (their titles, H1s, approximate word counts)
- Secondary keywords and related questions (People Also Ask)
Search: "[topic] keyword research", "[topic] how to", "[topic] guide"

Step 3 — Competitor analysis
For the top 3-5 results, use WebFetch to inspect their pages:
- Page title, H1, and meta description
- Approximate word count and content structure (H2 sections)
- Unique angles, data points, or formats they use

Step 4 — Synthesize findings
Produce a structured report with:
- Primary keyword recommendation (with estimated search volume if findable)
- Competitor analysis: who ranks, why they rank, gaps you can exploit
- Specific actionable recommendations for {ctx.site_url}
- 3 concrete title options (50-60 chars, keyword-first)
- Suggested next tasks with their execution types (e.g., rewrite_title, blog_write)

End your response with:
<!-- RESEARCH_OUTPUT
{{
  "primary_keyword": "<keyword>",
  "search_volume_estimate": "<est. X/mo>",
  "competitors": [
    {{"url": "<url>", "title": "<title>", "word_count": <n>}}
  ],
  "title_options": ["<option 1>", "<option 2>", "<option 3>"],
  "content_gaps": ["<gap 1>", "<gap 2>"]
}}
-->
"""
