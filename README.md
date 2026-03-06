# SEO Autonomous Agent

An autonomous agent that performs SEO tasks using Claude Code via OAuth authentication.

## Overview

This project provides an autonomous SEO agent built with Python that leverages Claude Code's AI capabilities to perform various SEO-related tasks. The agent uses your Claude Pro subscription via OAuth - no API key required.

## Features

- **Claude OAuth** - Uses your Claude Pro subscription (no API key needed)
- **10 SEO Skills** - Built-in skills for:
  - SEO Audit
  - Content Strategy
  - Copywriting
  - Copy Editing
  - Brand Voice
  - Competitor Alternatives
  - Programmatic SEO
  - Schema Markup
  - Analytics Tracking
  - Google Docs (save reports & content)
- **Google Docs Integration** - Automatically saves audit reports and blog posts to Google Docs
- **Webflow CMS** - Publish content directly to Webflow

## Requirements

- Python 3.11+ (or Python 3.9+ with system Python)
- Claude Code CLI installed
- Claude Pro subscription (for OAuth)

## Installation

1. **Install Claude Code CLI** (if not already installed):
   ```bash
   npm install -g @anthropic-ai/claude-code
   ```

2. **Verify Claude Code works**:
   ```bash
   claude --help
   ```

3. **Run the agent**:
   ```bash
   python3.11 main.py "Your SEO task here"
   ```

   Or use the system Python:
   ```bash
   python3 main.py "Your SEO task here"
   ```

## Usage

### Command Line Mode

Run a single task:
```bash
python3.11 main.py "Perform an SEO audit on example.com"
python3.11 main.py "What SEO skills are available?"
python3.11 main.py "Create a content strategy for a tech blog"
```

### Interactive Mode

Start an interactive session:
```bash
python3.11 main.py
```

Commands:
- `exit` or `quit` - Exit the program
- `interrupt` or `stop` - Stop the current task

## Configuration

Edit `agent/config.py` to customize:

| Setting | Default | Description |
|---------|---------|-------------|
| `model` | `"sonnet"` | Claude model (default, sonnet, opus, haiku) |
| `permission_mode` | `"acceptEdits"` | Permission mode for Claude |
| `allowed_tools` | See config | Tools the agent can use |

## Project Structure

```
seo-bot/
├── agent/
│   ├── __init__.py       # Package initialization
│   ├── config.py         # Agent configuration
│   └── seo_agent.py      # Main SEOAgent class
├── memory/               # Session memory (persistent context)
│   ├── CLAUDE.md         # Site overview, keywords, gaps
│   ├── seo-strategy.md    # Detailed strategy (evolves)
│   └── seo-context.md    # Sprint state, tickets
├── Skills/               # SEO skills (symlinked to .claude/skills)
├── .claude/
│   ├── CLAUDE.md -> ../memory/CLAUDE.md  # Symlink for auto-loading
│   └── skills -> ../Skills  # Symlink for Skills
├── main.py               # CLI entry point
├── requirements.txt       # Dependencies
└── README.md            # This file
```

## Memory System

The agent uses file-based memory for persistent context across sessions:

1. **`memory/CLAUDE.md`** - Site overview, target keywords, content gaps, what NOT to do
2. **`memory/seo-strategy.md`** - Detailed strategy that evolves over time
3. **`memory/seo-context.md`** - Current sprint state: active tickets, completed work

**Session workflow:**
1. Agent reads `memory/CLAUDE.md` for SEO context
2. Agent executes the task
3. Agent updates `memory/seo-context.md` with what was done
4. Next session continues from persisted state

**To get started:** Fill out `memory/CLAUDE.md` with your site details.

## Available Skills

The agent has access to these SEO skills:

1. **SEO Audit** - Audit a site's SEO health
2. **Content Strategy** - Plan and structure content
3. **Copywriting** - Write SEO-optimized copy
4. **Copy Editing** - Edit and refine existing copy
5. **Brand Voice** - Define and apply brand voice guidelines
6. **Competitor Alternatives** - Analyze competitors and positioning
7. **Programmatic SEO** - Scale SEO with programmatic approaches
8. **Schema Markup** - Implement structured data
9. **Analytics Tracking** - Set up and interpret analytics

## API Usage Examples

### Basic Task Execution

```python
import asyncio
from agent import SEOAgent, AgentConfig

async def main():
    config = AgentConfig()
    agent = SEOAgent(config)
    
    result = await agent.execute_task("Perform SEO audit on example.com")
    print(result)

asyncio.run(main())
```

### Interactive Session

```python
import asyncio
from agent import SEOAgent, AgentConfig

async def main():
    config = AgentConfig()
    
    async with SEOAgent(config) as agent:
        while True:
            user_input = input("You: ")
            if user_input.lower() in ["exit", "quit"]:
                break
            
            response = await agent.chat(user_input)
            print(f"Claude: {response}")

asyncio.run(main())
```

## Troubleshooting

### Claude CLI not found
If you see "Claude CLI not found", install Claude Code:
```bash
npm install -g @anthropic-ai/claude-code
```

### Permission errors
Ensure Claude Code has the necessary permissions in your Claude settings.

### Rate limiting
If you encounter rate limits, wait a moment and try again.

## License

MIT
