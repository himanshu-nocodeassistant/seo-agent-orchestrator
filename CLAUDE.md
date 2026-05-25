# SEO Bot - Autonomous Agent Project

This project contains an autonomous SEO agent built with Python using Claude Agent Overview

- ** SDK.

## ProjectLanguage**: Python
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
- **HTTP Client**: aiohttp>=3.9.0 (for Webflow API)
- **Web Server**: FastAPI, Uvicorn (for Kanban UI)
- **Database**: SQLite with SQLAlchemy ORM
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
7. **DECISIONS.md** - Record important technical decisions and rationale

## Code Conventions

- All public methods should have docstrings with parameters and return types
- Use type hints where beneficial
- Async methods for SDK interactions
- Proper cleanup with context managers or disconnect()

## Available Skills

The agent has access to these SEO skills (.skill files are ZIP archives containing SKILL.md + references):
- **SEO Audit** - Comprehensive website SEO analysis (automatically triggers Task Breakdown)
- **Content Strategy** - Content planning and optimization
- **Copywriting** - Writing SEO-optimized content
- **Copy Editing** - Editing existing content (includes plain-english-alternatives reference)
- **Brand Voice** - Maintaining consistent brand tone
- **Competitor Alternatives** - Finding competitor weaknesses
- **Programmatic SEO** - Automated SEO at scale (includes playbooks reference)
- **Schema Markup** - Adding structured data (includes JSON-LD examples reference)
- **Analytics Tracking** - Setting up tracking (includes GA4, GTM, event library references)
- **Task Breakdown** - Break audit findings into actionable tasks (one-output-per-task)
- **Page CRO** - Conversion rate optimization for marketing pages (includes experiments reference)
- **Marketing Psychology** - Apply psychological principles and behavioral science to marketing
- **Webflow CMS** - Manage Webflow CMS content (create, edit, publish posts)
- **Google Docs** - Create and manage Google Docs for reports and content
- **SEO Feedback Loop** - Track impact of implemented SEO changes, diagnose regressions, extract learnings, propagate winning patterns (includes sample log, sample learnings, sample review report, and templates). Use `execution_type: seo_impact_review` in Kanban to trigger a batch review of all pending changes.

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

## Available Tools

### Default Tools
The agent has these tools available by default:
- Read, Write, Edit, Bash, Glob, Grep - File operations
- Skill - Execute SEO skills
- WebSearch, WebFetch - Web browsing

### Webflow CMS Tools
**Automatically available when environment variables are set.** When `WEBFLOW_ACCESS_TOKEN`, `WEBFLOW_SITE_ID`, and `WEBFLOW_COLLECTION_ID` are configured, these tools are automatically added to `allowed_tools`:

- `mcp__webflow__list_cms_items` - List items in collection (supports limit/offset pagination)
- `mcp__webflow__get_cms_item` - Get single item by ID
- `mcp__webflow__create_cms_item` - Create new post (name, slug, content)
- `mcp__webflow__update_cms_item` - Update existing post
- `mcp__webflow__publish_cms_item` - Publish to live site
- `mcp__webflow__get_collection_info` - Get collection schema

The agent can use these tools to manage Webflow CMS content when Webflow is configured.

## Webflow CMS Integration

The agent can manage Webflow CMS collections (create, edit, publish posts). Uses Webflow Data API v2.

### Environment Variables
```bash
WEBFLOW_ACCESS_TOKEN=your_api_token
WEBFLOW_SITE_ID=your_site_id
WEBFLOW_COLLECTION_ID=your_collection_id
```

### Programmatic Configuration
```python
from agent import AgentConfig, WebflowConfig

config = AgentConfig(
    webflow_config=WebflowConfig(
        access_token="your_token",
        site_id="your_site_id", 
        collection_id="your_collection_id"
    )
)
```

### API Details
- **Base URL**: `https://api.webflow.com/v2`
- **Pagination**: Uses limit/offset (max 100 items per request)
- **Live Items**: Uses `/items/live` endpoint to fetch published items

### Module Structure
```
agent/webflow/
├── __init__.py    # Exports
├── config.py      # WebflowConfig dataclass
├── client.py     # WebflowAPIClient (raw API)
├── tools.py      # @tool decorated functions
└── server.py     # MCP server factory
```

### Pagination Example
To get more than 100 items, loop with incremental offsets:
```python
offset = 0
while True:
    result = await client.list_items(limit=100, offset=offset)
    items = result.get('items', [])
    if not items:
        break
    # process items
    offset += 100
```

## Google Docs Integration

The agent can create and manage Google Docs for SEO audit reports, blog content, and other documents.

### Environment Variables
```bash
GOOGLE_DOCS_CREDENTIALS_PATH=Google SA Credentials/tinyclaw-487419-d5ab318833bb.json
# OR use the standard Google application credentials path:
GOOGLE_APPLICATION_CREDENTIALS=Google SA Credentials/tinyclaw-487419-d5ab318833bb.json
```

### Programmatic Configuration
```python
from agent import AgentConfig, GoogleDocsConfig

config = AgentConfig(
    google_docs_config=GoogleDocsConfig(
        credentials_path="Google SA Credentials/tinyclaw-487419-d5ab318833bb.json"
    )
)
```

### Available Tools
**Automatically available when credentials path is set.** The following tools are added to `allowed_tools`:

- `mcp__google_docs__create_google_doc` - Create a new Google Doc
- `mcp__google_docs__get_google_doc` - Get document by ID
- `mcp__google_docs__append_to_google_doc` - Append content to document
- `mcp__google_docs__update_google_doc_title` - Update document title

### Security - No Delete Capability
**IMPORTANT:** By design, Google Docs cannot be deleted through this integration. The agent can only:
- ✅ Create new documents
- ✅ Read documents
- ✅ Append content to documents
- ✅ Update document titles
- ❌ Delete documents (intentionally disabled)

This ensures audit reports and blog content are preserved and cannot be accidentally removed.

### Module Structure
```
agent/google_docs/
├── __init__.py    # Exports
├── config.py      # GoogleDocsConfig dataclass
├── client.py      # GoogleDocsAPIClient
├── tools.py       # @tool decorated functions
└── server.py      # MCP server factory
```

## Kanban UI

The project includes a visual Kanban board for task management.

### Running the Server

```bash
# Start the Kanban server
uvicorn agent.api.main:app --reload --port 8000
```

Then open http://localhost:8000/kanban

### API Endpoints

- `GET /kanban` - Serve Kanban HTML UI
- `GET /health` - Health check
- `GET /tasks` - List all tasks with counts
- `POST /tasks` - Create new task
- `GET /tasks/{id}` - Get task by ID
- `PATCH /tasks/{id}` - Update task
- `DELETE /tasks/{id}` - Delete task
- `POST /tasks/{id}/execute` - Execute task via SEOAgent
- `GET /tasks/{id}/comments` - Get task comments
- `POST /tasks/{id}/comments` - Add comment
- `POST /automation/comments/process-one` - Process one eligible `@agent` comment action
- `POST /runs/{run_id}/seo-audit` - Run SEO audit

### Task Statuses

- `pending` - Tasks waiting to be worked on
- `in_progress` - Tasks currently being executed
- `completed` - Tasks finished successfully
- `blocked` - Tasks that encountered errors

### Database

Uses SQLite with SQLAlchemy ORM. The database is created automatically on first run.

Environment-based defaults for Kanban API:
- `APP_ENV=production` (default) -> `sqlite:///./kanban.db`
- `APP_ENV=staging` -> `sqlite:///./kanban.staging.db`
- `DATABASE_URL` (if set) overrides `APP_ENV`

Comment revision automation:
- `comment_actions` table tracks comment-triggered execution attempts and status.
- Trigger format: user comment body must begin with `@agent`.
- Background worker runs only while server is running.
- Autopilot skips `@agent` comments if the task was already executed after the comment was posted (`task.updated_at > comment.created_at`).

User comments in task execution:
- When a task is executed via the Execute button, all user comments on that task are included in the agent prompt under a `## User Notes` section.
- This means notes like "keep the tone casual" or "focus on mobile users" are automatically factored in — no `@agent` prefix needed.

Comment automation environment variables:
- `COMMENT_AUTOPILOT_ENABLED` (default `true`)
- `COMMENT_AUTOPILOT_INTERVAL_SECONDS` (default `300` — 5 minutes)
- `AGENT_EXECUTION_TIMEOUT_SECONDS` (default `900`)

Testing isolation:
- `tests/conftest.py` forces API tests to use in-memory SQLite with `StaticPool` so tests never write into production/staging DB files.

### Module Structure
```
agent/api/
├── __init__.py    # Module init
└── main.py        # FastAPI app with all endpoints and embedded Kanban HTML
```

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
