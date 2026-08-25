# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- **Reliability and tracing hardening** — atomic task claims, request correlation through `X-Request-ID`, paginated run events, run leases, heartbeats, stale-run recovery, and ownership fencing for runs, campaigns, and comment actions.
- **Safe campaign recovery** — resumable phase state, durable child-run claims, approval gates, and review-required states for uncertain or write-capable failures.
- **DataForSEO recovery records** — collision-safe manifests preserve submitted IDs, partial results, and uncertain POST outcomes; the CLI reports recovery details instead of retrying paid work blindly.

### Changed
- **Validation and health reporting** — strict task and comment validation, bounded list and audit inputs, server-controlled comment authors, and dependency-aware `/health` output.
- **Comment Autopilot** — leased claims, heartbeats, stale-action recovery, request IDs, and review gates prevent duplicate or unsafe comment-triggered runs.

## [2.3.0] - 2026-08-05

### Added
- **Green, non-hanging test suite** — `pytest.ini` registers the `integration` marker and excludes it by default (`addopts = -m "not integration"`); stale mocks now patch `SEOAgent.create_and_run_result` (the method the app actually calls); Google Docs tests use a fake service-account fixture; GitHub Actions CI runs `pytest tests/` on Python 3.11
- **API hardening** — CORS restricted to `ALLOWED_ORIGINS` (no more `*` + credentials), optional `API_TOKEN` bearer gate, slowapi rate limits (`API_RATE_LIMIT_EXECUTE`, default `5/minute`) on `POST /tasks/{id}/execute` and `POST /automation/comments/process-one`
- **SQLite WAL + busy_timeout** — long agent runs no longer lock the DB against concurrent API requests or campaign phases
- **Fixed `/runs/{run_id}/seo-audit`** — runs through the standard profile pipeline with a new read-only `seo_audit` profile (research validator); removed the Bash/localhost task-creation step
- **Client retries** — Webflow client retries 429/502/503/504 with jittered backoff honoring `Retry-After`; GSC/Google Docs `discovery.build` uses `num_retries=3`; SDK `MessageParseError` now surfaces in the run's error instead of silently returning empty results
- **Portability** — `SEO_AGENT_CWD` is now functional; Claude CLI auto-detected from PATH (`CLAUDE_CLI_PATH` override); removed the hardcoded `cwd` pointing at a different repo
- **Approval-gate resume** — `POST /tasks/{id}/execute?resume=true` (and a Resume button in the UI) continues a paused campaign on the same orchestrator run without regenerating the plan or re-running completed phases
- **Handoff validation** — phases with dependents get one correction retry when the `## Summary for Next Phase` block is missing; persistent misses are recorded in `OrchestrationStateModel.handoff_degraded_json` with a warning comment
- **Per-phase DB session isolation** — concurrent tier phases no longer share/interleave a SQLAlchemy session
- **Fail-fast plan validation** — every phase `execution_type` is checked against the profile registry before child tasks are created
- **DataForSEO client hardening** — `task_post` chunking (≤`DATAFORSEO_MAX_TASKS_PER_REQUEST`), parallel round polling with a global deadline (was N×max_wait), full-jitter backoff, atomic manifests with microsecond timestamps, and a shared token-bucket rate limiter (`DATAFORSEO_TASKS_PER_MINUTE`)
- **Measurement memory layer** — `agent/dataforseo/memory.py` renders the newest compiled rollup per pipeline into a `## Measured Data (DataForSEO)` prompt section for profiles tagged `dataforseo-measurements` (`research`, `campaign_researcher`, `campaign_analyst`, `seo_impact_review`)
- **Refresh scheduler** — `scripts/pipelines/refresh.py` + `dataforseo/refresh.tasks.json` for scheduled SERP/keyword-volume refreshes (cron/launchd)
- **Codebase organization** — `agent/api/main.py` split into `agent/db.py` (models/session/schemas), `agent/prompts.py`, `agent/feedback_loop.py`, `agent/api/helpers.py`, `agent/api/rate_limit.py`, `agent/api/routers/`, and `agent/api/static/kanban.html`; skills canonicalized to flat `<name>/SKILL.md` dirs (`.skill` ZIPs removed, `.claude/skills` symlink now repo-relative); `PLAN.md` and stale `References/` docs removed

### Changed
- Deprecations fixed while restructuring: FastAPI lifespan handlers, SQLAlchemy 2.0 `orm.declarative_base`, Pydantic `model_dump`, `datetime.now(timezone.utc)` helpers
- `seo_audit` is now an executable profile (previously a nonexistent type referenced by the broken audit endpoint and UI)
- `main.py` CLI uses `SEO_AGENT_CWD`/repo root instead of a hardcoded path
- README/CLAUDE.md reframed business-first (open-source platform positioning, what it delivers and why, guardrails, measurable outcomes) with all technical detail preserved below
- README gained a dedicated "Measured data, not guesses (DataForSEO)" section covering what it powers, how it runs, and cost control

### Added
- **DataForSEO batch extraction pipeline** (`agent/dataforseo/`) — ported from the sibling `seo-bot` project as a standalone sync pipeline, not agent-facing MCP tools. Replaces guessed keyword volumes/SERP data with measured DataForSEO API responses.
  - `client.py` — `DataForSEOClient`: retry+backoff on 429/502/503/504, Standard Queue task_post/task_get polling, crash-safe manifest writes before polling begins
  - `logger.py` — logs every paid API call to `dataforseo/raw/<tag>/<keyword-slug>/<location_code>/`, grouped for lookup by keyword rather than by endpoint
  - Coverage: SERP (Google organic), Keywords Data (Google Ads, Bing, Google Trends), DataForSEO Labs (Google), Backlinks, AI Optimization (LLM mentions/visibility across ChatGPT/Claude/Gemini/Perplexity, AI keyword data)
  - Not ported: YouTube SERP endpoints, Amazon/App Store Labs — out of scope for this project's SEO focus
  - `scripts/compile_serp_results.py`, `scripts/serp_recover_from_ids.py`, `scripts/purge_stale_poll_logs.py` — campaign-agnostic pipeline utilities; `TARGET_DOMAIN` hardcoding from the source replaced with `--target-domain`/`SEO_TARGET_DOMAIN`
  - `dataforseo/{raw,manifests,compiled}/` created empty — no keyword intelligence carried over from the source project
  - `tests/test_dataforseo_logger.py` — 9 tests on the log-grouping logic, ported verbatim (fully isolated via `tmp_path`)
  - New deps: `requests>=2.31.0`, `python-dotenv>=1.0.0`
- **`DataForSEOClient.total_cost` real-cost tracking** — accumulates the `cost` field from every API response (`_post`/`_get`), captured even on calls that ultimately raise `DataForSEOError` so billed spend is never dropped just because a call errored. Per-instance, not global. `tests/test_dataforseo_client.py` — 7 tests, all HTTP mocked.
- **14 per-class API pipeline scripts** (`scripts/pipelines/`) — one CLI script per `agent/dataforseo` class (SERP, Google Ads/Bing/Trends keywords, Labs, Backlinks, LLM Mentions, AI Keyword Data, 4x LLM Responses, 2x LLM Scraper), the first mechanism in this repo that actually pulls fresh DataForSEO data (the 3 utility scripts above only operate on already-fetched files). Every script delegates to a shared harness (`scripts/pipelines/_cli.py`) that introspects the class's public methods and exposes each as a subcommand (`--task '<json>'` or `--tasks-file`), rather than 14 hand-written near-duplicates. Prints `total_cost` after every run; for the 4 `llm_responses_*` pipelines, also sums and prints real per-item `input_tokens`/`output_tokens`/`money_spent` (genuine LLM token spend, distinct from the DataForSEO call cost). `tests/test_pipeline_cli.py` — 15 tests against a fake client class covering every method-shape the harness dispatches.
- **`SEO_TARGET_DOMAIN`** env var (`.env.example`) — the one domain-flagging parameter used across the pipeline (currently `scripts/serp_recover_from_ids.py --target-domain`); documented in one place so future scripts needing domain matching reuse the same name instead of inventing a new one.

## [2.2.0] - 2026-06-10

### Added
- **`campaign_draft_writer` execution profile** — write-only (EDIT tools, no Webflow publish); replaces the monolithic `campaign_content_writer` that could write files and publish in a single unguarded step
- **`requires_approval` flag on `ExecutionProfile`** — when `True`, the orchestrator tier loop pauses before that phase and sets `OrchestrationStateModel.status = 'awaiting_approval'`; the campaign resumes only when `parent_task.approved_at` is set. Set on `campaign_publisher` by default.
- **`grounding-required` procedural tag** — `research` and `campaign_researcher` profiles carry this tag; `ComposedPromptContext.to_prompt()` emits a cite-sources rule that requires every factual claim to be backed by a retrieved URL
- **`build_post_tool_use_hook(db, run_id)`** in `agent/api/main.py` — returns a `PostToolUse` hook that writes a `RunEventModel` row for every tool call the agent makes; wired into `_build_runtime_config` when `db`/`run_id` are provided
- **`SEOAgent.create_and_run_result`** classmethod — runs a prompt via the SDK and returns an object with `.result_text` and `.session_id`; used by `_run_agent_prompt` so hooks and config go through one code path
- **`AgentConfig.hooks`** field — passes SDK hook dict through to `ClaudeAgentOptions.hooks`
- **18 new tests** in `tests/test_safety_hardening.py` (10 pre-existing + 8 new): `TestContentWriterSplit` (6), `TestGroundingInstruction` (4), `TestApprovalGate` (4), `TestPostToolUseHook` (5)

### Changed
- `campaign_content_writer` profile **removed** — replaced by `campaign_draft_writer` (file edits) + `campaign_publisher` (Webflow publish, requires approval). Any orchestrator plan using `campaign_content_writer` must be updated to `campaign_draft_writer`.
- `campaign_publisher` now has `requires_approval=True` — will halt every campaign before publish unless the parent task has `approved_at` set
- `_build_prompt_with_context` accepts an optional `prompt_context` argument — when provided, skips file-based memory load (context is already embedded in the prompt string by the caller)

### Security
- `campaign_publisher` can no longer write or edit files — `Write`/`Edit` tools removed from its allowed set; it can only read and publish to Webflow CMS
- Validator failures now halt the entire campaign pipeline (raised in `_dispatch_phase`) — a phase producing malformed output cannot pass context forward to downstream phases

## [2.1.0] - 2026-06-08

### Added
- **Multi-agent campaign orchestration** — new `execution_type = "orchestrate_seo_campaign"` triggers a full multi-agent pipeline from a single Kanban task
  - `agent/orchestrator.py` — Python-managed dispatch loop: orchestrator agent produces a JSON plan; Python creates child tasks and runs each phase agent, threading outputs as context
  - `OrchestrationStateModel` — new DB table tracking plan JSON, current phase, per-phase outputs, child run IDs, and campaign status (`planning → running → completed | error`)
  - `parent_run_id` column on `AgentRunModel` — links every child run back to the orchestrator run for full audit trail
  - `GET /orchestrations/{orchestrator_run_id}` — endpoint returning campaign state and all child task details
- **DAG-based parallel phase execution** (`_resolve_execution_tiers`) — Kahn's topological sort groups phases into tiers; phases with no unmet dependencies run concurrently via `asyncio.gather`. Circular dependency and unknown dependency references raise `ValueError` before any agents run. Fail-fast: one failure in a tier cancels remaining tiers.
- **Structured inter-agent handoffs** (`_extract_summary_block`) — agents write a `## Summary for Next Phase ... ## End Summary` block; the next agent receives this clean summary instead of a raw truncated output dump. Falls back to 1500-char truncation when no summary block is present.
- **Retry with exponential backoff** (`_run_with_retry`) — transient failures (timeouts, 503s, rate limits) are retried up to `max_retries` times with doubling delay. Non-retryable errors (budget exceeded, malformed plan, circular dependency) raise immediately without retry.
- **SDK result hardening** (`_normalize_execution_result`) — handles `None`, plain strings, known SDK types, and unknown types gracefully; unknown types log a `WARNING` with full payload rather than crashing.
- **5 new execution profiles** in `agent/runtime_profiles.py`:
  - `orchestrate_seo_campaign` — BASE tools, 6 turns, $1.00, validates JSON plan structure
  - `campaign_researcher` — BASE + GSC (read-only), 14 turns, $2.50
  - `campaign_content_writer` — EDIT + WEBFLOW, 18 turns, $4.00, validates blog output + CHANGE_LOG
  - `campaign_publisher` — BASE + WEBFLOW, 8 turns, $1.50, validates CHANGE_LOG
  - `campaign_analyst` — BASE + GSC (read-only), 16 turns, $3.00, no session resume
- **Scalability annotations** — inline comments at every production-scaling boundary: task queue migration point (#1), Postgres swap (#2), tool scope enforcement (#6), file locking (#8)
- **17 new tests** in `tests/test_orchestration.py` covering: structured summary extraction, summary fallback to truncation, DAG tier resolution (serial/parallel/circular/unknown-dep), parallel happy path, parallel fail-fast, retry (transient/non-retryable/exhausted/ValueError), SDK hardening (known/string/unknown/None)

### Changed
- `_build_child_prompt_with_prior_outputs` now injects structured summaries from prior agents when available, with a reminder to each agent to write the `## Summary for Next Phase` block at the end of its output
- `_normalize_execution_result` extended to handle `None` and unknown SDK result types with a logged warning instead of a silent crash

### Known limitations (not implemented in this version)
- Campaign execution blocks the FastAPI worker — no task queue (Celery/arq). See Known Limitations in README.
- SQLite only — no multi-worker write concurrency. Switch via `DATABASE_URL`.
- Summary block not yet enforced by validator — agents that omit it fall back to truncation silently.
- No circuit breaker on retry — a fully-down downstream gets retried without backoff ceiling.
- File-based feedback loop state (`seo-changes.json`) uses `os.replace()`, not safe under concurrent workers.

## [2.0.0] - 2026-06-08

### Added
- **Google Search Console integration** (`agent/gsc/`) — read-only MCP module following the same pattern as `agent/webflow/` and `agent/google_docs/`
  - `GscConfig` — reads `GSC_SITE_URL` from env; credential lookup falls back from `GSC_CREDENTIALS_PATH` → `GOOGLE_DOCS_CREDENTIALS_PATH` → `GOOGLE_APPLICATION_CREDENTIALS`; the same Google SA JSON used for Google Docs works here
  - `GscAPIClient` — three read-only methods: `query_search_analytics` (clicks/impressions/CTR/position with date range + dimension filters), `inspect_url` (indexing status), `list_sitemaps`
  - Three MCP tools auto-registered when `GSC_SITE_URL` is set: `mcp__gsc__gsc_query_search_analytics`, `mcp__gsc__gsc_inspect_url`, `mcp__gsc__gsc_list_sitemaps`
  - `AgentConfig._setup_gsc_mcp()` and `AgentConfig.from_env()` updated — GSC is auto-configured when `GSC_SITE_URL` is present; no code changes required
- **GSC tools wired into two execution profiles** in `agent/runtime_profiles.py`:
  - `seo_impact_review` — uses GSC as primary ranking signal source (before/after click and position deltas per page); falls back to WebSearch if GSC unavailable
  - `research` — can pull live query and page data during keyword and competitor research
- **`_gsc_available()` / `_gsc_degradation_note()`** helpers in `agent/api/main.py` — `seo_impact_review` prompt injects a fallback note when GSC is not configured
- **`seo_impact_review` Phase 3 updated** — agent now queries GSC by page with a before/after date split; falls through to WebSearch only when GSC returns an error or is unconfigured
- 16 new tests in `tests/test_gsc_client.py` covering config, client (mocked API), runtime profile wiring, and `AgentConfig` integration

### Fixed
- `.env` path for Google SA credentials corrected from stale `Google SA Credentials/` (old uppercase directory) to `google-sa-credentials/` (renamed in previous cleanup)
- `GSC_SITE_URL` in `.env` was URL-encoded (`sc-domain%3A…`) — corrected to plain `sc-domain:…`

## [1.9.0] - 2026-04-09

### Added
- **Execution type now editable on existing tasks** — the task detail modal includes an "Execution Type" dropdown, allowing users to change a task's type after creation. Change is saved via the existing `PATCH /tasks/{id}` endpoint and the Execute button updates accordingly.
- **Mandatory brand voice check before all content-writing executions** — `build_execution_prompt` now injects a hard-coded first step for all execution types except `manual` and `webflow_publish`: the agent must invoke the `brand-voice` skill and internalize its guidelines before producing any copy. Applies to: `rewrite_title`, `rewrite_meta_desc`, `rewrite_h1`, `blog_write`, `rewrite_blog_content`, `internal_links`, `research`, `alt_text`, `update_schema`, `seo_impact_review`.

## [1.8.0] - 2026-03-19

### Added
- **SEO Feedback Loop** — deterministic application-layer change logging and impact review system
  - `CMS_CHANGE_FIELD_MAP` — single registry mapping 7 CMS execution types to change-type labels; all feedback-loop logic derives from this
  - `_parse_change_log_block()` — extracts structured `<!-- CHANGE_LOG {...} -->` block from agent output; returns `failure_reason` in `{missing_block, invalid_json, missing_required_fields, field_mismatch}`
  - `_write_change_log_entry()` — upserts idempotent entries to `memory/seo-changes.json`; always writes even on failed extraction (never silent loss)
  - `_build_change_id()` — deterministic key `"{task_id}-{execution_type}-{url_slug}"` for deduplication and retry safety
  - `_atomic_json_write()` — all JSON writes via temp file + `os.replace()` for write safety
  - `_render_changes_markdown()` / `_render_learnings_markdown()` — JSON → readable markdown views
  - `_refresh_markdown_views()` — regenerates `.claude/seo-changes-log.md` and `.claude/seo-learnings.md` after every JSON write
  - `_change_log_block_instruction()` — per-type structured output contract appended to agent prompts for 7 CMS branches
  - `seo_impact_review` execution type — 6-phase review prompt: backfill unlogged tasks → batch pending entries → evaluate each (WebSearch/WebFetch) → extract learnings → refresh views → post summary comment
  - `seo-feedback-loop.skill` — packaged with 5 reference files (3 samples + 2 templates) following the `.skill` ZIP convention
- `execute_task` now deterministically calls `_write_change_log_entry` after every CMS task — agent cannot skip logging; failures surface as task comment, never crash the task
- `VALID_REVIEW_STATUSES` set enforces formal status lifecycle: `pending-review → reviewed-positive | reviewed-negative | reviewed-neutral | reviewed-inconclusive`
- `seo_impact_review` added to `EXECUTABLE_TYPES` and to the Task Breakdown skill mapping in `run_seo_audit`
- `memory/CLAUDE.md` — agent now instructed to read `.claude/seo-learnings.md` before writing any SEO copy (site-specific learned patterns take precedence over generic best practices)
- `memory/seo-changes.json` and `memory/seo-learnings.json` — structured JSON sources of truth (created on first task completion)

### Tests
- 32 new tests in `tests/test_seo_feedback_loop.py` covering all new functions and integration paths (TDD: red → green)
- All 14 pre-existing failures in `test_seo_agent.py` confirmed pre-existing; zero regressions introduced

## [1.7.0] - 2026-03-19

### Added
- 5 new skills with structured references:
  - **Page CRO** (`page-cro.skill`) — conversion rate optimization for marketing pages; includes `references/experiments.md`
  - **Marketing Psychology** (`marketing-psychology.skill`) — behavioral science and persuasion frameworks for marketing
  - **Analytics Tracking** (`analytics-tracking.skill`) — GA4, GTM, and event tracking; includes 3 reference files (event-library, ga4-implementation, gtm-implementation)
  - **Programmatic SEO** (`programmatic-seo.skill`) — template-driven SEO at scale; includes `references/playbooks.md`
  - **Schema Markup** (`schema-markup.skill`) — updated with `references/schema-examples.md` (complete JSON-LD examples)
- Updated **Copy Editing** skill (`copy-editing.skill`) now includes `references/plain-english-alternatives.md`
- All new skills follow the structured format: `SKILL.md` + `references/` + `evals/evals.json`

### Changed
- CLAUDE.md updated to document all available skills including references bundled in each `.skill` ZIP

## [1.6.0] - 2026-03-19

### Added
- User comments now included in task execution prompts:
  - All user-authored comments on a task are appended as `## User Notes` when the Execute button is used
  - `build_execution_prompt` accepts an optional `comments` parameter; `_append_user_notes` helper handles formatting
  - No `@agent` prefix needed — plain notes like "keep it casual" are automatically factored in
- Autopilot stale-comment skip:
  - `@agent` comments are skipped if the task was already executed after the comment was posted (`task.updated_at > comment.created_at`)
  - Prevents duplicate re-execution when user clicks Execute after leaving an `@agent` comment

### Changed
- Reduced default autopilot polling interval from 900s (15 min) to 300s (5 min)

### Tests
- 6 new tests in `tests/test_execution_prompts.py` for comment injection
- 5 new tests in `tests/test_comment_autopilot.py` for stale-skip and interval (45 total passing)

## [1.5.0] - 2026-03-05

### Added
- Explicit Kanban API DB environment resolution in `agent/api/main.py`:
  - `APP_ENV=production` -> `sqlite:///./kanban.db`
  - `APP_ENV=staging` -> `sqlite:///./kanban.staging.db`
  - `DATABASE_URL` override takes precedence over `APP_ENV`
- Comment-driven autopilot execution for task revisions:
  - Trigger: user comments starting with `@agent`
  - Tracking table: `comment_actions` with attempts/status (`pending`, `running`, `succeeded`, `failed`, `retry_exhausted`)
  - Internal background poller processes one comment per cycle
  - Manual admin endpoint: `POST /automation/comments/process-one`
- Shared agent execution timeout control: `AGENT_EXECUTION_TIMEOUT_SECONDS` (default 900)
- Test DB isolation fixture: `tests/conftest.py` uses in-memory SQLite with `StaticPool`
- Added `.env.example` documenting runtime environment variables
- Added `DECISIONS.md` with database environment design decision

### Tests
- `tests/test_db_env_config.py` (5 tests)
- `tests/test_comment_autopilot.py` (6 tests)

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
- Skills loaded from `skills/` directory (symlinked to `.claude/skills`)

### Architecture
- Python-based agent using subprocess to call Claude Code CLI
- Async/await pattern for non-blocking execution
- Configuration dataclass for easy customization
