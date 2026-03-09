# Technical Decisions

## 2026-03-09 - Comment-driven agent autopilot for @agent feedback

### Context
Users need a way to leave revision feedback in task comments and have the agent apply that feedback automatically, even in a local server setup that may be started/stopped intermittently.

### Decision
Implement in-server comment autopilot in `agent/api/main.py`:
- Trigger only on user comments prefixed with `@agent`.
- Poll every 900 seconds by default while server is running.
- Process one eligible comment per cycle (oldest first).
- Track processing state in `comment_actions` table.
- Retry once on failure (2 attempts total), then mark retry exhausted.
- Expose manual processing endpoint: `POST /automation/comments/process-one`.

### Rationale
- Keeps the loop simple and robust for local single-process deployment.
- Prevents duplicate processing via `comment_id` uniqueness + action tracking.
- Gives operational control with environment variables and manual endpoint.
- Ensures user feedback and revised outputs remain in the task comment thread.

### Consequences
- Revisions are queued naturally while server is down and picked up on next run.
- Background loop is opt-out via `COMMENT_AUTOPILOT_ENABLED=false`.
- Long or stuck agent runs are bounded by `AGENT_EXECUTION_TIMEOUT_SECONDS`.

## 2026-03-08 - Kanban API database environment resolution

### Context
The API previously defaulted directly to `sqlite:///./kanban.db` at import time with no explicit environment model.
Tests also needed guaranteed isolation from file-backed databases.

### Decision
Use deterministic DB URL resolution in `agent/api/main.py`:
- If `DATABASE_URL` is set, use it.
- Else if `APP_ENV=staging`, use `sqlite:///./kanban.staging.db`.
- Else default to production `sqlite:///./kanban.db`.

For tests, route all API database access through a shared in-memory SQLite engine using `StaticPool` in `tests/conftest.py`.

### Rationale
- Keeps production as the safe default for runtime.
- Provides an explicit staging target without hardcoding test paths.
- Preserves flexibility for deployments via `DATABASE_URL`.
- Prevents accidental writes from tests into production/staging SQLite files.

### Consequences
- Operators can switch DB targets without code edits.
- Tests run against in-memory DBs and remain isolated from local file databases.
- Unknown `APP_ENV` values fall back to production unless `DATABASE_URL` is set.
