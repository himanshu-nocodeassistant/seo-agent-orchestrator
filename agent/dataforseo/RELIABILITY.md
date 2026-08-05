# DataForSEO Client Reliability

This documents failure modes hit while running large SERP Standard Queue
batches (e.g. `scripts/serp_standard_report.py`), and how `client.py` now
handles each one. Read this before writing a new script against
`DataForSEOClient`, `_task_post`, or `_task_post_and_poll`.

## Incident: tier-1 SERP run, 2026-07-01

Running 260 tasks (65 keywords x 4 locations) through Standard Queue hit
three separate failures back to back:

1. `_task_get` only recognized DataForSEO status `40601` ("Task In Queue")
   as "not ready yet, keep polling." The API also returns `40602` for the
   same condition, which fell through to the generic error branch and
   crashed the whole batch mid-poll.
2. `_task_post_and_poll` raised immediately when a single task wasn't
   ready after `max_wait`, discarding results already collected for every
   other task in the batch.
3. A one-off dropped connection (`RemoteDisconnected`) on a single
   `task_get` call crashed the entire recovery run, even though ~70% of
   tasks had already resolved successfully in that same loop.

None of these lost data permanently — task IDs were still recoverable
from the request/response logs `log_result` writes on every call — but
recovery required manually digging through JSON log files to reconstruct
which task IDs belonged to which keyword/location/tag, and re-running the
whole batch was tempting (and would have re-billed already-paid tasks).

## Fixes in `client.py`

### 1. Retry transient errors instead of crashing (`_request_with_retry`)

`_post` and `_get` now route every HTTP call through
`_request_with_retry`, which retries with exponential backoff (2s, 4s,
8s, 16s, 32s — `MAX_RETRIES = 5`) on:

- Rate limits and transient server errors: HTTP `429`, `502`, `503`, `504`
- Dropped connections / timeouts: `requests.exceptions.ConnectionError`,
  `requests.exceptions.Timeout`

Anything else (auth failures, malformed requests, other 4xx) raises
immediately — these aren't retryable and retrying would just waste time
and quota.

### 2. Recognize all "not ready" statuses (`TASK_NOT_READY_STATUSES`)

`_task_get` treats both `40601` and `40602` as "still in queue, keep
polling" (`TASK_NOT_READY_STATUSES = (40601, 40602)`), not just `40601`.
If DataForSEO introduces another queue-related status code in the future,
add it here rather than to the generic error path.

### 3. Persist task IDs immediately after submission (`_write_manifest`)

Every `_task_post` call writes a manifest to
`dataforseo/manifests/<timestamp>_<endpoint>.json` **before** any polling
starts:

```json
{
  "endpoint": "serp/google/organic/task_post",
  "created_at": "20260701-124732",
  "tasks": [
    {"task_id": "07011547-...", "request": {"keyword": "...", "location_code": 2840, "tag": "..."}}
  ]
}
```

This means a crash anywhere downstream of submission — a bug in the poll
loop, a killed process, a network partition — can never lose the mapping
from task ID back to what was requested. Recover results for a manifest
with:

```bash
python scripts/serp_recover_from_ids.py --manifest dataforseo/manifests/20260701-124732_serp_google_organic_task_post.json --output dataforseo/compiled/recovered.csv
```

This only calls `task_get` (a free read) on the existing IDs — it never
resubmits or re-bills anything.

### 4. One straggler no longer kills the batch

`_task_post_and_poll` now skips (logs a warning) any task still not ready
after `max_wait`, instead of raising and discarding every result already
collected for the rest of the batch. Skipped task IDs remain in the
manifest and can be recovered later with `serp_recover_from_ids.py` once
they finish processing on DataForSEO's side.

## Before running a large batch

- Check `dataforseo/manifests/` isn't accumulating stale manifests you
  meant to recover from and forgot about.
- For >100 tasks, expect the Standard Queue to take much longer than
  `max_wait` defaults assume for some fraction of tasks — treat "skipped"
  tasks as normal, not an error, and recover them separately afterward.
- Never re-run a submission script to "fix" a partial failure without
  first checking `dataforseo/manifests/` for an existing manifest covering
  the same keywords — re-running re-submits and re-bills.
