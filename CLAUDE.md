# SEO Bot - Autonomous Agent Project

This project contains an autonomous SEO agent built with Python using Claude Agent SDK.

## Project Overview

- **Language**: Python
- **AI Backend**: Claude Agent SDK (uses Claude Code CLI via SDK)
- **Purpose**: Autonomous SEO tasks (audit, content strategy, copywriting, etc.)

## Architecture

- `agent/seo_agent.py` - Main SEOAgent class using Claude Agent SDK
- `agent/config.py` - Configuration dataclass (AgentConfig)
- `main.py` - CLI entry point
- `Skills/` - SEO skills (.skill files are ZIP archives containing SKILL.md)
- `memory/` - Session memory (CLAUDE.md, seo-strategy.md, seo-context.md, seo-tasks.md)
- `tests/` - Test suite with pytest

## Technology Stack

- **Python**: 3.11+
- **SDK**: claude-agent-sdk>=0.1.44
- **Testing**: pytest>=9.0.0, pytest-asyncio>=1.3.0

## Memory System

The agent uses file-based memory for persistent context:

- **`memory/CLAUDE.md`** - Site overview, target keywords, content gaps, what NOT to do. Loaded at session start.
- **`memory/seo-strategy.md`** - Detailed strategy that evolves over time.
- **`memory/seo-context.md`** - Current sprint state: active tickets, completed work, pending actions.
- **`memory/seo-tasks.md`** - Generated task lists from audits with priorities and subtasks.

**Session workflow:**
1. Agent reads `memory/CLAUDE.md` for SEO context
2. Agent executes task via SDK
3. Agent updates `memory/seo-context.md` with what was done
4. Next session continues from persisted state

## Documentation Rules

Per the documentation-guide.md, always maintain:

1. **CLAUDE.md** (this file) - Architecture decisions, coding conventions, tools/stack used
2. **README.md** - Project overview, setup instructions, how to run locally
3. **CHANGELOG.md** - What changed and when (create if significant changes)
4. **Inline comments** - For non-obvious logic, especially complex queries
5. **Docstrings** - For all functions (parameters, return types, purpose)
6. **.env.example** - If environment variables are added

## Code Conventions

- All public methods should have docstrings with parameters and return types
- Use type hints where beneficial
- Async methods for SDK interactions
- Proper cleanup with context managers or disconnect()

## Available Skills

The agent has access to these SEO skills (.skill files are ZIP archives):
- **SEO Audit** - Comprehensive website SEO analysis (automatically triggers Task Breakdown)
- **Content Strategy** - Content planning and optimization
- **Copywriting** - Writing SEO-optimized content
- **Copy Editing** - Editing existing content
- **Brand Voice** - Maintaining consistent brand tone
- **Competitor Alternatives** - Finding competitor weaknesses
- **Programmatic SEO** - Automated SEO at scale
- **Schema Markup** - Adding structured data
- **Analytics Tracking** - Setting up tracking
- **Task Breakdown** - Break audit findings into actionable tasks (one-output-per-task)

## Usage

```bash
# Run a task
python3.11 main.py "Perform SEO audit on example.com"

# Interactive mode
python3.11 main.py

# Run tests
python -m pytest tests/test_seo_agent.py -v
```

## Configuration

Edit `agent/config.py` to customize:
- `model`: Claude model (default, sonnet, opus, haiku)
- `permission_mode`: Permission mode (acceptEdits, etc.)
- `allowed_tools`: Tools the agent can use (Read, Write, Edit, Bash, Glob, Grep, Skill)
- `setting_sources`: Sources for settings (user, project)

## Testing

Run the test suite:
```bash
# All tests
python -m pytest tests/test_seo_agent.py -v

# Specific test class
python -m pytest tests/test_seo_agent.py::TestMemorySystem -v

# Integration tests only
python -m pytest tests/test_seo_agent.py -m integration -v
```

## Important
- Never push, merge or commit to Github without my express approval
- Always update docs per @documentation-guide.md
- Follow red/green TDD
