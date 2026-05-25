"""
AnalyticsAgent — SEO analytics and feedback loop specialist.

Scope: SEO impact reviews — comparing before/after GSC data, extracting learnings,
       propagating winning patterns.
Tools: Read, WebFetch, Bash (for localhost GSC API calls). No Write/Edit except
       to memory/seo-learnings.json and memory/seo-changes.json.
MCP: none.
"""

import logging
import os

from claude_agent_sdk import ClaudeAgentOptions

from .base import AgentContext, AgentResult, BaseSpecialistAgent

logger = logging.getLogger(__name__)


class AnalyticsAgent(BaseSpecialistAgent):
    """
    SEO analytics reviewer specialist.

    Read-only by design except for the two memory JSON files.
    Analyzes before/after GSC data, produces structured metrics reports,
    and extracts learnings for future tasks.
    """

    name = "AnalyticsAgent"

    SYSTEM_PROMPT = (
        "You are an SEO analytics reviewer. Your job is to evaluate the impact of "
        "implemented SEO changes by comparing before/after Google Search Console data, "
        "classify outcomes (positive/negative/neutral/inconclusive), extract learnings, "
        "and propagate winning patterns. You may only write to: memory/seo-learnings.json "
        "and memory/seo-changes.json. All other file operations are read-only. "
        "Use Bash only for localhost API calls (e.g. GET http://localhost:8000/tasks). "
        "Never modify CMS content or site files."
    )

    def _build_options(self) -> ClaudeAgentOptions:
        """Build read-only analytics options."""
        return ClaudeAgentOptions(
            cwd=self.base_config.cwd,
            permission_mode=self.base_config.permission_mode,
            allowed_tools=["Read", "WebFetch", "Bash"],
            setting_sources=[],
            system_prompt=self.SYSTEM_PROMPT,
            model=self.base_config.model,
            max_turns=self.base_config.max_turns,
            max_budget_usd=self.base_config.max_budget_usd,
            mcp_servers={},
        )

    def _build_prompt(self, ctx: AgentContext) -> str:
        """Build seo_impact_review prompt from the full phase instructions."""
        site_url = ctx.site_url
        seo_review_batch_size = int(os.environ.get("SEO_REVIEW_BATCH_SIZE", "20"))
        cms_types_list = "blog_write, internal_links, rewrite_blog_content, rewrite_h1, rewrite_meta_desc, rewrite_title"

        user_notes_block = ""
        if ctx.user_notes:
            notes = "\n".join(f"- {n}" for n in ctx.user_notes)
            user_notes_block = f"\n\n## User Notes\n{notes}"

        return f"""## SEO Impact Review Task

**Task:** {ctx.task_title}
{f"**Details:** {ctx.task_description}" if ctx.task_description else ""}
**Site:** {site_url}
**Pipeline stage:** {ctx.pipeline_step + 1} of {ctx.pipeline_total}
{user_notes_block}

## Instructions

You are running an SEO feedback loop impact review for {site_url}.
Execute phases in order. After each phase the system state must be valid before proceeding.

CONSTRAINTS:
- Process at most {seo_review_batch_size} pending-review entries per run (oldest logged_at first)
- Skip entry and mark reviewed-inconclusive if live data unavailable after 2 fetch attempts
- Never re-review entries already in a reviewed-* state
- Write JSON updates after each individual entry, not batched at the end

PHASE 1 — Backfill unlogged completed tasks
1. GET http://localhost:8000/tasks — collect all tasks with status=completed
2. Read memory/seo-changes.json — note all task_ids already present
3. For each completed task with execution_type in [{cms_types_list}] whose task_id is not in the log:
   Append a backfill entry to memory/seo-changes.json:
   {{
     "id": "<task_id>-<execution_type>-unknown",
     "task_id": <id>, "task_title": "<title>", "execution_type": "<type>",
     "change_type": "<mapped field>", "url": null,
     "before": null, "after": null, "extraction_status": "backfilled",
     "is_backfilled": true, "logged_at": "<task updated_at>", "attempts": 1,
     "status": "pending-review", "review_notes": null, "reviewed_at": null,
     "learning_ids": [], "failure_reason": null
   }}
4. Write memory/seo-changes.json atomically. Regenerate .claude/seo-changes-log.md.
→ State: all completed CMS tasks now have a log entry.

PHASE 2 — Load batch
1. Read memory/seo-changes.json
2. Filter entries where status = "pending-review", sort by logged_at ASC, take first {seo_review_batch_size}
3. Report: "Found N pending entries. Processing M (batch limit: {seo_review_batch_size})."
→ State: batch list defined, no mutations yet.

PHASE 3 — Evaluate each entry (sequential)
For each entry in the batch:
a. If is_backfilled=true and url=null: set status=reviewed-inconclusive,
   review_notes="backfilled — no URL to evaluate", reviewed_at=now. Write JSON. Continue.
b. WebFetch the entry url — note current value of the changed field
c. WebSearch using Bash: curl "http://localhost:8000/gsc/page-metrics?url=<url>&change_date=<logged_at[:10]>"
   to get before/after GSC data if available.
d. Classify outcome: reviewed-positive | reviewed-negative | reviewed-neutral | reviewed-inconclusive
   - positive: measurable improvement visible (ranking, snippet, field value)
   - negative: measurable regression
   - neutral: change present but no ranking signal yet
   - inconclusive: live data unavailable after 2 attempts
e. For negative: add one-line hypothesis (too soon / competitor change / intent mismatch / rolled back)
f. Set entry status, review_notes, reviewed_at=now in memory/seo-changes.json
g. Atomic write immediately after each entry — partial progress is safe on timeout

PHASE 4 — Extract learnings (positives only, skip backfilled)
For each reviewed-positive, non-backfilled entry:
1. Read memory/seo-learnings.json
2. Derive a kebab-case principle key (e.g. "buyer-intent-qualifier-in-title")
3. If key already exists: increment hit_count, add source_entry_id, update updated_at.
   Promote confidence: low→medium at 2 hits, medium→high at 4 hits.
4. If key is new: add full entry with confidence=low, hit_count=1
5. Write memory/seo-learnings.json atomically after each learning
6. Update source entry's learning_ids in memory/seo-changes.json

PHASE 5 — Refresh views
Regenerate .claude/seo-changes-log.md from memory/seo-changes.json
Regenerate .claude/seo-learnings.md from memory/seo-learnings.json

PHASE 6 — Return structured summary
Entries processed: N | Positive: N | Negative: N | Neutral: N | Inconclusive: N | Backfilled (skipped): N
New learnings: [id: principle]
Confidence updates: [id: previous→new]
Propagation opportunities: [page URL → learning to apply]
Recommended next tasks: [task title, execution_type]
"""
