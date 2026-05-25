# SEO Agent Memory

This file provides context for every SEO agent session. Claude Code loads this automatically at session start.

## Setup Instructions

1. Copy this template as `memory/CLAUDE.md`
2. Fill in your site-specific information
3. The file is NOT git-ignored (generic template only) — customize for your site

## Site Overview

- **Site name:** [YOUR_SITE_NAME]
- **URL:** [YOUR_SITE_URL]
- **Industry:** [YOUR_INDUSTRY]
- **Primary audience:** [YOUR_TARGET_AUDIENCE — e.g., COO, CEO, Founders of SMBs]
- **Project size / AOV:** [YOUR_PROJECT_SIZE]

## Target Keywords (Priority Order)

### Primary (Commercial — Service Pages)
1. **[YOUR_PRIMARY_KEYWORD_1]** — est. [VOLUME]/mo — commercial — [SERP_NOTES]
2. **[YOUR_PRIMARY_KEYWORD_2]** — est. [VOLUME]/mo — commercial — [SERP_NOTES]
3. **[YOUR_PRIMARY_KEYWORD_3]** — est. [VOLUME]/mo — commercial — [SERP_NOTES]

### Secondary (Informational — Blog Content)
4. **[YOUR_SECONDARY_KEYWORD_1]** — est. [VOLUME]/mo — informational — [SERP_NOTES]
5. **[YOUR_SECONDARY_KEYWORD_2]** — est. [VOLUME]/mo — informational — [SERP_NOTES]

### Tertiary (Navigational / Branded)
6. **[YOUR_BRAND_NAME]** — branded — [RANK_STATUS]

## Content Gaps

- [ ] [CONTENT_GAP_1]: [DESCRIPTION]
- [ ] [CONTENT_GAP_2]: [DESCRIPTION]
- [ ] [CONTENT_GAP_3]: [DESCRIPTION]

## What NOT to Do

- Don't target [COMPETITOR_KEYWORD_1] — [REASON]
- Don't use "[BANNED_PHRASE]" in page titles — [REASON]
- [ADDITIONAL_RESTRICTIONS]

## Site-Specific SEO Learnings

Before writing titles, meta descriptions, H1s, or content recommendations, read `.claude/seo-learnings.md` if it exists.
These are principles extracted from measured ranking changes on this site. Prefer them over generic best practices.

## ⚠️ Copy Writing Rules (Apply Globally)

- [BRAND_VOICE_RULE_1]
- [BRAND_VOICE_RULE_2]
- [BRAND_VOICE_RULE_3]

## SERP Competitive Intelligence

### "[YOUR_PRIMARY_KEYWORD_1]" SERP (top results):
1. [COMPETITOR_1] — [NOTES]
2. [COMPETITOR_2] — [NOTES]
3. [YOUR_SITE] — [RANK_STATUS]

## Current Sprint Focus

See `seo-context.md` for active tickets and current work.

---

## Agent Capabilities & Tool Whitelisting

The SEO bot orchestrator uses specialized agents with strict tool permissions following the least-privilege principle.

### Specialist Agents

| Agent | Purpose | Allowed Tools |
|-------|---------|--------------|
| **ResearchAgent** | Keyword research, SERP analysis, competitor research | WebSearch, WebFetch, Read |
| **ContentAgent** | Blog posts, title/meta rewrites, content optimization | Read, Write, Edit, Glob, Grep, Skill |
| **TechnicalSEOAgent** | Schema markup, alt text, internal links | WebFetch, Read, Write, Edit, Skill |
| **AnalyticsAgent** | GSC impact reviews, learning extraction | Read, WebFetch, Bash (localhost only) |

### Tool Descriptions

- **WebSearch**: Search the web for keywords, competitors, SERP data
- **WebFetch**: Fetch page content for analysis
- **Read**: Read files from the local codebase
- **Write**: Write files to the local codebase
- **Edit**: Edit existing files
- **Glob**: Find files by pattern
- **Grep**: Search file contents
- **Skill**: Invoke skill prompts (brand-voice, copywriting, etc.)
- **Bash**: Execute shell commands (AnalyticsAgent only for localhost GSC API)

### Execution Types & Pipelines

| Execution Type | Agent Pipeline |
|---------------|---------------|
| `research` | ResearchAgent only |
| `rewrite_title` | ResearchAgent → ContentAgent |
| `rewrite_meta_desc` | ResearchAgent → ContentAgent |
| `rewrite_h1` | ResearchAgent → ContentAgent |
| `blog_write` | ResearchAgent → ContentAgent |
| `rewrite_blog_content` | ResearchAgent → ContentAgent |
| `update_schema` | TechnicalSEOAgent only |
| `alt_text` | TechnicalSEOAgent only |
| `internal_links` | ResearchAgent → TechnicalSEOAgent |
| `seo_impact_review` | AnalyticsAgent only |

### Quality Validation

Each agent output is validated against quality thresholds:
- **ResearchValidator**: Checks for keywords, competitors, title options, structured data
- **ContentValidator**: Checks word count, heading structure, required fields
- **TechnicalSEOValidator**: Checks JSON-LD validity, schema.org compliance, alt text format
- **AnalyticsValidator**: Checks for complete phases, learning extraction, next steps

### Feedback Loop

Changes are automatically logged to `memory/seo-changes.json` when agents output `<!-- CHANGE_LOG {...} -->` blocks. Impact reviews are triggered automatically after 14 days or when 5+ pending changes exist.
