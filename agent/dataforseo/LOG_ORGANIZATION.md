# Log Organization: Grouping by Tag/Keyword/Location

Read this before changing `logger.py` or writing scripts that read `dataforseo/raw/`.

## Problem

`log_result` currently writes one file per API call, foldered by endpoint
path:

```
dataforseo/raw/serp/google/organic/task_post/2026-07-01/12-47-32_weweb-agency.json
dataforseo/raw/serp/google/organic/task_get/advanced/07011547-...-bbe4bf3d1e08/2026-07-01/14-39-09_no-keyword.json
```

This mirrors API mechanics, not the thing you actually want to query
("show me every call for `weweb agency` in the US"). Two issues make that
query hard today:

- `task_post` writes are batched: one call submits up to 100 tasks (many
  keyword x location combos) into a single file. The file doesn't belong
  to one keyword.
- `task_get` files are keyed by opaque `task_id` and literally named
  `no-keyword` in the filename — the real `keyword`/`tag`/`location_code`
  only exist inside `result.tasks[0].data`, not the path.

Finding a specific keyword's history means grepping file contents across
the whole tree.

## Target layout

```
dataforseo/raw/<tag>/<keyword-slug>/<location_code>/<YYYY-MM-DD>_<HH-MM-SS>_<task_post|task_get>.json
```

Example, for `weweb agency` tracked under `tier1_service_weweb`, US
(2840):

```
dataforseo/raw/tier1_service_weweb/weweb-agency/2840/
├── 2026-07-01_12-46-44_task_post.json     # 1st submission (retry/dup)
├── 2026-07-01_12-47-32_task_post.json     # 2nd submission
├── 2026-07-01_13-00-23_task_get.json      # poll 1 (not ready)
├── 2026-07-01_14-23-24_task_get.json      # poll 2 (not ready)
└── 2026-07-01_14-39-09_task_get.json      # poll 3 (ready, has results)
```

The folder is a **growing directory, not a one-call-one-file mapping**.
Every call touching this keyword+location, from any endpoint, at any
time, lands here as a new timestamped file. Nothing overwrites; repeats
(retries, duplicate submissions, repeated polls) just accumulate side by
side, same as today.

`ls dataforseo/raw/tier1_service_weweb/` lists every keyword tracked under that
tier/page. `ls dataforseo/raw/tier1_service_weweb/weweb-agency/` lists every
location tracked for that keyword. No grepping required.

## Splitting batched `task_post` calls

A single `task_post` API call can cover multiple keywords and locations
at once — e.g. one call submitting `weweb agency US`, `weweb agency UK`,
and `bubble agency US` together. The response's `result["tasks"]` array
has one entry per submitted task, each carrying its own `data.keyword`,
`data.location_code`, `data.tag`.

`log_result` splits this: it iterates `result["tasks"]` and writes **one
file per task**, routed to that task's own `tag/keyword-slug/location/`
folder — using each task's own `data` fields, not any single shared
value. One API call fans out to N files across N different folders:

```
dataforseo/raw/tier1_service_weweb/weweb-agency/2840/2026-07-01_12-47-32_task_post.json
    → {id, data: {keyword: "weweb agency", location_code: 2840, tag: "tier1_service_weweb"}, status: "Task Created"}

dataforseo/raw/tier1_service_weweb/weweb-agency/2826/2026-07-01_12-47-32_task_post.json
    → {id, data: {keyword: "weweb agency", location_code: 2826, ...}, status: "Task Created"}

dataforseo/raw/tier1_service_bubble/bubble-agency/2840/2026-07-01_12-47-32_task_post.json
    → {id, data: {keyword: "bubble agency", location_code: 2840, tag: "tier1_service_bubble"}, status: "Task Created"}
```

Same timestamp on all three (submitted in the same call), but each file
contains only that one task's own record. No cross-contamination between
keyword+location combos that happened to ship in the same batch.

`task_get` calls are already one-task-per-call (each poll hits a single
`task_id`), so no splitting is needed there — just route the single file
to its `tag/keyword/location` folder using `result.tasks[0].data`.

## What's preserved vs. what needs a manifest

Splitting a batch preserves every per-task field (`id`, `data`, per-task
`cost`, `status`) — nothing about an individual task's record is lost.

What does **not** travel with a per-task split file: the shared call-level
envelope (`tasks_count`, aggregate `cost`, overall `time` for the whole
batch). That envelope is what answers "which N tasks were submitted
together in one call, for what total cost" — a different question than
"what happened to this one keyword."

This is already covered by the existing manifest mechanism (see
`RELIABILITY.md` "Persist task IDs immediately after submission"):
`dataforseo/manifests/<timestamp>_<endpoint>.json` records the full batch
(all task ids + their keyword/location/tag + aggregate cost) at
submission time. The tag/keyword/location split and the manifest are
complementary, not redundant — keep both. Do not remove manifest writing
when implementing the split.

## Extraction source of truth

- For `task_post`: iterate `result["tasks"]`; each entry's `data.keyword`,
  `data.tag`, `data.location_code` is authoritative for that task.
- For `task_get`: `result["tasks"][0]["data"].keyword` /
  `.tag` / `.location_code` is authoritative. The top-level `payload` sent
  to `log_result` is `[]` for `task_get` calls — do NOT rely on `payload`
  to extract keyword/tag/location for this endpoint, only `result`.

## Stale poll log cleanup

Every poll attempt is logged — including not-ready responses (status_code 40601
"Task In Queue" / 40602 "Task In Progress"). These transient snapshots have no
informational value once the task completes: the final "Ok." file (status_code
20000) in the same folder supersedes them, and the task_id is already in the
`task_post` log and the manifest.

**Automatic cleanup (ongoing):** `_task_post_and_poll` calls
`purge_stale_poll_logs(tasks[0])` (from `logger.py`) immediately after a
successful `task_get`. This scans the `tag/keyword/location_code/` folder for
sibling `*task_get*.json` files with a not-ready status_code and deletes them.
Only the just-written success file survives.

**One-time purge:** `scripts/purge_stale_poll_logs.py` walks the entire `dataforseo/raw/`
tree and performs the same check across all existing files. Supports `--dry-run`.

```
python scripts/purge_stale_poll_logs.py --dry-run  # preview
python scripts/purge_stale_poll_logs.py             # execute
```
