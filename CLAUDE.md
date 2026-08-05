# SEO Bot - Autonomous Agent Project

## Business Context

This project exists to make SEO a measurable, compounding growth channel instead
of a manual, guess-driven process. Success looks like:

- **Attributable rank changes** — every CMS change is logged and reviewed
  against Google Search Console data, so we know what actually moved rankings.
- **Repeatable content production** — audits and keyword research turn into
  coordinated campaigns (researcher → writer → publisher → analyst) that run
  with consistent quality and brand voice.
- **Controlled spend** — per-task budgets, rate limits, real DataForSEO cost
  tracking, and a human approval gate before anything publishes.
- **Decisions from measured data** — keyword volumes, SERP positions, and
  backlink data come from measured sources, never guessed by the agent.

Technical guidance for achieving these outcomes follows; keep business impact
in mind when choosing between "expedient" and "correct".

## ProjectLanguage: Python
- **AI Backend**: Claude Agent SDK (uses Claude Code CLI via SDK)
- **Purpose**: Autonomous SEO tasks (audit, content strategy, copywriting, etc.)

## Architecture

- `agent/seo_agent.py` - Main SEOAgent class using Claude Agent SDK; returns `AgentExecutionResult`
- `agent/config.py` - Configuration dataclass (AgentConfig); exports `PROJECT_ROOT`; supports `SEO_AGENT_CWD` env var and `max_thinking_tokens`
- `agent/memory_service.py` - Layered memory composition: builds `ShortTermContext`, `EpisodicContext`, `SemanticContext`, `ProceduralContext` into a `ComposedPromptContext` for prompt injection
- `agent/runtime_profiles.py` - `ExecutionProfile` registry; maps each execution type to tool policy, budget, timeout, turn limit, validator, semantic char limits, and `requires_approval` flag
- `agent/orchestrator.py` - Multi-agent campaign dispatch loop; DAG tier resolution (`_resolve_execution_tiers`), structured inter-agent handoffs (`_extract_summary_block`), retry with backoff (`_run_with_retry`), parallel execution via `asyncio.gather`
- `agent/db.py` - SQLAlchemy engine, session factory, ORM models, and Pydantic API schemas (WAL + busy_timeout enabled for SQLite)
- `agent/prompts.py` - Workflow prompts per execution type (`build_execution_prompt`)
- `agent/feedback_loop.py` - Change-log/learnings persistence (`seo-changes.json`, `seo-learnings.json`, markdown views)
- `main.py` - CLI entry point; uses `PROJECT_ROOT` for portable working directory
- `agent/api/main.py` - FastAPI app assembly: CORS (`ALLOWED_ORIGINS`), optional bearer-token gate (`API_TOKEN`), slowapi rate limits, lifespan (autopilot + DB migrations)
- `agent/api/helpers.py` - Shared run/comment/autopilot helpers (formerly in main.py)
- `agent/api/routers/` - `tasks.py`, `comments.py`, `runs.py`, `automation.py` endpoint routers
- `agent/api/rate_limit.py` - Shared slowapi `limiter` for cost-triggering endpoints
- `agent/api/static/kanban.html` - Kanban board UI (served as a static file)
- `skills/` - SEO skills as canonical unpacked `<name>/SKILL.md` directories (no `.skill` ZIP archives)
- `memory/` - Session memory (CLAUDE.md, seo-strategy.md, seo-context.md, seo-tasks.md)
- `tests/` - Test suite with pytest

## Multi-Agent Orchestration

Trigger: create a Kanban task with `execution_type = "orchestrate_seo_campaign"` and click Execute.

**Flow:**
1. Orchestrator agent reads `memory/` files and outputs a `{"campaign_goal": ..., "phases": [...]}` JSON plan
2. Python (`agent/orchestrator.py`) parses the plan and resolves execution tiers via Kahn's topological sort
3. Child `TaskModel` rows are created (one per phase, with `parent_task_id` set)
4. Tiers execute sequentially; phases within a tier run concurrently via `asyncio.gather`
   - Each phase runs on its **own DB session** (closed in `finally`), so concurrent phases never share/interleave a SQLAlchemy session
5. **Approval gate**: before dispatching any phase whose `ExecutionProfile.requires_approval=True`, the orchestrator checks `parent_task.approved_at`. If unset, sets `state.status='awaiting_approval'` and halts. Campaign resumes when `approved_at` is set via `PATCH /tasks/{id}`.
   - **Resume is explicit**: `POST /tasks/{id}/execute?resume=true` (or the Resume button in the UI) continues the SAME orchestrator run — the plan is not regenerated and completed phases are not re-run.
6. Each phase agent receives prior outputs via structured `## Summary for Next Phase` blocks (falls back to 1500-char truncation)
   - Phases with downstream dependents get ONE correction retry when the block is missing; if still missing, `handoff_degraded` is recorded in the orchestration state (`handoff_degraded_json`) plus a warning comment
7. `OrchestrationStateModel` persists state: plan JSON, current phase, all phase outputs, child run IDs, and final status (`running | awaiting_approval | completed | error`)
8. All child `AgentRunModel` rows carry `parent_run_id` pointing to the orchestrator run

**Phase plan schema** (what the orchestrator agent must output):
```json
{
  "campaign_goal": "string",
  "phases": [
    {
      "phase": "researcher",
      "task_title": "Research: <specific angle>",
      "task_description": "...",
      "execution_type": "campaign_researcher",
      "depends_on": []
    },
    { "phase": "draft_writer", "execution_type": "campaign_draft_writer", "depends_on": ["researcher"], ... },
    { "phase": "publisher", "execution_type": "campaign_publisher", "depends_on": ["draft_writer"], ... }
  ]
}
```

**Inter-agent handoff protocol:** Each child agent must end its output with:
```
## Summary for Next Phase
<concise handoff notes for the next agent>
## End Summary
```

**Retry policy:** transient errors (timeouts, 503s, rate limits) are retried up to 2 times with exponential backoff with an optional `max_total_seconds` wall-clock cap. Non-retryable: budget exceeded, malformed plan, circular dependency.

**Plan validation:** every phase's `execution_type` is validated against the profile registry right after parsing — a bad plan fails fast with a clear error before any child task is created.

**Approval gate:** `campaign_publisher` has `requires_approval=True`. The orchestrator halts before that tier and sets `state.status='awaiting_approval'`. Set `approved_at` on the parent task via the Kanban UI (PATCH) to resume.

**Grounding requirement:** `research` and `campaign_researcher` profiles carry the `grounding-required` procedural tag. The injected system prompt requires every factual claim to cite a source URL; the validator also checks for at least one `https://` URL in the output.

**Audit log:** every tool call made during a run is written to `RunEventModel` via a `PostToolUse` SDK hook wired in `_build_runtime_config`.

**Scalability boundaries** (annotated in source with `# Scalability note`):
- `#1` — move `run_campaign_orchestration` call to a task queue (Celery/arq) for production; return 202 + polling
- `#2` — swap SQLite for Postgres via `DATABASE_URL`; schema is unchanged
- `#6` — child agent tool scopes are enforced in `runtime_profiles.py`; never expand via `EXECUTABLE_TYPES`
- `#8` — `_atomic_json_write` uses `os.replace()` (POSIX-atomic); add `fcntl.flock()` for multi-worker

## Technology Stack

- **Python**: 3.11+
- **SDK**: claude-agent-sdk>=0.1.44
- **HTTP Client**: aiohttp>=3.9.0 (for Webflow API); requests>=2.31.0 (for DataForSEO pipeline)
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
1. Agent reads `memory/CLAUDE.md`, `memory/seo-strategy.md`, and `memory/seo-context.md` for SEO context
2. `memory_service` composes a layered prompt context (short-term, episodic, semantic, procedural)
3. `runtime_profiles` selects the `ExecutionProfile` for the execution type (tools, budget, turns, validator)
4. Agent executes the task via SDK; result stored in `AgentRunModel`
5. Next session can resume via session ID and draws from `EpisodicContext` (prior run summaries)

**Orchestration workflow** (when `execution_type = "orchestrate_seo_campaign"`):
1. Orchestrator agent produces JSON plan → stored in `OrchestrationStateModel.plan_json`
2. `_resolve_execution_tiers` builds DAG tiers from `depends_on` fields
3. Each tier dispatches concurrently; outputs accumulate in `OrchestrationStateModel.phase_outputs_json`
4. Child runs record `parent_run_id`; child tasks record `parent_task_id`

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
- `allowed_tools`: Tools the agent can use (Read, Write, Edit, Glob, Grep, Skill, WebSearch, WebFetch — Bash excluded by default)
- `hooks`: Optional SDK hook dict (e.g. `PostToolUse` audit log); set by `_build_runtime_config` automatically
- `setting_sources`: Sources for settings (user, project)

## Available Tools

### Default Tools
The agent has these tools available by default (Bash intentionally excluded — runtime profiles stamp the exact allowed list):
- Read, Write, Edit, Glob, Grep - File operations
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
GOOGLE_DOCS_CREDENTIALS_PATH=google-sa-credentials/service-account.json
# OR use the standard Google application credentials path:
GOOGLE_APPLICATION_CREDENTIALS=google-sa-credentials/service-account.json
```

### Programmatic Configuration
```python
from agent import AgentConfig, GoogleDocsConfig

config = AgentConfig(
    google_docs_config=GoogleDocsConfig(
        credentials_path="google-sa-credentials/service-account.json"
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

## Google Search Console Integration

The agent can query live Search Console data: clicks, impressions, CTR, position,
URL indexing status, and sitemaps. Read-only — no write operations are exposed.

Uses the same Google Service Account as Google Docs. Grant the SA access to your
GSC property in Search Console → Settings → Users and permissions.

### Environment Variables
```bash
GSC_SITE_URL=sc-domain:example.com          # domain property
# OR
GSC_SITE_URL=https://www.example.com/       # URL-prefix property

# Credentials (falls back to GOOGLE_DOCS_CREDENTIALS_PATH / GOOGLE_APPLICATION_CREDENTIALS):
GSC_CREDENTIALS_PATH=google-sa-credentials/service-account.json
```

### Programmatic Configuration
```python
from agent import AgentConfig, GscConfig

config = AgentConfig(
    gsc_config=GscConfig(
        site_url="sc-domain:example.com",
        credentials_path="google-sa-credentials/service-account.json"
    )
)
```

### Available Tools
**Automatically available when `GSC_SITE_URL` is set.** Added to `allowed_tools`:

- `mcp__gsc__gsc_query_search_analytics` - Query clicks/impressions/CTR/position by query, page, device, or date
- `mcp__gsc__gsc_inspect_url` - Get indexing status for a specific URL
- `mcp__gsc__gsc_list_sitemaps` - List sitemaps submitted to GSC

### Which Profiles Get GSC Access

| Execution type | GSC tools | Reason |
|---|---|---|
| `seo_impact_review` | ✅ | Compares ranking before/after CMS changes |
| `research` | ✅ | Pulls live query data during keyword and competitor research |
| all others | ❌ | Publish/rewrite profiles don't need ranking data at write time |

### Module Structure
```
agent/gsc/
├── __init__.py    # Exports
├── config.py      # GscConfig dataclass
├── client.py      # GscAPIClient (read-only)
├── tools.py       # @tool decorated functions
└── server.py      # MCP server factory
```

## DataForSEO Integration

Unlike GSC/Webflow/Google Docs, DataForSEO is **not** wired into the agent as live
MCP tools. It's a batch extraction pipeline: standalone scripts call
`agent/dataforseo/` classes to pull SERP rankings, keyword volume, backlinks, and
AI-search-visibility data, log every paid API call to disk, and compile the
results into files the agent reads via `memory/`. This exists so keyword
volumes, SERP positions, and ranking data come from measured DataForSEO
responses instead of the agent guessing at them.

`agent/dataforseo/__init__.py` is deliberately **not** re-exported from
`agent/__init__.py` — importing the agent must not require `requests`/`python-dotenv`.

### Environment Variables
```bash
DATAFORSEO_LOGIN=your_login_email
DATAFORSEO_PASSWORD=your_api_password   # API password from the DataForSEO dashboard, not your account password
SEO_TARGET_DOMAIN=yoursite.com          # optional — flags your own domain's rows in recovery/report output
```

### Storage Layout
```
dataforseo/
├── raw/        # one file per API call, grouped tag/keyword-slug/location_code/ (gitignored contents)
├── manifests/  # {task_id: request} written immediately on task_post, so a crash never loses billed task IDs (gitignored contents)
└── compiled/   # rolled-up JSON/CSV output — what scripts and the agent actually read (tracked in git)
```
See `agent/dataforseo/LOG_ORGANIZATION.md` for why `raw/` is grouped this way, and
`agent/dataforseo/RELIABILITY.md` for the retry/manifest/recovery design.

### Module Structure
```
agent/dataforseo/
├── client.py                    # DataForSEOClient — sync requests, retry+backoff, task_post/task_get polling, manifest writes
├── logger.py                    # log_result() — writes every call to dataforseo/raw/
├── serp/google_organic.py       # SERP rankings
├── keywords_data/               # google_ads.py, bing.py, google_trends.py — keyword volume/CPC/trends
├── dataforseo_labs/google.py    # keyword ideas, ranked keywords, competitor domains
├── backlinks/backlinks.py       # backlink data
└── ai_optimization/             # LLM mentions/visibility (ChatGPT, Claude, Gemini, Perplexity) + AI keyword data
```

### Utility Scripts
```
scripts/compile_serp_results.py    # dataforseo/raw/ -> one compiled JSON, deduped to latest per keyword+location
scripts/serp_recover_from_ids.py   # recover results from a manifest/task_post log without re-billing tasks
scripts/purge_stale_poll_logs.py   # delete not-ready poll snapshots superseded by a completed task_get
scripts/pipelines/refresh.py       # scheduled SERP + keyword-volume refresh (reads dataforseo/refresh.tasks.json)
```
These operate on already-fetched local files (or resume an in-flight
task_post) — they don't pull fresh data from the API themselves.

### Refreshing Measurements on a Schedule

`scripts/pipelines/refresh.py` reads `dataforseo/refresh.tasks.json` (a `serp`
keyword list and a `keyword_volume` list with locations/tags), runs the
standard-queue `search` / `search_volume` batches, and writes rollups to
`dataforseo/compiled/` with the naming the measurement memory layer reads.
Run it from cron/launchd, e.g. daily at 2am:

```
0 2 * * * cd /path/to/seo-bot-orchestrator && .venv/bin/python scripts/pipelines/refresh.py >> dataforseo/refresh.log 2>&1
```

The agent consumes the compiled rollups through the measurement memory layer:
`agent/dataforseo/memory.py` picks the newest compiled file per pipeline and
`fetch_semantic_context` injects a `## Measured Data (DataForSEO)` section for
profiles tagged `dataforseo-measurements` (`research`, `campaign_researcher`,
`campaign_analyst`, `seo_impact_review`) — so keyword volumes/SERP positions
come from measured responses, not guesses.

**Client hardening:** `DataForSEOClient` chunks `task_post` payloads into
`DATAFORSEO_MAX_TASKS_PER_REQUEST` (default 100) batches, polls all pending
tasks per round with a global `max_wait` deadline, uses full-jitter backoff
honoring `Retry-After`, writes manifests atomically, and rate-limits task
creation via a shared token bucket (`DATAFORSEO_TASKS_PER_MINUTE`, default
100). Never run pipeline scripts without explicit user permission — every
`task_post` bills real API spend.

**Not ported:** the ~30 one-off campaign report scripts (e.g. white-label
keyword volume, bubble-migration keyword suggestions) that lived in the source
project's `scripts/` — those encode a specific client's already-extracted
keyword intelligence, not reusable pipeline logic. Write new campaign-specific
scripts against `agent/dataforseo/` as needed; keep them out of `CLAUDE.md`
unless they become reusable infrastructure.

### API Pipelines (fresh data pulls)

`scripts/pipelines/` has one CLI script per `agent/dataforseo` class — these are
what actually calls the API to pull new data. Every script is a ~25-line wrapper
around the shared harness in `scripts/pipelines/_cli.py`, which introspects the
class's public methods and exposes each as a subcommand:

```
python scripts/pipelines/<name>.py <method> --task '{"...": "..."}'          # single ad-hoc task
python scripts/pipelines/<name>.py <method> --tasks-file tasks.json          # batch, from a JSON list
python scripts/pipelines/<name>.py <method> --help                           # per-method arg/field docs
```

Output writes to `dataforseo/compiled/<pipeline>-<method>-<date>.json` by default
(override with `--output`). The 14 scripts:

```
scripts/pipelines/serp_google_organic.py         # GoogleOrganicSERP
scripts/pipelines/keywords_google_ads.py         # GoogleAdsKeywords
scripts/pipelines/keywords_bing.py                # BingKeywords
scripts/pipelines/keywords_google_trends.py      # GoogleTrends
scripts/pipelines/labs_google.py                  # GoogleLabs (keyword ideas, ranked keywords, competitors)
scripts/pipelines/backlinks.py                    # BacklinksAPI
scripts/pipelines/llm_mentions.py                 # LLMMentions (AI Overviews / ChatGPT mention search)
scripts/pipelines/ai_keyword_data.py              # AIKeywordData (AI-assistant search volume)
scripts/pipelines/llm_responses_chat_gpt.py       # ChatGPTResponses
scripts/pipelines/llm_responses_claude.py         # ClaudeResponses
scripts/pipelines/llm_responses_gemini.py         # GeminiResponses
scripts/pipelines/llm_responses_perplexity.py     # PerplexityResponses (no task_post — API doesn't support it)
scripts/pipelines/llm_scraper_chat_gpt.py         # ChatGPTScraper
scripts/pipelines/llm_scraper_gemini.py           # GeminiScraper
```

**Cost tracking:** `DataForSEOClient.total_cost` accumulates the real `cost`
field from every response (`agent/dataforseo/client.py`) — not a hardcoded
per-endpoint estimate. Every pipeline run prints `DataForSEO API cost this run: $X.XXXX`
at the end. For the four `llm_responses_*` pipelines specifically, each result
item also carries real `input_tokens`/`output_tokens`/`money_spent` (genuine LLM
token usage, distinct from the DataForSEO call cost); those are summed and
printed as `LLM token usage: ... input / ... output tokens, $X.XXXX money_spent`
whenever present. Cost is captured even on a call that ultimately errors —
billed spend is real regardless of whether the call succeeded.

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

API hardening environment variables:
- `ALLOWED_ORIGINS` (comma-separated CORS origins; default localhost:8000)
- `API_TOKEN` (optional bearer token; when set every request needs `Authorization: Bearer <token>`)
- `API_RATE_LIMIT_EXECUTE` (per-minute slowapi limit on execute/process-one; default `5/minute`)
- `SEO_AGENT_CWD` (agent working directory; defaults to repo root)
- `CLAUDE_CLI_PATH` (Claude CLI override; auto-detected from PATH if unset)

Testing isolation:
- `tests/conftest.py` forces API tests to use in-memory SQLite with `StaticPool` (patching `agent.db` engine/session) so tests never write into production/staging DB files, and raises the rate limit so the shared TestClient key never trips it.

### Module Structure
```
agent/api/
├── __init__.py    # Module init
├── main.py        # FastAPI app assembly + backwards-compat re-exports
├── helpers.py     # Shared run/comment/autopilot helpers
├── rate_limit.py  # slowapi limiter
├── routers/       # tasks.py, comments.py, runs.py, automation.py
└── static/
    └── kanban.html
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
