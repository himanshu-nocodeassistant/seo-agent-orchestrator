# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

## [1.9.0] - 2026-04-09

### Added
- **Execution type now editable on existing tasks** — the task detail modal includes an "Execution Type" dropdown, allowing users to change a task's type after creation. Change is saved via the existing `PATCH /tasks/{id}` endpoint and the Execute button updates accordingly.
- **Mandatory brand voice check before all content-writing executions** — `build_execution_prompt` now injects a hard-coded first step for all execution types except `manual` and `webflow_publish`: the agent must invoke the `brand-voice` skill and internalize its guidelines before producing any copy. Applies to: `rewrite_title`, `rewrite_meta_desc`, `rewrite_h1`, `blog_write`, `rewrite_blog_content`, `internal_links`, `research`, `alt_text`, `update_schema`, `seo_impact_review`.

## [1.8.0] - 2026-03-19

### Added
- **SEO Feedback Loop** — deterministic application-layer change logging and impact review system
  - `CMS_CHANGE_FIELD_MAP` — single registry mapping 7 CMS execution types to change-type labels; all feedback-loop logic derives from this
  - `_parse_change_log_block()` — extracts structured `<!-- CHANGE_LOG {...} -->` block from agent output; returns `failure_reason` in `{missing_block, invalid_json, missing_required_fields, field_mismatch}`
  - `_write_change_log_entry()` — upserts idempotent entries to `memory/seo-changes.json`; always writes even on failed extraction (never silent loss)
  - `_build_change_id()` — deterministic key `"{task_id}-{execution_type}-{url_slug}"` for deduplication and retry safety
  - `_atomic_json_write()` — all JSON writes via temp file + `os.replace()` for write safety
  - `_render_changes_markdown()` / `_render_learnings_markdown()` — JSON → readable markdown views
  - `_refresh_markdown_views()` — regenerates `.claude/seo-changes-log.md` and `.claude/seo-learnings.md` after every JSON write
  - `_change_log_block_instruction()` — per-type structured output contract appended to agent prompts for 7 CMS branches
  - `seo_impact_review` execution type — 6-phase review prompt: backfill unlogged tasks → batch pending entries → evaluate each (WebSearch/WebFetch) → extract learnings → refresh views → post summary comment
  - `seo-feedback-loop.skill` — packaged with 5 reference files (3 samples + 2 templates) following the `.skill` ZIP convention
- `execute_task` now deterministically calls `_write_change_log_entry` after every CMS task — agent cannot skip logging; failures surface as task comment, never crash the task
- `VALID_REVIEW_STATUSES` set enforces formal status lifecycle: `pending-review → reviewed-positive | reviewed-negative | reviewed-neutral | reviewed-inconclusive`
- `seo_impact_review` added to `EXECUTABLE_TYPES` and to the Task Breakdown skill mapping in `run_seo_audit`
- `memory/CLAUDE.md` — agent now instructed to read `.claude/seo-learnings.md` before writing any SEO copy (site-specific learned patterns take precedence over generic best practices)
- `memory/seo-changes.json` and `memory/seo-learnings.json` — structured JSON sources of truth (created on first task completion)

### Tests
- 32 new tests in `tests/test_seo_feedback_loop.py` covering all new functions and integration paths (TDD: red → green)
- All 14 pre-existing failures in `test_seo_agent.py` confirmed pre-existing; zero regressions introduced

## [1.7.0] - 2026-03-19

### Added
- 5 new skills with structured references:
  - **Page CRO** (`page-cro.skill`) — conversion rate optimization for marketing pages; includes `references/experiments.md`
  - **Marketing Psychology** (`marketing-psychology.skill`) — behavioral science and persuasion frameworks for marketing
  - **Analytics Tracking** (`analytics-tracking.skill`) — GA4, GTM, and event tracking; includes 3 reference files (event-library, ga4-implementation, gtm-implementation)
  - **Programmatic SEO** (`programmatic-seo.skill`) — template-driven SEO at scale; includes `references/playbooks.md`
  - **Schema Markup** (`schema-markup.skill`) — updated with `references/schema-examples.md` (complete JSON-LD examples)
- Updated **Copy Editing** skill (`copy-editing.skill`) now includes `references/plain-english-alternatives.md`
- All new skills follow the structured format: `SKILL.md` + `references/` + `evals/evals.json`

### Changed
- CLAUDE.md updated to document all available skills including references bundled in each `.skill` ZIP

## [1.6.0] - 2026-03-19

### Added
- User comments now included in task execution prompts:
  - All user-authored comments on a task are appended as `## User Notes` when the Execute button is used
  - `build_execution_prompt` accepts an optional `comments` parameter; `_append_user_notes` helper handles formatting
  - No `@agent` prefix needed — plain notes like "keep it casual" are automatically factored in
- Autopilot stale-comment skip:
  - `@agent` comments are skipped if the task was already executed after the comment was posted (`task.updated_at > comment.created_at`)
  - Prevents duplicate re-execution when user clicks Execute after leaving an `@agent` comment

### Changed
- Reduced default autopilot polling interval from 900s (15 min) to 300s (5 min)

### Tests
- 6 new tests in `tests/test_execution_prompts.py` for comment injection
- 5 new tests in `tests/test_comment_autopilot.py` for stale-skip and interval (45 total passing)

## [1.5.0] - 2026-03-05

### Added
- Explicit Kanban API DB environment resolution in `agent/api/main.py`:
  - `APP_ENV=production` -> `sqlite:///./kanban.db`
  - `APP_ENV=staging` -> `sqlite:///./kanban.staging.db`
  - `DATABASE_URL` override takes precedence over `APP_ENV`
- Comment-driven autopilot execution for task revisions:
  - Trigger: user comments starting with `@agent`
  - Tracking table: `comment_actions` with attempts/status (`pending`, `running`, `succeeded`, `failed`, `retry_exhausted`)
  - Internal background poller processes one comment per cycle
  - Manual admin endpoint: `POST /automation/comments/process-one`
- Shared agent execution timeout control: `AGENT_EXECUTION_TIMEOUT_SECONDS` (default 900)
- Test DB isolation fixture: `tests/conftest.py` uses in-memory SQLite with `StaticPool`
- Added `.env.example` documenting runtime environment variables
- Added `DECISIONS.md` with database environment design decision

### Tests
- `tests/test_db_env_config.py` (5 tests)
- `tests/test_comment_autopilot.py` (6 tests)

## [1.4.0] - 2026-06-03

### Added
- Google Docs Integration - save SEO audit reports and blog content to Google Docs
- `agent/google_docs/` module with config, client, tools, server
- Google Docs MCP tools:
  - `create_google_doc` - Create new document
  - `get_google_doc` - Read document by ID
  - `append_to_google_doc` - Append content to document
  - `update_google_doc_title` - Update document title
- google-docs skill - Agent now mandatory saves SEO outputs to Google Docs
- 43 new tests for Google Docs integration

### Features
- No delete capability (by design for security)
- Auto-configured via `GOOGLE_DOCS_CREDENTIALS_PATH` environment variable
- Uses existing Google Service Account credentials

### Security
- Delete operations intentionally disabled - documents cannot be deleted
- Preserves audit reports and blog content

### Updated Skills
- seo-audit skill now requires saving reports to Google Docs

### Dependencies
- Added google-api-python-client>=2.100.0
- Added google-auth-httplib2>=0.1.0
- Added google-auth-oauthlib>=0.8.0

## [1.3.0] - 2026-04-03

### Added
- Kanban UI - visual task management interface
- FastAPI server with REST API for task management (`agent/api/main.py`)
- Task CRUD endpoints (GET/POST/PATCH/DELETE /tasks)
- Execute task endpoint using SEOAgent
- Comments endpoint for task collaboration
- SEO Audit endpoint (`POST /runs/{run_id}/seo-audit`)
- Health check endpoint (`GET /health`)
- Kanban HTML with same styling as seo-agent (DM Sans, Tailwind)
- No authentication required (unlike seo-agent)

### Features
- 4-column Kanban board (Pending, In Progress, Completed, Blocked)
- Stats bar with task counts
- Task cards with priority, execution type, due dates
- Task detail modal with status controls
- Comments system
- Execute tasks via SEOAgent
- Run Audit button

### Technical
- Added FastAPI, SQLAlchemy, Uvicorn dependencies
- SQLite database for task storage
- branch: feature/kanban-ui

## [1.2.1] - 2026-03-03

### Fixed
- Webflow API integration now uses v2 API (`https://api.webflow.com/v2`)
- Changed `list_items` endpoint from `/items` to `/items/live` to fetch published items
- Updated CLAUDE.md with Webflow pagination docs and API details

### Changed
- Base URL in `agent/webflow/config.py` updated to v2

## [1.2.0] - 2026-03-03

### Changed
- Replaced subprocess-based Claude Code CLI calls with Claude Agent SDK
- SDK provides better async support and cleaner API
- Added claude-agent-sdk>=0.1.44 to requirements.txt

### Added
- Comprehensive pytest test suite with 25 tests
- Tests for Memory System, Skills, Interrupt Feature, Session Continuity
- Integration tests for full interactive sessions
- tests/ directory with test_seo_agent.py
- Testing dependencies: pytest>=9.0.0, pytest-asyncio>=1.3.0

### Fixed
- Resolved "ProcessTransport is not ready for writing" error
- Proper async generator mocking in tests

## [1.1.0] - 2026-02-24

### Added
- Memory-based workflow for persistent context across sessions
- `memory/CLAUDE.md` - Site overview, target keywords, content gaps template
- `memory/seo-strategy.md` - Detailed strategy that evolves over time
- `memory/seo-context.md` - Sprint state tracking (tickets, pending actions)
- Symlinked `memory/CLAUDE.md` to `.claude/CLAUDE.md` for auto-loading
- Auto-update of seo-context.md after each task

### Features
- Agent loads memory context at session start
- Claude is instructed to update context file with tickets created
- Last session info tracked for continuity

## [1.0.0] - 2026-02-24

### Added
- Initial release of SEO Autonomous Agent
- Claude Code CLI integration via subprocess (OAuth authentication)
- 9 SEO skills (seo-audit, content-strategy, copywriting, copy-editing, brand-voice, competitor-alternatives, programmatic-seo, schema-markup, analytics-tracking)
- CLI entry point (`main.py`)
- Configuration system (`agent/config.py`)
- README.md with full documentation
- CLAUDE.md with architecture decisions

### Features
- Uses Claude Pro subscription via OAuth (no API key required)
- Default model: Sonnet (configurable to default, sonnet, opus, haiku)
- Command line mode and interactive mode support
- Skills loaded from `Skills/` directory (symlinked to `.claude/skills`)

### Architecture
- Python-based agent using subprocess to call Claude Code CLI
- Async/await pattern for non-blocking execution
- Configuration dataclass for easy customization
