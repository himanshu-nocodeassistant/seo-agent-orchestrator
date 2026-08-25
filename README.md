# SEO Agent Orchestrator

SEO Agent Orchestrator runs SEO tasks through Claude Code. It supports audits, content work, Webflow updates, Google Search Console reads, DataForSEO pulls, and campaign orchestration. A Kanban API tracks tasks, runs, approvals, and results.

## How it works

The agent uses Claude Code through OAuth. Each task maps to an **execution profile** that controls its tools, turn limit, budget, timeout, and output validator.

A four-layer memory system feeds every prompt:
- **Semantic:** site overview, keyword strategy, and ranking learnings from `memory/`
- **Episodic:** summaries of prior runs for the same task
- **Procedural:** the workflow prompt for the execution type
- **Short-term:** current run metadata, task notes, and `@agent` comments

## Features

- **Campaign orchestration:** researcher, writer, publisher, and analyst phases with dependencies, retries, handoffs, and approval before publishing
- **SEO skills:** SEO Audit, Content Strategy, Copywriting, Copy Editing, Brand Voice, Competitor Alternatives, Programmatic SEO, Schema Markup, Analytics Tracking, Page CRO, Marketing Psychology, Webflow CMS, Google Docs, SEO Feedback Loop, Task Breakdown
- **Kanban UI:** create tasks, execute them, and add `@agent` comments for revisions
- **Comment Autopilot:** claims comments, runs revisions, and sends unsafe work for review
- **Run tracing:** records run status, session ID, validator result, request ID, and tool events
- **Recovery controls:** task claims, leases, heartbeats, stale-run recovery, ownership checks, and review states
- **Session reuse:** follow-up runs can continue the same Claude session
- **Integrations:** Webflow CMS, Google Docs, Google Search Console, and DataForSEO
- **Measured ranking data:** DataForSEO provides keyword volumes, SERP positions, backlinks, and AI-search visibility for research and impact reviews
- **SEO Feedback Loop:** records CMS changes and reviews ranking data

## Reliability and recovery

The API is designed for a small self-hosted deployment with SQLite and one process:

- Execute requests atomically claim a task. A duplicate request returns the active run instead of starting another paid run.
- Every run accepts or generates an `X-Request-ID`. The ID is returned in the response and stored on run and event records.
- Runs use a 15-minute lease with heartbeats. Stale read-only work can recover; write-capable or uncertain work moves to `review_required` and does not retry automatically.
- Comment actions and campaign children use database claims and ownership checks. A stale worker cannot finish a newer run or add post-run side effects.
- DataForSEO preserves task IDs, manifests, partial results, and unknown submission outcomes. An uncertain paid POST is not sent again automatically.
- Query trace events with `GET /runs/{run_id}/events?page=1&limit=50`. The server caps `limit` at 200.

## Requirements

- Python 3.11+
- Claude Code CLI (`npm install -g @anthropic-ai/claude-code`)
- Claude Pro or Max subscription for OAuth

## Installation

```bash
git clone https://github.com/[your-username]/seo-agent-orchestrator.git
cd seo-agent-orchestrator
pip install -r requirements.txt
```

Install Claude Code CLI if you haven't already:
```bash
npm install -g @anthropic-ai/claude-code
claude  # completes OAuth on first run
```

## Setup

1. Edit `memory/CLAUDE.md` with your site URL, target keywords, content gaps, and constraints. The agent loads this file at the start of each session.

2. **Copy the env template:**
   ```bash
   cp .env.example .env
   ```

3. To use Webflow, add `WEBFLOW_ACCESS_TOKEN`, `WEBFLOW_SITE_ID`, and `WEBFLOW_COLLECTION_ID` to `.env`. Webflow tools are enabled when these are set.

4. To use Google Docs or Search Console, place the service account JSON in `google-sa-credentials/` and set `GOOGLE_DOCS_CREDENTIALS_PATH`. For Search Console, also set `GSC_SITE_URL`, then grant the service account access to the property.

## Usage

### CLI

```bash
# Single task
python main.py "Perform an SEO audit on https://yoursite.com"
python main.py "Write a blog post targeting 'internal tools for operations teams'"
python main.py "Rewrite the title tag on /service-page"

# Interactive mode
python main.py
```

### Kanban UI

```bash
uvicorn agent.api.main:app --reload --port 8000
```

Open `http://localhost:8000/kanban`. Create a task, set its execution type, and click Execute. Add `@agent` comments to trigger revisions.

### Python API

```python
import asyncio
from agent import SEOAgent, AgentConfig

async def main():
    config = AgentConfig.from_env()
    agent = SEOAgent(config)
    result = await agent.execute_task("Rewrite the title tag on /weweb-agency")
    print(result.result_text)

asyncio.run(main())
```

## Guardrails

- Publishing requires approval. `campaign_publisher` pauses until `approved_at` is set.
- Profiles set the maximum budget, turns, and timeout. Rate limits protect paid endpoints.
- Validators must pass before a run is marked complete. Research output needs cited URLs. CMS changes need a change log.
- Uncertain writes, failed write validation, stale write runs, and lost ownership move to review. They aren't retried blindly.
- CMS changes are stored with ranking data from Google Search Console when the feedback loop runs.

## Measured data, not guesses (DataForSEO)

Keyword volumes, SERP positions, backlink counts, and AI-search visibility come from **measured DataForSEO API responses**, never from the agent guessing at numbers. A batch extraction pipeline pulls the data, rollups are compiled under `dataforseo/compiled/`, and the newest results per pipeline are injected into the agent's context as a "Measured Data" section for research, campaign-research, and impact-review tasks.

- **What it powers** — keyword research grounded in real volume/CPC, SERP position tracking, competitor and backlink analysis, and AI-search (LLM mention) visibility; the SEO Feedback Loop reviews ranking impact against this measured data.
- **How it runs** — one CLI script per data source under `scripts/pipelines/` (SERP, keyword volume, backlinks, AI visibility), plus `scripts/pipelines/refresh.py` for scheduled refreshes via cron/launchd (see the script's header for a ready-made schedule line).
- **Cost is controlled and visible** — every pipeline prints the real billed cost of the run (from the API's `cost` field, not an estimate); task creation is rate-limited (`DATAFORSEO_TASKS_PER_MINUTE`) and batched (`DATAFORSEO_MAX_TASKS_PER_REQUEST`) to stay inside API quotas.

Configuration: `DATAFORSEO_LOGIN` / `DATAFORSEO_PASSWORD` (API password from the DataForSEO dashboard) plus the rate-limit env vars in the Configuration table below. Full pipeline design and reliability notes live in `agent/dataforseo/RELIABILITY.md` and `agent/dataforseo/LOG_ORGANIZATION.md`.

## Configuration

### AgentConfig

| Setting | Default | Description |
|---------|---------|-------------|
| `model` | `"sonnet"` | Claude model (`sonnet`, `opus`, `haiku`) |
| `permission_mode` | `"acceptEdits"` | Permission mode for Claude Code |
| `max_turns` | per profile | Override max turns for a run |
| `max_budget_usd` | per profile | Override cost ceiling |
| `max_thinking_tokens` | per profile | Bounded thinking budget |

### Environment Variables

Copy `.env.example` to `.env` and fill in the values you need.

| Variable | Purpose | Default |
|---------|---------|---------|
| `CLAUDE_CLI_PATH` | Override Claude CLI path (auto-detected from PATH if unset) | auto |
| `SEO_AGENT_CWD` | Working directory for the agent | repo root |
| `APP_ENV` | Kanban DB selection (`production` or `staging`) | `production` |
| `DATABASE_URL` | Explicit DB URL (overrides `APP_ENV`) | unset |
| `COMMENT_AUTOPILOT_ENABLED` | Enable `@agent` comment background worker | `true` |
| `COMMENT_AUTOPILOT_INTERVAL_SECONDS` | Poll interval for comment autopilot | `300` |
| `AGENT_EXECUTION_TIMEOUT_SECONDS` | Timeout per agent execution | `900` |
| `CAMPAIGN_TIMEOUT_SECONDS` | Maximum wall-clock time for one campaign | `5400` |
| `ALLOWED_ORIGINS` | Comma-separated CORS origins for the local API | `http://localhost:8000,http://127.0.0.1:8000` |
| `API_TOKEN` | Optional bearer token; when set every request needs `Authorization: Bearer <token>` | unset |
| `API_RATE_LIMIT_EXECUTE` | Per-minute rate limit on endpoints that start paid agent runs | `5/minute` |
| `WEBFLOW_ACCESS_TOKEN` | Webflow API token | unset |
| `WEBFLOW_SITE_ID` | Webflow site ID | unset |
| `WEBFLOW_COLLECTION_ID` | Webflow CMS collection ID | unset |
| `GOOGLE_DOCS_CREDENTIALS_PATH` | Path to Google SA credentials JSON | unset |
| `GOOGLE_APPLICATION_CREDENTIALS` | Alternative credentials path (same SA JSON) | unset |
| `GSC_SITE_URL` | GSC property (`sc-domain:example.com` or `https://www.example.com/`) | unset |
| `GSC_CREDENTIALS_PATH` | SA credentials for GSC (falls back to `GOOGLE_DOCS_CREDENTIALS_PATH`) | unset |
| `DATAFORSEO_MAX_TASKS_PER_REQUEST` | Max tasks per DataForSEO `task_post` batch | `100` |
| `DATAFORSEO_TASKS_PER_MINUTE` | Shared per-process rate limit for DataForSEO task creation | `100` |

## Execution Profiles

Each task type maps to an `ExecutionProfile` in `agent/runtime_profiles.py` that controls tools, budget, turns, and output validation.

| Profile | Max Turns | Budget | Timeout | Notes |
|---------|-----------|--------|---------|-------|
| `rewrite_title` | 10 | $1.50 | 5 min | Writes to Webflow, validates CHANGE_LOG block |
| `rewrite_meta_desc` | 10 | $1.50 | 5 min | Writes to Webflow |
| `rewrite_h1` | 10 | $1.50 | 5 min | Writes to Webflow |
| `blog_write` | 18 | $4.00 | 15 min | Full post, validates title/slug/word count |
| `rewrite_blog_content` | 18 | $4.00 | 15 min | Rewrites existing content |
| `webflow_publish` | 8 | $1.00 | 4 min | Publishes staged items |
| `internal_links` | 14 | $2.50 | 10 min | Adds internal links across pages |
| `research` | 12 | $2.00 | 8 min | Read-only + GSC; produces structured report |
| `alt_text` | 8 | $1.00 | 4 min | Read-only; produces alt text recommendations |
| `update_schema` | 10 | $1.50 | 5 min | Produces JSON-LD blocks for manual paste |
| `seo_impact_review` | 20 | $4.00 | 15 min | Feedback loop review; uses GSC for ranking deltas; no session reuse |
| `manual` | 8 | $1.00 | 4 min | Fallback for unknown types |
| `orchestrate_seo_campaign` | 6 | $1.00 | 3 min | Produces JSON plan; no session reuse |
| `campaign_researcher` | 14 | $2.50 | 10 min | Read-only + GSC |
| `campaign_draft_writer` | 18 | $4.00 | 15 min | File edits only; validates blog output |
| `campaign_publisher` | 8 | $1.50 | 5 min | Webflow publish; approval required; validates CHANGE_LOG |
| `campaign_analyst` | 16 | $3.00 | 12 min | Read-only + GSC; no session reuse |

## Memory System

The agent uses a four-layer memory model, composed by `agent/memory_service.py` before each run:

| Layer | Source | Purpose |
|---|---|---|
| **Short-term** | Current run, task, `@agent` comments | Run ID, trigger, session ID, user notes |
| **Episodic** | `AgentRunModel` DB records | Prior run summaries for the same task |
| **Semantic** | `memory/` files + `.claude/seo-learnings.md` | Site overview, strategy, learnings, context |
| **Procedural** | `ExecutionProfile` + workflow prompt | Tool policy, budget, validator, step-by-step instructions |

**To get started:** Fill out `memory/CLAUDE.md` with your site details. The agent will populate `memory/seo-context.md` and `.claude/seo-learnings.md` automatically as it runs.

## Project Structure

```
seo-agent-orchestrator/
├── agent/
│   ├── config.py             # AgentConfig; auto-detects Claude CLI from PATH
│   ├── seo_agent.py          # SEOAgent class; returns AgentExecutionResult
│   ├── memory_service.py     # Four-layer prompt composition
│   ├── runtime_profiles.py   # ExecutionProfile registry (incl. campaign profiles)
│   ├── orchestrator.py       # Multi-agent dispatch, leases, DAG, retry, recovery
│   ├── dataforseo/            # DataForSEO client, recovery manifests, and pipelines
│   ├── db.py                 # SQLAlchemy engine, models, and API schemas
│   ├── prompts.py            # Workflow prompts per execution type
│   ├── feedback_loop.py      # Change-log/learnings persistence
│   ├── api/
│   │   ├── main.py           # FastAPI app assembly (CORS, token, rate limits, lifespan)
│   │   ├── helpers.py        # Shared run/comment/autopilot helpers
│   │   ├── rate_limit.py     # slowapi limiter for cost-triggering endpoints
│   │   ├── routers/          # tasks, comments, runs, automation routers
│   │   └── static/           # kanban.html board
│   ├── webflow/              # Webflow CMS MCP integration
│   ├── google_docs/          # Google Docs MCP integration
│   └── gsc/                  # Google Search Console MCP integration (read-only)
├── memory/                   # Persistent site context (gitignored except seo-strategy.md)
│   ├── CLAUDE.md             # ← fill this in first
│   ├── seo-strategy.md       # Strategy (committed as a template)
│   ├── seo-context.md        # Auto-updated after each run
│   └── seo-tasks.md          # Auto-generated from audits
├── skills/                   # SEO skills (unpacked <name>/SKILL.md dirs)
├── .claude/
│   └── seo-learnings.md      # Auto-extracted ranking learnings
├── tests/                    # pytest test suite
├── main.py                   # CLI entry point
├── requirements.txt          # Dependencies
└── .env.example              # Environment variable reference
```

## Running Tests

```bash
pip install -r requirements.txt
python -m pytest tests/ -v

# Specific module
python -m pytest tests/test_seo_agent.py -v
```

API tests use an in-memory SQLite database. They don't write to the production database.

## Kanban API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/kanban` | Kanban board UI |
| `GET` | `/health` | Health check |
| `GET` | `/tasks` | List all tasks |
| `POST` | `/tasks` | Create task |
| `PATCH` | `/tasks/{id}` | Update task |
| `DELETE` | `/tasks/{id}` | Delete task |
| `POST` | `/tasks/{id}/execute` | Execute task via agent |
| `GET` | `/runs/{run_id}/events` | Paginated run and tool trace events |
| `GET` | `/tasks/{id}/comments` | List comments |
| `POST` | `/tasks/{id}/comments` | Add comment |
| `POST` | `/automation/comments/process-one` | Manually trigger one autopilot cycle |
| `GET` | `/orchestrations/{run_id}` | Campaign state, phase outputs, child tasks |

## Troubleshooting

**Claude CLI not found.** Install Claude Code and run `claude` once to complete OAuth:
```bash
npm install -g @anthropic-ai/claude-code
claude
```

If Claude is installed in a non-standard location, set `CLAUDE_CLI_PATH` in your `.env`.

**Google credentials.** Place the service account JSON in `google-sa-credentials/` (gitignored). The same file works for Google Docs and Search Console. Never commit credential files.

**Google Search Console access.** After adding `GSC_SITE_URL`, grant the service account read access to the property. Its email is in the JSON file under `"client_email"`.

**Webflow rate limits.** Space out bulk operations or use the `webflow_publish` profile for publish-only runs.

## Known limitations

### Campaign execution is inline

Campaigns run inside the HTTP request. A four phase campaign can keep the request open for several minutes. For more users, move orchestration to a task queue such as Celery or arq and return `202 Accepted`. `OrchestrationStateModel` already stores phase state for this change.

### SQLite limits write concurrency

SQLite supports the current single process setup. Multiple workers can contend for writes. Set `DATABASE_URL` to a PostgreSQL connection string when moving to multiple workers. The schema stays the same.

### Phase concurrency uses one process

`asyncio.gather` overlaps Claude calls on one thread. SQLite still serializes writes. The API calls are the slow part, so this is enough for the current setup.

### Handoffs have a fallback

Phases with dependents should end with a `## Summary for Next Phase` block. The orchestrator retries once when it is missing. If it is still missing, it passes a 1500 character fallback, records `handoff_degraded`, and adds a warning comment.

### Unknown SDK events are logged

Unknown SDK result types are wrapped and logged as warnings. They aren't sent to an alerting system.

### Tool scope checks are not enforced at startup

Each profile lists its allowed tools, and tests check the profiles. There is no startup assertion that blocks a read only profile from being given write access.

### Retries have no shared circuit breaker

Each phase retries its own transient failures. There is no shared stop signal when the Claude API is down.

### Feedback loop files support one writer

`seo-changes.json` uses `os.replace()`, which is safe for one writer. Multiple workers need file locking or database storage.

## License

MIT
