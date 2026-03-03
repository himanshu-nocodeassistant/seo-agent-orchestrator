# Changelog

All notable changes to this project will be documented in this file.

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
