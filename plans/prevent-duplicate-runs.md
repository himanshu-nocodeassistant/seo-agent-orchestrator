# Plan: Prevent Duplicate Runs

> Source PRD: [GitHub issue #7](https://github.com/himanshu-nocodeassistant/seo-agent-orchestrator/issues/7)

## Architectural decisions

Durable decisions that apply across all phases:

- **Routes**: Keep `POST /tasks/{id}/execute` with `resume` as a query flag. Require `Idempotency-Key`. Apply the same contract to run-starting SEO audit requests.
- **Lease**: Store one current lease per task with the run, owner token, increasing fence version, state, and Unix-time acquisition, heartbeat, expiry, and release values.
- **Idempotency**: Store an append-only request record. Make request scope plus key unique. Bind it to a request fingerprint and run.
- **Claim transaction**: Create or bind the request, create or select the run, acquire the lease, and update task pointers in one transaction.
- **Conflict contract**: Replay the original run for the same key and fingerprint. Return `409 Conflict` for a changed fingerprint or another live request. Include the active run ID and status.
- **Lease timing**: Use a configurable five-minute timeout. Renew near one-third of the timeout. Use a controlled clock in tests.
- **Fencing**: Heartbeats, checkpoints, finalization, release, task updates, and terminal comments must match the current owner and fence version.
- **Resume**: Resume only an approved campaign in `awaiting_approval`. Reuse its run, plan, phase outputs, and completed child runs.
- **Recovery**: Mark replaced stale read-only runs `expired`. Do not resume stale single-agent runs. Mark uncertain external writes `needs_review`, block the task, and require `acknowledge_stale=true` with a new key before fresh manual execution.
- **Autopilot**: Replace process-local correctness with database claims. Use attempt-scoped internal idempotency keys and recover stale actions.
- **Compatibility**: Keep `active_run_id` as a display pointer. Keep existing run response fields. Add optional fields only.
- **TDD rule**: For each behavior, add one failing external-behavior test, make it pass with the minimum change, and refactor only while focused tests stay green.

---

## Phase 1: One Protected Manual Run

**User stories**: 1, 3–5, 7, 10–12, 32

### What to build

Deliver one complete protected manual-execution path. A task claim and run are created atomically. One worker executes. A concurrent worker receives a clear conflict. The Kanban view shows the active run and does not start duplicate work.

### Acceptance criteria

- [ ] **RED**: A file-backed SQLite test with two independent sessions and two valid, different request keys proves that both workers can currently claim one task.
- [ ] **GREEN**: Exactly one worker creates a run and owns the lease.
- [ ] **GREEN**: The other request returns `409` with the active run ID and status.
- [ ] **GREEN**: The losing request creates no run, start event, start comment, or agent call.
- [ ] **GREEN**: Success and failure release only the lease owned by that run.
- [ ] **GREEN**: Existing single manual execution still completes through the API and UI.

---

## Phase 2: Durable Idempotent Execute Requests

**User stories**: 2, 6, 30

### What to build

Add a durable request identity to the protected manual path. The client creates one key per user action. Retries with the same request return the first run in any state. Misuse of a key fails without new work.

### Acceptance criteria

- [ ] **RED**: Repeating one request key currently creates a second run.
- [ ] **GREEN**: The first request stores its key, fingerprint, and run binding.
- [ ] **GREEN**: The same key and fingerprint returns the original queued, running, or terminal run.
- [ ] **GREEN**: Replay creates no new comments, events, leases, or agent calls.
- [ ] **GREEN**: Reusing the scoped key with another task, execution type, parameter set, or resume mode returns `409`.
- [ ] **GREEN**: Missing public keys fail validation, while the Kanban client always sends a generated key.
- [ ] **GREEN**: UI tests prove that execute, resume, and SEO audit actions send a key and that a retry of the same action reuses its key.
- [ ] **GREEN**: Replay works from a new database session and after process restart.

---

## Phase 3: Stale-Lease Recovery and Fencing

**User stories**: 8–12, 23

### What to build

Keep healthy work alive with heartbeats and recover tasks after worker failure. A new owner can claim an expired lease. The prior worker loses authority to change task or run state. Recovery stops for review when an external write has an uncertain result.

### Acceptance criteria

- [ ] **RED**: A seeded stale lease currently blocks work or lets an old worker clear newer state.
- [ ] **GREEN**: A fresh lease rejects another request until it expires.
- [ ] **GREEN**: Heartbeats extend only the current owner’s lease.
- [ ] **GREEN**: A new key can replace an expired lease and marks the prior run `expired`.
- [ ] **GREEN**: Reclaim increments the fence version and uses a new owner token.
- [ ] **GREEN**: A stale worker cannot checkpoint, finalize, release, change task state, clear `active_run_id`, or add a terminal comment.
- [ ] **GREEN**: A write-capable run with uncertain effects becomes `needs_review`, the task becomes `blocked`, and no automatic replay occurs.
- [ ] **GREEN**: Run and task reads expose the review state, and one event and comment explain the required action.
- [ ] **GREEN**: Fresh manual execution is allowed only with `acknowledge_stale=true` and a new key. Automatic paths cannot acknowledge it.
- [ ] **GREEN**: Tests use fixed time. They do not wait for real timeout periods.

---

## Phase 4: Safe Campaign Start, Pause, and Resume

**User stories**: 13–23

### What to build

Protect the full campaign life cycle with the same lease and request rules. Save each phase result as a durable checkpoint. Approval pause keeps the campaign identity. Resume claims that campaign once and skips all completed work.

### Acceptance criteria

- [ ] **RED**: Concurrent campaign starts or resumes currently create duplicate planning or phase work.
- [ ] **GREEN**: One campaign request creates one plan, parent run, and expected child runs.
- [ ] **GREEN**: Safe phase parallelism remains available within one owned campaign.
- [ ] **GREEN**: Each completed phase is durably saved before later work starts.
- [ ] **GREEN**: Approval pause records `awaiting_approval`, keeps the original run identity, and blocks a fresh execute request.
- [ ] **GREEN**: Resume requires the target paused run, approval, a matching key, and a new valid lease owner.
- [ ] **GREEN**: Resume does not regenerate the plan or rerun completed phases.
- [ ] **GREEN**: Two concurrent resume requests continue pending phases once.
- [ ] **GREEN**: Completed, failed, malformed, unapproved, and non-paused campaigns cannot resume.
- [ ] **GREEN**: An uncertain in-flight write phase becomes `needs_review`, blocks the parent task, emits one review event and comment, and cannot resume automatically.
- [ ] **GREEN**: After external verification, the operator can use `acknowledge_stale=true` and a new key to start fresh work. The old campaign is never resumed.

---

## Phase 5: Multi-Worker Comment Autopilot

**User stories**: 24–28, 30

### What to build

Move Comment Autopilot correctness into the database. One worker claims one comment action and the shared task lease. Crashed actions become retryable. Manual and automatic execution cannot overlap.

### Acceptance criteria

- [ ] **RED**: Two independent autopilot workers can currently select the same comment action.
- [ ] **GREEN**: Exactly one worker claims the action, increments its attempt once, and calls the agent once.
- [ ] **GREEN**: A completed action cannot run again.
- [ ] **GREEN**: A stale running action can start its next allowed attempt with an attempt-scoped key.
- [ ] **GREEN**: A manual run and an autopilot run for one task cannot overlap.
- [ ] **GREEN**: Completion and failure comments are written once.
- [ ] **GREEN**: Multi-worker tests pass without a process-local lock.

---

## Phase 6: Protect All Remaining Run Starters

**User stories**: 15, 29, 30

### What to build

Extend the proven claim and idempotency contract to SEO audits and campaign child phases. Preserve valid child-phase parallelism across different tasks while preventing duplicate work for the same child task or audit request.

### Acceptance criteria

- [ ] **RED**: Repeated audit requests and duplicate child dispatch can currently create extra work.
- [ ] **GREEN**: SEO audit requires a request key and replays the original audit task and run for the same request.
- [ ] **GREEN**: A changed audit fingerprint returns `409` and creates no task or run.
- [ ] **GREEN**: Each campaign child run uses the shared task-claim rules.
- [ ] **GREEN**: Two claims for the same child task cannot run together.
- [ ] **GREEN**: Claims for different child tasks can run in parallel.
- [ ] **GREEN**: All public and internal run starters use one tested claim interface.

---

## Phase 7: Safe Rollout and Operational Verification

**User stories**: 31, 32

### What to build

Make the safety model deployable on existing SQLite and PostgreSQL installations. Reconcile legacy active-run pointers, expose useful events, and verify the complete system under concurrent load without changing unrelated behavior.

### Acceptance criteria

- [ ] **RED**: An old database without safety records cannot silently start duplicate work.
- [ ] **GREEN**: Startup creates all required safety structures and is repeatable.
- [ ] **GREEN**: Startup fails clearly if the safety migration cannot complete.
- [ ] **GREEN**: A legacy task with `active_run_id` and no lease is treated as busy until reconciled.
- [ ] **GREEN**: Claim, replay, heartbeat, expiry, reclaim, conflict, pause, resume, and release events are recorded without owner-token secrets.
- [ ] **GREEN**: Existing manual, campaign, approval, retry, autopilot, audit, security, and UI tests remain green.
- [ ] **GREEN**: Concurrent-worker tests pass against a temporary file-backed database with separate sessions.
- [ ] **GREEN**: The full test suite passes without access to the production database.
