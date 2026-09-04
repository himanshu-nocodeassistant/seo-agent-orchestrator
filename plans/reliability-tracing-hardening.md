# Plan: Reliability, Tracing, and Hardening

> Source PRD: Reliability, Tracing, and Hardening for the SEO Agent Orchestrator

## Architectural decisions

- **Deployment**: Optimise for small self-hosted deployments with SQLite and one process. Keep behaviour safe if more than one request reaches the service at the same time.
- **Execution API**: Keep the current synchronous execution flow. A duplicate execute request returns the existing active run.
- **Routes**: Keep existing task, run, automation, and health routes. Add `GET /runs/{run_id}/events?page=<n>&limit=<n>` for paginated event access.
- **Authentication**: Use the existing bearer token boundary. Do not add per-user identity or permissions in this work.
- **Run models**: Continue to use `TaskModel`, `AgentRunModel`, `RunEventModel`, and `CommentActionModel`. Add only fields needed for request correlation, heartbeats, leases, and recovery state.
- **Tracing**: Store events in the database. Accept or generate `X-Request-ID`, return it in the response, and link it to the run and event records.
- **Trace payloads**: Keep full tool input after redacting known credential fields. Retain data until manual deletion. Expose it to callers that can already read the run.
- **Recovery**: Use a 15-minute lease without a heartbeat. Retry stale read-only work. Mark stale write-capable work for review.
- **DataForSEO**: Use connect and read timeouts, capped retries, collision-safe manifest names, and a 30-minute polling limit. Preserve submitted task IDs when polling stops.
- **Validation**: Use strict known task values, server-controlled comment authors, and conservative limits: title 500 characters, description and notes 20,000 characters, comments 10,000 characters, list limit maximum 200, and audit days from 1 to 365.
- **Out of scope**: No task queue, external tracing system, full migration framework, task deletion redesign, shared memory-file locking, or global agent-timeout redesign.

---

## Phase 1: Idempotent task execution

**User stories**: Operators can execute a task safely; repeated requests do not create duplicate paid work; clients receive one stable run ID.

### What to build

Create an end-to-end task-claim flow. An execute request accepts or generates a request ID, atomically claims an unclaimed task, creates one active run, and marks the task as active. A later request for the same active task returns the existing run record without starting another agent or external write.

### Acceptance criteria

- [ ] Two concurrent execute requests create at most one active run.
- [ ] A duplicate request returns the existing run ID and status.
- [ ] The task and run claim are committed as one safe state change.
- [ ] The request ID is returned and stored with the run.
- [ ] A completed or failed task can still start a new run under the existing rules.
- [ ] API and concurrency tests cover manual and campaign task execution.

---

## Phase 2: Reliable DataForSEO requests

**User stories**: Data pulls do not hang forever; transient failures are retried safely; submitted task IDs survive a later failure.

### What to build

Harden the DataForSEO client and its recovery path. Apply connect and read timeouts to every request, cap retry delays, write a recovery manifest after each successful submission batch, and use collision-safe names for manifests and raw logs. Poll until completion or the 30-minute limit. On timeout, raise a typed recovery error that includes the preserved task IDs and manifest location.

### Acceptance criteria

- [ ] Network connection and read stalls end within the configured timeout.
- [ ] Retry delays are bounded, including server-provided retry delays.
- [ ] A failure after one successful batch leaves all submitted task IDs recoverable.
- [ ] Concurrent submissions do not overwrite manifest or raw-log files.
- [ ] Polling stops at 30 minutes and returns a clear recovery state.
- [ ] Existing completed-result behaviour remains unchanged.
- [ ] DataForSEO client, pipeline, and recovery tests cover these cases.

---

## Phase 3: Run tracing and event access

**User stories**: Operators can follow one request through a run; tool activity is visible; tracing problems do not stop useful agent work.

### What to build

Create a trace event service for run lifecycle, tool use, retry, heartbeat, recovery, and failure events. Each event includes request ID, run ID, session ID where available, event type, timestamp, duration where available, and outcome. Redact known credential fields before storing full tool input. Add a paginated run-event endpoint with page and limit parameters.

### Acceptance criteria

- [ ] Run events can be queried by run ID with bounded page size.
- [ ] Events contain enough identifiers to connect API, run, session, and tool activity.
- [ ] Known credential fields are redacted before persistence.
- [ ] Oversized event data is handled within a defined database limit.
- [ ] A trace write failure is recorded or logged without failing the agent run.
- [ ] Existing run lifecycle events remain available.
- [ ] API, redaction, pagination, and failure-isolation tests pass.

---

## Phase 4: Health reporting

**User stories**: Operators can quickly tell whether the service, database, and background worker are usable.

### What to build

Extend the existing health response without adding a new route. Keep the endpoint fast. Report service liveness, database reachability, autopilot worker state, and a clear overall status. Do not expose secrets or detailed internal errors.

### Acceptance criteria

- [ ] A healthy service reports database and worker status clearly.
- [ ] A database failure produces a non-healthy result.
- [ ] A stopped or failed background worker is visible.
- [ ] The health endpoint does not start paid work or perform long checks.
- [ ] Health responses remain safe to use for local process monitoring.
- [ ] Health tests cover healthy and failed dependencies.

---

## Phase 5: Run leases and stale-run recovery

**User stories**: Crashed runs do not remain active forever; read-only work can recover; external-write work is not retried blindly.

### What to build

Add a run lease with heartbeat updates. A run without a heartbeat for 15 minutes becomes stale. Read-only stale runs move to a recoverable state and may retry once under the existing run rules. Write-capable stale runs move to review-required state and do not retry automatically. Record every transition as a run event and expose the state through existing run and task responses.

### Acceptance criteria

- [ ] Active runs update their heartbeat during meaningful work.
- [ ] Runs with a current heartbeat are not reclaimed.
- [ ] A stale read-only run becomes recoverable without creating an unsafe duplicate.
- [ ] A stale write-capable run is blocked and marked for review.
- [ ] Recovery transitions clear or preserve active-run state correctly.
- [ ] Recovery is safe after process restart.
- [ ] Lease, heartbeat, stale detection, and retry tests pass.

---

## Phase 6: Comment-autopilot recovery

**User stories**: Comment actions are claimed once; crashed actions do not remain stuck; the background worker survives unexpected errors.

### What to build

Make comment-action claiming durable. Claim pending work with a database-backed state change, record a lease and heartbeat, reclaim stale actions after 15 minutes, and apply the same read-only versus write-capable recovery rule. Add an exception boundary around each worker cycle so one unexpected error does not stop future processing.

### Acceptance criteria

- [ ] One comment action cannot be claimed twice by concurrent processing attempts.
- [ ] A running action can be reclaimed after its lease expires.
- [ ] A stale action records its last error and recovery state.
- [ ] An unexpected worker error is logged and the next cycle still runs.
- [ ] Retry attempt counts remain bounded.
- [ ] Existing comment trigger and reply behaviour remains unchanged.
- [ ] Autopilot concurrency, stale recovery, and worker-survival tests pass.

---

## Phase 7: Strict API validation

**User stories**: Invalid task data is rejected before execution; comments cannot impersonate the agent; large inputs do not create uncontrolled storage or prompt growth.

### What to build

Strengthen task, comment, list, and audit request schemas. Accept only known task statuses and execution types, while allowing null execution type for manual tasks. Enforce text and numeric limits. Set comment authors on the server instead of accepting an arbitrary author from the client. Preserve clear validation errors for API callers.

### Acceptance criteria

- [ ] Unknown task statuses are rejected.
- [ ] Unknown execution types are rejected before execution.
- [ ] Null execution type remains valid for manual tasks.
- [ ] Clients cannot submit comments as the agent.
- [ ] Text, list, priority, and audit-day limits are enforced.
- [ ] Validation errors use stable, clear API responses.
- [ ] Existing valid task, comment, and audit requests continue to work.
- [ ] API validation and regression tests pass.
