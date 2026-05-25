"""
TechnicalSEOAgent — Technical SEO specialist.

Scope: schema markup (JSON-LD), alt text audits, internal link plans.
Tools: WebFetch, Skill, Read, Write.
MCP: none.
"""

import logging

from claude_agent_sdk import ClaudeAgentOptions

from .base import AgentContext, AgentResult, BaseSpecialistAgent

logger = logging.getLogger(__name__)


class TechnicalSEOAgent(BaseSpecialistAgent):
    """
    Technical SEO specialist.

    Allowed tools: WebFetch, Skill, Read, Write.
    Invokes schema-markup Skill for structured data tasks.
    Produces copy-paste-ready JSON-LD or HTML.
    Never makes automated CMS changes.
    """

    name = "TechnicalSEOAgent"

    SYSTEM_PROMPT = (
        "You are a technical SEO specialist. For schema markup tasks, invoke the "
        "schema-markup Skill before generating any JSON-LD. Produce copy-paste-ready "
        "JSON-LD or HTML implementations with step-by-step instructions for manual "
        "insertion. For alt text tasks, audit every image on the page and write "
        "descriptive, SEO-optimised alt text following WCAG guidelines. For internal "
        "link tasks, produce a prioritised link plan. Never make automated CMS changes."
    )

    def _build_options(self) -> ClaudeAgentOptions:
        """Build options with web + Skill + file-read tools."""
        return ClaudeAgentOptions(
            cwd=self.base_config.cwd,
            permission_mode=self.base_config.permission_mode,
            allowed_tools=["WebFetch", "Skill", "Read", "Write"],
            setting_sources=["user", "project"],  # needed for Skill tool
            system_prompt=self.SYSTEM_PROMPT,
            model=self.base_config.model,
            max_turns=self.base_config.max_turns,
            max_budget_usd=self.base_config.max_budget_usd,
            mcp_servers={},
        )

    def _build_prompt(self, ctx: AgentContext) -> str:
        """Build technical SEO prompt based on execution type."""
        user_notes_block = ""
        if ctx.user_notes:
            notes = "\n".join(f"- {n}" for n in ctx.user_notes)
            user_notes_block = f"\n\n## User Notes\n{notes}"

        # Extract prior research if any
        prior_research = ""
        for prior in ctx.prior_outputs:
            if prior.get("agent") == "ResearchAgent":
                prior_research = f"""
## Prior Research
{prior.get("output", "")}
"""
                break

        etype = ctx.execution_type

        if etype == "update_schema":
            task_instructions = f"""
## Task: Generate JSON-LD Schema Markup

Generate valid JSON-LD structured data for a page on {ctx.site_name} ({ctx.site_url}).

WORKFLOW — execute every step in order:

Step 1 — Invoke schema-markup Skill
Use the Skill tool to invoke the schema-markup skill. Read its guidelines and examples.

Step 2 — Fetch the current page
Use WebFetch on the URL referenced in the task.
Check what JSON-LD schemas already exist (look for <script type="application/ld+json">).
Note the page type: blog post, service page, FAQ, homepage, etc.

Step 3 — Research the correct schema type
Based on the page type, identify the appropriate schema:
- BlogPosting or Article (blog posts)
- Service (service pages)
- FAQPage (FAQ pages)
- Organization (homepage/about)
- BreadcrumbList (navigation)
Use WebFetch if needed to verify schema.org required vs recommended fields.

Step 4 — Generate the JSON-LD
Write the complete, valid JSON-LD block.
Use https://schema.org (not http://).
Include all recommended fields (not just required).
Validate mentally against the schema.org spec.

Step 5 — Produce implementation instructions
Provide step-by-step instructions for inserting the <script> block into
the page's <head> section (CMS-agnostic instructions).

Step 6 — Save to task notes. No automated CMS changes.
"""

        elif etype == "alt_text":
            task_instructions = f"""
## Task: Write Alt Text for Page Images

Audit and write descriptive alt text for all images on a page of {ctx.site_name} ({ctx.site_url}).

WORKFLOW — execute every step in order:

Step 1 — Fetch the page
Use WebFetch on the URL referenced in the task.
Find all images with empty alt="" or missing alt attributes.
Categorize them: logos, testimonials/portraits, rating stars, content images, decorative.

Step 2 — Write alt text per category
Rules by image type:
- Client logos: "[Company Name] logo"
- Testimonial portraits: "[Person Name], [Job Title] at [Company Name]"
- Rating stars: "Rating X out of 5 stars" (or aria-hidden if purely decorative)
- Content images: descriptive text of what the image shows and its purpose
- Decorative dividers/backgrounds: leave as alt="" (correct) or add aria-hidden="true"

Step 3 — Produce a report
Format as a table:
| Image Description / URL | Recommended Alt Text |
|---|---|
...

Step 4 — Save report to task notes. No automated CMS changes for this task type.
"""

        elif etype == "internal_links":
            task_instructions = f"""
## Task: Create Internal Link Plan

Create a prioritized internal link plan for pages on {ctx.site_name} ({ctx.site_url}).

WORKFLOW — execute every step in order:

Step 1 — Research site structure
Use WebFetch on {ctx.site_url}/sitemap.xml or the main URL to understand what pages exist.
Build a map of each key page: title, URL, topic/theme.

Step 2 — Use prior research if available (see above)
The research agent may have identified which pages to link.

Step 3 — Identify link opportunities
For the page(s) mentioned in the task, identify topically related pages that would benefit
from receiving or sending a link.
Prioritize: pages with overlapping topics, service pages, case studies.

Step 4 — Produce the link plan
For each recommended internal link, specify:
- Source page URL
- Target page URL
- Suggested anchor text
- Where to insert in the source page (section/paragraph hint)

Step 5 — Report:
- Link plan: [table of source → target, anchor text, insertion point]
- Priority links (most impactful 3-5): highlighted
- Manual implementation instructions
"""

        else:
            task_instructions = f"""
## Task: {ctx.task_title}

Perform technical SEO analysis for {ctx.site_name} ({ctx.site_url}).

Step 1 — Fetch the page(s) referenced in the task using WebFetch.
Step 2 — Invoke the relevant Skill (schema-markup if schema-related).
Step 3 — Produce a detailed technical report with copy-paste-ready recommendations.
Step 4 — No automated CMS changes.
"""

        return f"""## Technical SEO Task

**Task:** {ctx.task_title}
{f"**Details:** {ctx.task_description}" if ctx.task_description else ""}
**Site:** {ctx.site_url} ({ctx.site_name})
**Pipeline stage:** {ctx.pipeline_step + 1} of {ctx.pipeline_total}
{prior_research}
{task_instructions}
{user_notes_block}
"""
