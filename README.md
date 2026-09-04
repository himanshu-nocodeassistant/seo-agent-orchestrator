# SEO Agent Orchestrator

*Turn SEO from a manual, hard-to-measure process into a repeatable system that compounds organic growth.*

**SEO Agent Orchestrator is an open-source SEO operations platform** — an autonomous operator for your site that audits, optimizes, writes, publishes, and — most importantly — **measures whether the changes actually moved rankings**. Built on Python + the Claude Agent SDK and driven through a visual Kanban board, with a human approval gate before anything goes live.

## Why it exists — the business case

- **SEO is measurable but rarely measured.** The agent closes the loop: every CMS change is logged, its ranking impact reviewed against Search Console, and the winning patterns fed back into the next task.
- **Content work doesn't scale manually.** A researcher → writer → publisher → analyst campaign pipeline turns one campaign request into a coordinated set of specialized tasks that run automatically.
- **Guardrails protect the business.** Cost ceilings per task, tool permissions per task type, output validators, rate limits, and a human approval step before publishing — automation without losing control.
- **Decisions come from data, not guesses.** Measured keyword volumes, SERP positions, and backlink data are injected into the agent's context so recommendations are grounded in real numbers.

## What it delivers

| Business outcome | How it's delivered |
|---|---|
| Faster page-level optimization | One task rewrites titles, meta descriptions, H1s, alt text, schema — with Webflow publish when configured |
| Consistent content production | Blog posts and rewrites follow brand voice, SEO workflow, and validator checks |
| Rank changes you can attribute | Every CMS change is change-logged and reviewed against GSC clicks/impressions/position |
| Learning that compounds | SEO Feedback Loop extracts learnings from measured outcomes and propagates what works |
| Team leverage | Comment Autopilot picks up "@agent" revision requests and re-runs automatically |
| Cost control | Per-task budget ceilings, per-minute rate limits, real cost tracking on data pulls |

## Open source, self-hosted, no lock-in

SEO Agent Orchestrator is released under the [MIT License](LICENSE). It runs entirely on your own infrastructure against your existing Claude Code subscription — your ranking data, CMS, and credentials never leave your control. As an open-source project, the entire pipeline is inspectable and extensible: agent logic, SEO skills, data integrations, and the API are all yours to read, fork, and extend. No black box, no per-seat pricing, no vendor lock-in.

## How it works

The agent runs on your existing Claude Code subscription (OAuth — no API key). Each task maps to an **execution profile** that controls which tools the agent can use, how many turns it gets, its cost ceiling, and a structured validator that checks the output before a run is marked complete.

A four-layer memory system feeds every prompt:
- **Semantic** — your site overview, keyword strategy, and extracted ranking learnings from `memory/`
- **Episodic** — summaries of prior runs for the same task, pulled from the database
- **Procedural** — the workflow prompt for the execution type (rewrite title, write blog post, etc.)
- **Short-term** — current run metadata, task notes, and `@agent` comments from the Kanban board

## Features

- **Multi-agent campaign orchestration** — one campaign task (researcher → writer → publisher → analyst) with DAG-based parallelism, structured handoffs, retry on transient failures, and an approval gate before publishing
- **15 SEO Skills** — SEO Audit, Content Strategy, Copywriting, Copy Editing, Brand Voice, Competitor Alternatives, Programmatic SEO, Schema Markup, Analytics Tracking, Page CRO, Marketing Psychology, Webflow CMS, Google Docs, SEO Feedback Loop, Task Breakdown
- **Kanban UI** — visual task board at `http://localhost:8000/kanban`; create tasks, execute them, leave `@agent` comments for revisions
- **Comment Autopilot** — background worker that picks up `@agent` comments and re-runs the agent automatically
- **Run tracking** — every execution is recorded with status, session ID, validator result, and a result summary; child campaign runs link back to the orchestrator run via `parent_run_id`
- **Session reuse** — the agent resumes the same Claude session for follow-up runs on a task, preserving context
- **Webflow CMS** — agents read CMS items and propose changes; the API applies create, update, and publish actions after approval
- **Google Docs** — save audit reports and blog drafts to Google Docs (read/write only — no delete)
- **Google Search Console** — query live clicks, impressions, CTR, and position; inspect URL indexing status; list sitemaps (read-only)
- **SEO Feedback Loop** — log CMS changes, review ranking impact using GSC data, extract learnings, propagate winning patterns

## Requirements

- Python 3.11+
- Claude Code CLI (`npm install -g @anthropic-ai/claude-code`)
- Claude Pro or Max subscription (for OAuth — no API key needed)

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

1. **Fill in your site context** — edit `memory/CLAUDE.md` with your site URL, target keywords, content gaps, and what NOT to do. This is loaded at the start of every agent session.

2. **Copy the env template:**
   ```bash
   cp .env.example .env
   ```

3. **(Optional) Webflow** — add `WEBFLOW_ACCESS_TOKEN`, `WEBFLOW_SITE_ID`, `WEBFLOW_COLLECTION_ID` to `.env`. Agents receive read access automatically. Webflow writes require an approved proposal.

4. **(Optional) Google Docs / Search Console** — place your Google Service Account JSON in `google-sa-credentials/` (gitignored), then set `GOOGLE_DOCS_CREDENTIALS_PATH` in `.env`. For Search Console, also set `GSC_SITE_URL` (e.g. `sc-domain:example.com`). The same service account covers both — just grant it access to your GSC property in Search Console → Settings → Users and permissions.

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

## Business guardrails by default

- **Human approval before publishing** — campaigns first require parent approval, then show the exact Webflow proposal for approval. The campaign resumes from where it stopped (no re-planning, no double-billing).
- **Spend is bounded** — every execution profile has a max budget and turn limit, API rate limits cap cost-triggering endpoints, and DataForSEO pulls track real billed cost per run.
- **Nothing ships unverified** — outputs must pass a structured validator (grounded research requires cited URLs; CMS changes require a machine-readable change log) before a run is marked complete.
- **Published changes are attributable** — the SEO Feedback Loop correlates CMS changes with GSC ranking data so you can see what actually worked.

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
| `COMMENT_AUTOPILOT_INTERVAL_SECONDS` | Poll interval for comment autopilot | `900` |
| `AGENT_EXECUTION_TIMEOUT_SECONDS` | Timeout per agent execution | `900` |
| `ALLOWED_ORIGINS` | Comma-separated CORS origins for the local API | `http://localhost:8000,http://127.0.0.1:8000` |
| `API_TOKEN` | Bearer token; required for approval routes unless `APP_ENV` is explicitly `local`, `development`, or `test`. When set, every request needs `Authorization: Bearer <token>` | unset |
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
| `rewrite_title` | 10 | $1.50 | 5 min | Proposes a Webflow update; validates CHANGE_LOG block |
| `rewrite_meta_desc` | 10 | $1.50 | 5 min | Proposes a Webflow update |
| `rewrite_h1` | 10 | $1.50 | 5 min | Proposes a Webflow update |
| `blog_write` | 18 | $4.00 | 15 min | Proposes a CMS item; validates title/slug/word count |
| `rewrite_blog_content` | 18 | $4.00 | 15 min | Proposes a content update |
| `webflow_publish` | 8 | $1.00 | 4 min | Proposes publishing a staged item |
| `internal_links` | 14 | $2.50 | 10 min | Proposes batch updates across pages |
| `research` | 12 | $2.00 | 8 min | Read-only + GSC; produces structured report |
| `alt_text` | 8 | $1.00 | 4 min | Read-only; produces alt text recommendations |
| `update_schema` | 10 | $1.50 | 5 min | Produces JSON-LD blocks for manual paste |
| `seo_impact_review` | 20 | $4.00 | 15 min | Feedback loop review; uses GSC for ranking deltas; no session reuse |
| `manual` | 8 | $1.00 | 4 min | Fallback for unknown types |
| `orchestrate_seo_campaign` | 6 | $1.00 | 3 min | Produces JSON plan; no session reuse |
| `campaign_researcher` | 14 | $2.50 | 10 min | Read-only + GSC |
| `campaign_draft_writer` | 18 | $4.00 | 15 min | File edits only; validates blog output |
| `campaign_publisher` | 8 | $1.50 | 5 min | Read-only Webflow access; returns a publish proposal |
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
│   ├── orchestrator.py       # Multi-agent dispatch loop; DAG resolution; retry
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
│   │   ├── approvals.py      # Proposal state and snapshot rules
│   │   ├── proposal_parser.py# Extracts complete proposals from agent output
│   │   └── text_safety.py    # Fences notes and preserves full text
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

API tests use an in-memory SQLite database automatically — no production DB is touched.

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
| `GET` | `/tasks/{id}/comments` | List comments |
| `POST` | `/tasks/{id}/comments` | Add comment |
| `POST` | `/automation/comments/process-one` | Manually trigger one autopilot cycle |
| `GET` | `/orchestrations/{run_id}` | Campaign state, phase outputs, child tasks |
| `GET` | `/tasks/{id}/webflow-proposals` | List complete Webflow proposals |
| `POST` | `/tasks/{id}/webflow-proposals` | Create a pending proposal; never writes to Webflow |
| `POST` | `/tasks/{id}/webflow-proposals/{proposal_id}/approve` | Re-check and apply one proposal |
| `POST` | `/tasks/{id}/webflow-proposals/{proposal_id}/reject` | Reject one proposal |

## Webflow approval flow

Webflow write profiles are proposal-only:

```text
Agent reads Webflow
      ↓
Agent returns the full proposal
      ↓
API stores pending_approval
      ↓
User approves or rejects in Kanban
      ↓
API re-reads Webflow and checks the saved snapshot
      ↓
API applies the exact payload, once
```

The SDK receives a per-profile tool allowlist. Webflow write tools are absent from
agent profiles. The write functions also reject calls without approved proposal
context. Prompts are guidance only; the allowlist and server checks enforce the rule.

For campaigns, `campaign_publisher` is a child profile, not a separate agent class.
The orchestrator pauses after it stores the child's Webflow proposal. Approve that
proposal, then resume the parent campaign.

## Troubleshooting

**Claude CLI not found** — install Claude Code and run `claude` once to complete OAuth:
```bash
npm install -g @anthropic-ai/claude-code
claude
```

If Claude is installed in a non-standard location, set `CLAUDE_CLI_PATH` in your `.env`.

**Google credentials** — place your service account JSON in `google-sa-credentials/` (gitignored). The same file works for Google Docs and Search Console. Never commit credential files.

**Google Search Console access** — after adding `GSC_SITE_URL`, grant your service account read access to the property in Search Console → Settings → Users and permissions. The SA email is inside the JSON file under `"client_email"`.

**Webflow rate limits** — the Webflow API has rate limits. Space out bulk operations or use the `webflow_publish` profile for publish-only runs.

## Known Limitations (Production Scaling)

This is a single-user tool. I made deliberate calls to keep it simple — none of these are oversights, and none require a rewrite to fix. Here's what I skipped and why.

**1. Campaigns run inside the HTTP request, not a background worker.**
The whole orchestration runs inline — if a 4-phase campaign takes 10 minutes, the request is open for 10 minutes. Fine for one user. If you're scaling this up, the fix is a task queue (Celery or arq) and a `202 Accepted` response that the client polls. I actually designed `OrchestrationStateModel` with exactly this in mind — it tracks state phase by phase, so a queue worker can pick up where it left off if it crashes.

**2. SQLite doesn't handle concurrent writes.**
Two workers writing at the same time will fight. I used SQLite because there are no ops concerns — nothing to provision, nothing to back up. To go multi-worker, just set `DATABASE_URL` to a Postgres connection string. The schema doesn't change at all.

**3. "Parallel" phases aren't truly parallel — they're concurrent.**
`asyncio.gather` runs them on the same thread, and SQLite only allows one writer at a time anyway. But the actual bottleneck is the Claude API call, which takes seconds to minutes. The DB write takes microseconds. So the parallelism still delivers real time savings. With Postgres and async SQLAlchemy each phase gets its own connection and you get the full benefit.

**4. If an agent skips the summary block, the next agent gets raw truncated output.**
Phases with downstream dependents must end with a `## Summary for Next Phase` block. If it's missing, the orchestrator retries once with a correction prompt asking for the block (only for phases that have dependents, so final phases cost nothing extra). If it's still missing, the campaign continues with the 1500-char truncation fallback, but records `handoff_degraded` in the orchestration state and posts a warning comment on the task — the pipeline now knows the handoff was degraded.

**5. Unknown SDK result types get logged but not alerted.**
If the SDK ships a new event type we don't handle, we log a warning and wrap it gracefully — nothing crashes. But in production that warning would be invisible. Wire the logger to Sentry or Datadog if you care about SDK contract changes.

**6. Tool scopes use two runtime checks.**
Each run receives the allowlist from its execution profile through the Claude SDK.
Webflow mutation functions also require approved proposal context. Tests protect the
profile definitions. A future change can add a startup assertion for profile tiers.

**7. Retry has no circuit breaker.**
If Claude's API goes down completely, each phase retries independently — you get 3 attempts per phase but no shared "stop trying" signal across phases. For one campaign at a time this is fine. At scale you'd want a circuit breaker so once you've confirmed the API is down, everything fails fast instead of hammering it.

**8. The feedback loop JSON files aren't safe under concurrent writes.**
`seo-changes.json` is written atomically using `os.replace()`, which is safe for one writer. Two workers writing simultaneously could corrupt it. Single worker, so not a problem here. The comment in the source marks exactly where you'd add `fcntl.flock()` — or just move the state into the database.

## License

MIT
