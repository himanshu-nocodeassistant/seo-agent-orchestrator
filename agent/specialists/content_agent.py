"""
ContentAgent — SEO content writing specialist.

Scope: blog posts, title rewrites, meta description rewrites, H1 rewrites,
       blog content rewrites. Uses Skill tool for brand-voice and copywriting.
Tools: Read, Write, Edit, Skill. Google Docs MCP tools when configured.
MCP: google_docs (optional, from config).
"""

import logging

from claude_agent_sdk import ClaudeAgentOptions

from .base import AgentContext, AgentResult, BaseSpecialistAgent

logger = logging.getLogger(__name__)


class ContentAgent(BaseSpecialistAgent):
    """
    SEO content writer specialist.

    Allowed tools: Read, Write, Edit, Skill (+ Google Docs MCP tools if configured).
    Invokes brand-voice Skill before producing any copy.
    For blog posts: invokes copywriting Skill.
    For edits: invokes copy-editing Skill.
    """

    name = "ContentAgent"

    SYSTEM_PROMPT = (
        "You are an SEO content writer. Before producing any copy, invoke the "
        "brand-voice Skill to apply brand voice rules. For new blog posts, invoke "
        "the copywriting Skill. For edits to existing content, invoke the copy-editing "
        "Skill. Produce publish-ready copy that is keyword-optimised, human-first, "
        "and targeted at the site's primary audience. Never change CMS content directly — "
        "output the final copy in your response for manual review and publishing."
    )

    def _build_options(self) -> ClaudeAgentOptions:
        """Build options with file + Skill tools and optional Google Docs MCP."""
        # Include Google Docs MCP tools if the config has them
        mcp_servers = {}
        allowed_tools = ["Read", "Write", "Edit", "Skill"]

        if self.base_config.google_docs_config is not None:
            # Delegate to config's MCP setup (already wired in AgentConfig.__post_init__)
            mcp_servers = dict(self.base_config.mcp_servers)
            google_docs_tools = [
                "mcp__google_docs__create_google_doc",
                "mcp__google_docs__get_google_doc",
                "mcp__google_docs__append_to_google_doc",
                "mcp__google_docs__update_google_doc_title",
            ]
            allowed_tools = allowed_tools + google_docs_tools

        return ClaudeAgentOptions(
            cwd=self.base_config.cwd,
            permission_mode=self.base_config.permission_mode,
            allowed_tools=allowed_tools,
            setting_sources=["user", "project"],  # needed for Skill tool
            system_prompt=self.SYSTEM_PROMPT,
            model=self.base_config.model,
            max_turns=self.base_config.max_turns,
            max_budget_usd=self.base_config.max_budget_usd,
            mcp_servers=mcp_servers,
        )

    def _build_prompt(self, ctx: AgentContext) -> str:
        """Build content prompt, incorporating research from prior pipeline stages."""
        # Extract prior research output if present
        prior_research = ""
        for prior in ctx.prior_outputs:
            if prior.get("agent") == "ResearchAgent":
                prior_research = f"""
## Research Findings (from ResearchAgent)

{prior.get("output", "")}
"""
                break

        user_notes_block = ""
        if ctx.user_notes:
            notes = "\n".join(f"- {n}" for n in ctx.user_notes)
            user_notes_block = f"\n\n## User Notes\n{notes}"

        etype = ctx.execution_type

        if etype == "blog_write":
            task_instructions = f"""
## Task: Write New Blog Post

Write a complete, publish-ready blog post for {ctx.site_name} ({ctx.site_url}).

WORKFLOW — execute every step in order:

Step 1 — Apply brand voice
Use the Skill tool to invoke the brand-voice skill. Read its guidelines carefully
before writing a single word of copy.

Step 2 — Create outline (if research available, build on it; otherwise research first)
- SEO title (50-60 chars, keyword-first, ends with "| {ctx.site_name}")
- Meta description (150-160 chars)
- H1 (matches or is close to the SEO title)
- H2 sections with supporting H3s
- Target word count: 800-1500 words

Step 3 — Write the post
Use the Skill tool to invoke the copywriting skill.
Write the full post following the outline. Must include:
- Primary keyword in first 100 words
- Keyword density ~1-2% (natural usage)
- 2-3 internal links to other {ctx.site_url} pages
- CTA at the end pointing to the site's services

Step 4 — Finalize draft
Present clearly:
- SEO title
- Meta description
- Slug suggestion
- Full post content
- Excerpt (2-sentence summary)

Step 5 — Report:
- Title: [title]
- URL slug: [slug]
- Word count: [count]
- Primary keyword targeted: [keyword]
"""
        elif etype in ("rewrite_title", "rewrite_meta_desc", "rewrite_h1"):
            field_map = {
                "rewrite_title": ("page title", "50-60 characters"),
                "rewrite_meta_desc": ("meta description", "150-160 characters"),
                "rewrite_h1": ("H1 heading", "under 70 characters"),
            }
            field_name, char_rule = field_map[etype]

            task_instructions = f"""
## Task: Rewrite {field_name.title()}

Produce the final {field_name} for {ctx.site_name} ({ctx.site_url}).

WORKFLOW — execute every step in order:

Step 1 — Apply brand voice
Use the Skill tool to invoke the brand-voice skill before writing any copy.

Step 2 — Use research findings above
Extract the primary keyword, competitor analysis, and title options from the research.

Step 3 — Write options
Produce 3 options for the {field_name}. Rules:
- {char_rule}
- Primary keyword near the beginning
- Direct and clear — no filler qualifiers
{"- Ends with: '| " + ctx.site_name + "'" if etype == "rewrite_title" else ""}

Step 4 — Select and finalize
Pick the strongest option. Present:
- Final draft: [the best option]
- 2 backup options
- Keyword rationale
"""
        elif etype in ("rewrite_blog_content",):
            task_instructions = f"""
## Task: Rewrite Blog Content

Rewrite existing blog content for {ctx.site_name} ({ctx.site_url}) for better SEO.

WORKFLOW — execute every step in order:

Step 1 — Apply brand voice
Use the Skill tool to invoke the brand-voice skill.

Step 2 — Use research findings above
Identify what keyword target to update, what sections to improve.

Step 3 — Rewrite
Use the Skill tool: invoke the copy-editing skill for targeted improvements,
or copywriting skill for a full rewrite if the content is poor.
Apply: better keyword targeting, improved structure, internal links.

Step 4 — Finalize revised draft
Present clearly:
- Revised title (if changed)
- Revised SEO title/meta description
- Full revised content

Step 5 — Report what changed: content, title, meta desc, keyword target
"""
        else:
            task_instructions = f"""
## Task: {ctx.task_title}

Produce high-quality, publish-ready SEO copy for {ctx.site_name} ({ctx.site_url}).

Step 1 — Apply brand voice: invoke the brand-voice Skill.
Step 2 — Use research findings if available.
Step 3 — Write the copy with keyword focus and clear CTAs.
Step 4 — Present the final output clearly.
"""

        return f"""## SEO Content Task

**Task:** {ctx.task_title}
{f"**Details:** {ctx.task_description}" if ctx.task_description else ""}
**Site:** {ctx.site_url} ({ctx.site_name})
**Pipeline stage:** {ctx.pipeline_step + 1} of {ctx.pipeline_total}
{prior_research}
{task_instructions}
{user_notes_block}
"""
