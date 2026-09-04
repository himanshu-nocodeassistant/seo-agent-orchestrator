# Webflow writes should wait for approval

Parent PRD: [GitHub issue #5](https://github.com/himanshu-nocodeassistant/seo-agent-orchestrator/issues/5)

## Goal

Require an operator to review and approve every Webflow create, update, and publish action before it can change live content.

The operator must see the complete proposal. CMS text and user text must not be silently truncated.

## Non-goals

- Multi-approver workflows, roles, delegation, or approval expiry.
- Rollback or a full Webflow version history.
- Queue infrastructure or a new worker system.
- Approval for writes to other integrations.
- Automatic content quality scoring.
- Per-item approval.

## Durable design decisions

- Put the approval check at the server Webflow write boundary. Prompt instructions are not a control.
- A write task first creates a proposal. Proposal generation can read Webflow data but cannot write.
- Store one complete proposal per task. It includes the operation, target, before values, after values, full payload, status, timestamps, approver, and apply result.
- Use task-level approval. One approval covers all changes in the task, including internal-link batches.
- Use dedicated approve and reject actions. A generic task update must not count as approval.
- Apply the stored proposal with no model call. Re-read the target before apply and mark the proposal stale if values changed.
- Use idempotency keys and one active-run guard per task.
- Preserve visible CMS and user text in storage and previews. Fence untrusted text before it enters prompts.
- Limit only metadata, labels, logs, and model context. Use chunking, retrieval, or a clear summary for large model input.
- Attach audit events to every run path. Redact secrets and session identifiers.
- Keep read-only and draft-only tasks working without approval.
- Require normal API authentication and CORS controls on approval actions.

## Phase 1. Approve one Webflow update

User stories: 1, 3, 4.

Build one complete path for an update to an existing Webflow item. This is the first child issue.

### Schema

- Add proposal storage with a status lifecycle for pending, approved, rejected, applied, failed, and stale states.
- Store the full before snapshot and full approved payload.
- Store approval and apply timestamps, actor identity, run identity, and idempotency data.
- Add the migration and indexes needed to find proposals by task and status.

### API and execution

- Make a write task produce a validated proposal instead of calling a Webflow write tool.
- Return a machine-readable pending state.
- Add read, approve, and reject actions for the task proposal.
- Apply only the stored proposal after approval.
- Re-read the Webflow item before apply and block the write if the before values changed.

### UI

- Show the task as pending approval.
- Show operation, target, full before values, and full after values.
- Show clear approved, rejected, applied, failed, and stale states.
- Add approve and reject controls.

### Tests

- An unapproved task makes no Webflow write call.
- Approval applies the exact stored payload.
- Rejection never calls Webflow.
- A changed target becomes stale and does not receive the update.
- Repeated approval does not apply the update twice.
- The existing read-only and draft-only flows still work.

### Acceptance criteria

- No Webflow update can happen before approval.
- An operator can review the full update and approve or reject it.
- The server applies the approved payload without another model call.
- Stale data blocks the update with a clear next action.

## Phase 2. Add create and publish

User stories: 3, 4, 7.

Extend the approved update path to Webflow creates and publishes. This is the second child issue.

### Schema

- Store complete create fields, slug, and publish intent.
- Store the created Webflow item identity and per-operation result.
- Keep retry state so an approved create cannot create a duplicate.

### API and execution

- Gate create and publish with the same proposal policy.
- Check for an existing matching item before create.
- Apply create first when publish depends on a new item, then store its identity.
- Make approval and apply idempotent.

### UI

- Show the full create payload and publish action before approval.
- Show the created item identity and publish result after apply.
- Show a clear duplicate or retry state.

### Tests

- Create, update, and publish all require approval.
- A create retry does not create a second item.
- Publish uses the approved item and approved fields.
- A failed publish does not repeat the create.
- Repeated approval is safe.

### Acceptance criteria

- No create or publish happens before approval.
- The full approved create payload is applied once.
- A retry cannot create a duplicate item.
- The operator can see the result of each operation.

## Phase 3. Approve internal-link batches

User stories: 2, 6, 7.

Add one task-level proposal for several internal-link changes. This is the third child issue.

### Schema

- Store each proposed item change under the task proposal.
- Store ordered per-item results, errors, and retry eligibility.
- Keep the full link text and target data.

### API and execution

- Generate one proposal for the full batch.
- Use one approval for the task.
- Apply items in order with the same exact-payload and stale-data checks.
- Do not roll back successful items.
- Allow retry only for items that did not apply, after revalidation.

### UI

- Show the full batch before approval.
- Make each item and proposed change easy to inspect.
- Show success, failure, stale, and retry state per item.

### Tests

- One approval covers the full batch.
- No item writes before approval.
- Every item receives the approved payload.
- Partial failure reports exact item status.
- Retry does not repeat successful items.

### Acceptance criteria

- An operator approves the batch once.
- The system reports the result for every item.
- A partial failure does not hide completed work or repeat it.

## Phase 4. Preserve text and trace actions

User stories: 5, 8.

Make content handling and audit coverage consistent across all run paths. This is the fourth child issue.

### Schema and audit

- Keep full proposal content in storage that supports long text and structured data.
- Record proposal creation, approval, rejection, apply, stale, failure, and retry events.
- Redact secrets and session identifiers from audit metadata.

### Prompt and display handling

- Fence external, stored, and user text before prompt assembly.
- Remove hidden or forged control markers only. Keep visible text unchanged.
- Do not truncate CMS or user text in storage, proposals, or previews.
- Use chunking, retrieval, or an explicit summary for large model input.
- Apply clear bounds to metadata, labels, logs, and model context only.

### Tests

- Long CMS and user text survives storage and preview unchanged.
- Fencing blocks control markers without changing visible content.
- All run paths create the expected audit events.
- Audit records contain no secrets or session identifiers.
- Large model input uses an explicit chunk, retrieval, or summary path.

### Acceptance criteria

- No CMS or user text is silently cut.
- Every Webflow write task has a traceable proposal and decision.
- The agent cannot use stored text as an instruction to bypass approval.

## Phase 5. Harden and roll out

User stories: 3, 6, 7, 8.

Close the reliability and deployment gaps before enabling the workflow for production. This is the fifth child issue.

### API and runtime

- Guard one active run per task.
- Enforce authentication and CORS rules on approval actions.
- Validate execution types and proposal shapes early.
- Return clear errors for malformed or unsupported operations.

### Data and deployment

- Use real schema migrations, UTC timestamps, and useful indexes.
- Keep the safe write policy enabled by default in production.
- Allow any local bypass only through an explicit local setting.
- Add operational checks for failed, stale, partial, and stuck proposals.

### Tests and CI

- Test concurrent execute requests for one task.
- Test auth, CORS, invalid execution types, and malformed proposals.
- Run the full suite with supported Python versions.
- Add format and lint checks.
- Add Webflow contract tests for supported operations and unsupported fields.

### Acceptance criteria

- Concurrent runs cannot produce conflicting proposals.
- Protected routes reject unauthorised approval requests.
- Production cannot bypass the Webflow approval policy by default.
- CI checks the safety and reliability rules.

## Rollout order

1. Title and metadata updates.
2. H1 updates.
3. Blog create and publish.
4. Internal-link batches.

Keep the parent PRD open. Create one child GitHub issue per phase when that phase starts, and link it to issue #5.

## Definition of done

- Every Webflow create, update, and publish has a proposal and approval record.
- Zero Webflow writes happen before approval.
- The server applies only the stored approved payload.
- Stale targets block overwrite.
- Retries do not duplicate work.
- CMS and user text stays complete.
- All run paths have safe audit records.
- The full test suite, format checks, lint checks, and supported Python version checks pass.
