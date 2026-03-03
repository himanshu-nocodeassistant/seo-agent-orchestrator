# SEO Bot - Autonomous Agent Project

This project contains an autonomous SEO agent built with Python using Claude Code CLI via subprocess.

## Project Overview

- **Language**: Python
- **AI Backend**: Claude Code CLI (OAuth)
- **Purpose**: Autonomous SEO tasks (audit, content strategy, copywriting, etc.)

## Architecture

- `agent/seo_agent.py` - Main SEOAgent class using subprocess to call Claude CLI
- `agent/config.py` - Configuration dataclass
- `main.py` - CLI entry point
- `Skills/` - 9 SEO skills (symlinked to `.claude/skills`)
- `memory/` - Session memory (CLAUDE.md, seo-strategy.md, seo-context.md)

## Memory System

The agent uses file-based memory for persistent context:

- **`memory/CLAUDE.md`** - Site overview, target keywords, content gaps, what NOT to do. Loaded at session start.
- **`memory/seo-strategy.md`** - Detailed strategy that evolves over time.
- **`memory/seo-context.md`** - Current sprint state: active tickets, completed work, pending actions.

**Session workflow:**
1. Agent reads `memory/CLAUDE.md` for SEO context
2. Agent executes task
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

## Available Skills

The agent has access to these SEO skills:
- SEO Audit
- Content Strategy
- Copywriting
- Copy Editing
- Brand Voice
- Competitor Alternatives
- Programmatic SEO
- Schema Markup
- Analytics Tracking

## Usage

```bash
# Run a task
python3.11 main.py "Perform SEO audit on example.com"

# Interactive mode
python3.11 main.py
```

## Configuration

Edit `agent/config.py` to customize:
- `model`: Claude model (default, sonnet, opus, haiku)
- `permission_mode`: Permission mode
- `allowed_tools`: Tools the agent can use

## Important
- Never push, merge or commit to Github without my express approval