# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- **Research Learnings Integration** — 6-phase implementation based on RESEARCH-LEARNINGS.md analysis
  - Phase 1: Supervisor Logging — `SupervisorLogger` class with JSON Lines logging to `memory/supervisor.log`
  - Phase 2: Retry Logic — `agent/retry.py` with exponential backoff and configurable retry conditions
  - Phase 3: Validation Layer — `agent/validators/` package with 4 validators (Research, Content, TechnicalSEO, Analytics)
  - Phase 4: Automated Feedback Loop — `FeedbackLoopOrchestrator` with auto-change detection
  - Phase 5: Programmatic SEO Expansion — `TemplatedPageGenerator`, `BulkPageProcessor`, and new pipelines
  - Phase 6: Tool Whitelisting — Strict tool sets per specialist in `agent/specialists/config.py`
- `agent/__init__.py` — Updated exports for new modules (SupervisorLogger, RetryConfig, FeedbackLoopOrchestrator, etc.)
- `memory/CLAUDE.md` — Added Agent Capabilities & Tool Whitelisting documentation section
- `memory/seo-context.md` — Added Feedback Loop State and Programmatic SEO Jobs tracking sections
- `Skills/programmatic-seo/references/` — Added 3 new playbooks (bulk-page-templates, location-page-playbook, comparison-page-playbook)

### Changed
- `agent/config.py` — Added RetryConfig, enable_supervisor_logging, enable_validation settings
- `agent/orchestrator.py` — Integrated SupervisorLogger, AGENT_VALIDATORS, feedback loop with new pipelines
- `agent/specialists/base.py` — Added retry loop with exponential backoff, tool whitelisting enforcement

### New Files
- `agent/retry.py` — RetryConfig, RetryMetrics, with_retry() decorator
- `agent/feedback_loop.py` — FeedbackLoopOrchestrator, ChangeEntry
- `agent/programmatic.py` — TemplatedPageGenerator, BulkPageProcessor
- `agent/specialists/config.py` — SPECIALIST_TOOLS whitelist definitions
- `agent/validators/__init__.py`, `base.py`, `research_validator.py`, `content_validator.py`, `technical_seo_validator.py`, `analytics_validator.py`

## [2.0.0] - 2026-05-25

### Added
- **Multi-Channel Agent Orchestrator** — deterministic pipeline routing to specialist agents
  - `OrchestratorAgent` — routes tasks to specialist pipelines by `execution_type`
  - `ResearchAgent` — web research and keyword analysis (tools: WebSearch, WebFetch)
  - `ContentAgent` — copywriting and content generation (tools: Read, Write, Edit, Skill, optional Google Docs MCP)
  - `AnalyticsAgent` — SEO impact review and GSC analysis (tools: Read, WebFetch, Bash — read-only)
  - `TechnicalSEOAgent` — schema, alt text, internal links (tools: WebFetch, Skill, Read, Write)
  - `AgentContext` / `AgentResult` dataclasses for structured inter-agent handoff
  - Observable orchestration: `🔄 / ✅ / ❌` progress comments posted to Kanban after each stage
  - Pipeline registry (`AGENT_PIPELINE`) — maps each `execution_type` to an ordered list of agents
- `agent/specialists/` package — base class + 4 concrete specialist agents
- `agent/orchestrator.py` — OrchestratorAgent with legacy fallback for unknown execution types
- `agent/sdk_compat.py` — shared, idempotent SDK monkey-patch module for unknown message types

### Changed
- `agent/api/main.py` — `execute_task` endpoint now routes via `OrchestratorAgent`
- `agent/config.py` — site identity read from `TARGET_SITE_URL` / `TARGET_SITE_NAME` env vars; Claude CLI resolved via `shutil.which` or `CLAUDE_CLI_PATH` env var
- `agent/__init__.py` — exports `OrchestratorAgent` and all 4 specialist agents
- `memory/CLAUDE.md` and `.claude/CLAUDE.md` — fully sanitised to generic placeholders
- `memory/seo-context.md` and `memory/seo-strategy.md` — replaced with generic templates (git-ignored)
- `.env.example` — added `TARGET_SITE_URL`, `TARGET_SITE_NAME`, `TARGET_SITEMAP_URL`

### Removed
- `agent/webflow/` module (5 files) — Webflow CMS integration removed
- `PLAN.md` — internal implementation notes, not needed for production
- `References/` — Claude SDK reference docs, superseded by upstream docs

### Security
- Hardcoded site-specific paths and credential references replaced with env-var-driven config
- Google SA credentials folder git-untracked and excluded via `.gitignore`
- Confidential memory files (`seo-context.md`, `seo-strategy.md`, `seo-changes.json`, `seo-learnings.json`) added to `.gitignore`

## [1.9.0] - 2026-04-09

### Added
- **Execution type now editable on existing tasks** — the task detail modal includes an "Execution Type" dropdown, allowing users to change a task's type after creation. Change is saved via the existing `PATCH /tasks/{id}` endpoint and the Execute button updates accordingly.
- **Mandatory brand voice check before all content-writing executions** — `build_execution_prompt` now injects a hard-coded first step for all execution types except `manual` and `webflow_publish`: the agent must invoke the `brand-voice` skill and internalize its guidelines before producing any copy. Applies to: `rewrite_title`, `rewrite_meta_desc`, `rewrite_h1`, `blog_write`, `rewrite_blog_content`, `internal_links`, `research`, `alt_text`, `update_schema`, `seo_impact_review`.

## [1.8.0] - 2026-03-19

### Added
- **SEO Feedback Loop** — deterministic application-layer change logging and impact review system
  - `CMS_CHANGE_FIELD_MAP` — single registry mapping 7 CMS execution types to change-type labels
  - `_parse_change_log_block()` — extracts structured `<!-- CHANGE_LOG {...} -->` block from agent output
  - `_write_change_log_entry()` — upserts idempotent entries to `memory/seo-changes.json`
  - `_build_change_id()` — deterministic key `"{task_id}-{execution_type}-{url_slug}"` for deduplication
  - `_atomic_json_write()` — all JSON writes via temp file + `os.replace()` for write safety
  - `_render_changes_markdown()` / `_render_learnings_markdown()` — JSON → readable markdown views
  - `_refresh_markdown_views()` — regenerates `.claude/seo-changes-log.md` and `.claude/seo-learnings.md`
  - `seo_impact_review` execution type — 6-phase review: backfill → batch → evaluate → learnings → refresh → comment
  - `seo-feedback-loop.skill` — packaged with 5 reference files (3 samples + 2 templates)
- `execute_task` deterministically calls `_write_change_log_entry` after every CMS task
- `VALID_REVIEW_STATUSES` set enforces formal status lifecycle

### Tests
- 32 new tests in `tests/test_seo_feedback_loop.py`

## [1.7.0] - 2026-03-19

### Added
- 5 new skills with structured references:
  - **Page CRO** (`page-cro.skill`) — includes `references/experiments.md`
  - **Marketing Psychology** (`marketing-psychology.skill`) — behavioral science for marketing
  - **Analytics Tracking** (`analytics-tracking.skill`) — GA4, GTM, event tracking; includes 3 reference files
  - **Programmatic SEO** (`programmatic-seo.skill`) — includes `references/playbooks.md`
  - **Schema Markup** (`schema-markup.skill`) — includes `references/schema-examples.md`
- Updated **Copy Editing** skill now includes `references/plain-english-alternatives.md`

## [1.6.0] - 2026-03-19

### Added
- User comments now included in task execution prompts (`## User Notes` section)
- Autopilot stale-comment skip — `@agent` comments skipped if task was re-executed after the comment

### Changed
- Reduced default autopilot polling interval from 900s to 300s

### Tests
- 6 new tests in `tests/test_execution_prompts.py` for comment injection
- 5 new tests in `tests/test_comment_autopilot.py` for stale-skip and interval

## [1.5.0] - 2026-03-05

### Added
- Explicit Kanban API DB environment resolution:
  - `APP_ENV=production` → `sqlite:///./kanban.db`
  - `APP_ENV=staging` → `sqlite:///./kanban.staging.db`
  - `DATABASE_URL` override takes precedence
- Comment-driven autopilot execution for task revisions (`@agent` trigger)
- `comment_actions` table with attempts/status tracking
- Shared agent execution timeout: `AGENT_EXECUTION_TIMEOUT_SECONDS` (default 900)
- Test DB isolation fixture: `tests/conftest.py` uses in-memory SQLite with `StaticPool`
- `.env.example` documenting runtime environment variables
- `DECISIONS.md` with database environment design decision

### Tests
- `tests/test_db_env_config.py` (5 tests)
- `tests/test_comment_autopilot.py` (6 tests)

## [1.4.0] - 2026-06-03

### Added
- Google Docs Integration — save SEO audit reports and blog content to Google Docs
- `agent/google_docs/` module with config, client, tools, server
- Google Docs MCP tools: create, read, append, update title (no delete by design)
- `google-docs` skill — agent saves SEO outputs to Google Docs

### Dependencies
- Added google-api-python-client>=2.100.0, google-auth-httplib2>=0.1.0, google-auth-oauthlib>=0.8.0

## [1.3.0] - 2026-04-03

### Added
- Kanban UI — visual task management interface
- FastAPI server with REST API for task management (`agent/api/main.py`)
- Task CRUD endpoints (GET/POST/PATCH/DELETE /tasks)
- Execute task endpoint using SEOAgent
- Comments endpoint for task collaboration
- 4-column Kanban board (Pending, In Progress, Completed, Blocked)
- Task cards with priority, execution type, due dates
- SQLite database for task storage via SQLAlchemy ORM

## [1.2.1] - 2026-03-03

### Fixed
- Webflow API integration now uses v2 API (`https://api.webflow.com/v2`)
- Changed `list_items` endpoint to `/items/live` to fetch published items

## [1.2.0] - 2026-03-03

### Changed
- Replaced subprocess-based Claude Code CLI calls with Claude Agent SDK
- Added claude-agent-sdk>=0.1.44 to requirements.txt

### Added
- Comprehensive pytest test suite with 25 tests
- Tests for Memory System, Skills, Interrupt Feature, Session Continuity

## [1.1.0] - 2026-02-24

### Added
- Memory-based workflow for persistent context across sessions
- `memory/CLAUDE.md` — site overview, target keywords, content gaps template
- `memory/seo-strategy.md` — detailed strategy that evolves over time
- `memory/seo-context.md` — sprint state tracking (tickets, pending actions)
- Symlinked `memory/CLAUDE.md` to `.claude/CLAUDE.md` for auto-loading

## [1.0.0] - 2026-02-24

### Added
- Initial release of SEO Autonomous Agent
- Claude Agent SDK integration (OAuth authentication, no API key required)
- 9 SEO skills (seo-audit, content-strategy, copywriting, copy-editing, brand-voice, competitor-alternatives, programmatic-seo, schema-markup, analytics-tracking)
- CLI entry point (`main.py`)
- Configuration system (`agent/config.py`)