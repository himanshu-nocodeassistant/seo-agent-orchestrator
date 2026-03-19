# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- Explicit Kanban API DB environment resolution in `agent/api/main.py`:
  - `APP_ENV=production` -> `sqlite:///./kanban.db`
  - `APP_ENV=staging` -> `sqlite:///./kanban.staging.db`
  - `DATABASE_URL` override takes precedence over `APP_ENV`
- Comment-driven autopilot execution for task revisions:
  - Trigger: user comments starting with `@agent`
  - Tracking table: `comment_actions` with attempts/status (`pending`, `running`, `succeeded`, `failed`, `retry_exhausted`)
  - Internal background poller (default every 300s) processes one comment per cycle
  - Manual admin endpoint: `POST /automation/comments/process-one`
- Shared agent execution timeout control: `AGENT_EXECUTION_TIMEOUT_SECONDS` (default 900)
- Red/green TDD coverage for DB URL selection:
  - `tests/test_db_env_config.py` (5 tests)
- Red/green TDD coverage for comment autopilot:
  - `tests/test_comment_autopilot.py` (11 tests)
- User comments included in task execution prompts:
  - All user-authored comments on a task are appended as `## User Notes` in the agent prompt when the Execute button is used
  - `build_execution_prompt` accepts an optional `comments` parameter; `_append_user_notes` helper handles the formatting
  - No `@agent` prefix needed — plain notes like "keep it casual" are automatically factored in
- Autopilot stale-comment skip:
  - `@agent` comments are skipped if the task was already executed after the comment was posted (`task.updated_at > comment.created_at`)
  - Prevents duplicate re-execution when user clicks Execute after leaving an `@agent` comment
- Reduced default autopilot polling interval from 900s (15 min) to 300s (5 min)
- Red/green TDD for all new behaviours:
  - `tests/test_execution_prompts.py` (6 new tests for comment injection)
  - `tests/test_comment_autopilot.py` (5 new tests for stale-skip and interval)
- Test DB isolation fixture:
  - `tests/conftest.py` now uses in-memory SQLite with `StaticPool` to prevent test writes to file-backed DBs
- Added `.env.example` documenting runtime environment variables
- Added `DECISIONS.md` with database environment design decision

### Verification
- `pytest tests/test_db_env_config.py -v` -> 5 passed
- `pytest tests/test_kanban_api.py -q` -> 26 passed
- `pytest tests/test_comment_autopilot.py tests/test_db_env_config.py tests/test_kanban_api.py -q` -> 37 passed

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
