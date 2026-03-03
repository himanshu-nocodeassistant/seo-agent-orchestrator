# Changelog

All notable changes to this project will be documented in this file.

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
