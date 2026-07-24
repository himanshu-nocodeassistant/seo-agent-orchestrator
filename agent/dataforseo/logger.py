import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# DataForSEO status codes for tasks that aren't ready yet.
# Mirrors TASK_NOT_READY_STATUSES in client.py — kept separate to avoid a
# circular import (client imports logger).
_NOT_READY_STATUS_CODES = frozenset({40601, 40602})

# Resolves to <project-root>/logs/ regardless of nesting depth:
# agent/dataforseo/logger.py -> agent/dataforseo/ -> agent/ -> project root
LOGS_DIR = Path(__file__).parent.parent.parent / "dataforseo" / "raw"

# See agent/dataforseo/LOG_ORGANIZATION.md for the full design rationale.
CALL_KIND_BY_SUFFIX = {
    "task_post": "task_post",
    "task_get": "task_get",
}


def log_result(endpoint: str, payload: list, result: dict) -> list[Path]:
    """
    Write a timestamped JSON log entry for every DataForSEO API call.

    Calls that carry per-task `tag`/`keyword`/`location_code` (tracked SERP
    tasks) are grouped and, if the call was a batch, split so each task's
    slice lands in its own folder:

        logs/<tag>/<keyword-slug>/<location_code>/<YYYY-MM-DD>_<HH-MM-SS>_<task_post|task_get>.json

    One task_post call can cover multiple keyword/location combos at once;
    each is written as a separate file using that task's own `data` fields
    (never the shared payload). task_get calls are already one task per
    call. See LOG_ORGANIZATION.md for why this doesn't lose the batch-level
    view (that's `logs/task_manifests/`, written separately by client.py).

    Calls without per-task tag/keyword/location (most non-SERP endpoints:
    backlinks, keywords_data, labs, locations/languages lookups, etc.) fall
    back to the old endpoint-mirrored layout:

        logs/<endpoint>/<...>/<YYYY-MM-DD>/<HH-MM-SS>_<keyword-or-no-keyword>.json
    """
    now = datetime.now(timezone.utc)
    call_kind = _call_kind(endpoint)
    tasks = result.get("tasks") or []

    written = []
    for task in tasks:
        data = task.get("data") or {}
        tag = data.get("tag")
        keyword = data.get("keyword")
        location_code = data.get("location_code")
        if tag and keyword and location_code is not None:
            written.append(
                _write_grouped(now, tag, keyword, location_code, call_kind, task)
            )

    if written:
        return written

    # Fallback: no task carried tag/keyword/location_code (non-SERP calls,
    # or SERP calls where the task didn't create/resolve cleanly).
    return [_write_legacy(now, endpoint, payload, result)]


def _call_kind(endpoint: str) -> str:
    # task_get endpoints are called as ".../task_get/<variant?>/<task_id>",
    # so the segment we care about isn't always last (task_id is).
    parts = endpoint.strip("/").split("/")
    for segment in parts:
        if segment in CALL_KIND_BY_SUFFIX:
            return CALL_KIND_BY_SUFFIX[segment]
    return _slugify(parts[-1]) or "call"


def _write_grouped(
    now: datetime,
    tag: str,
    keyword: str,
    location_code: int,
    call_kind: str,
    task: dict,
) -> Path:
    log_dir = LOGS_DIR / _slugify(tag) / _slugify(keyword) / str(location_code)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{now.strftime('%Y-%m-%d_%H-%M-%S')}_{call_kind}.json"
    entry = {"timestamp": now.isoformat(), **task}
    log_file.write_text(json.dumps(entry, indent=2, ensure_ascii=False))
    return log_file


def _write_legacy(now: datetime, endpoint: str, payload: list, result: dict) -> Path:
    parts = endpoint.strip("/").split("/")
    log_dir = LOGS_DIR.joinpath(*parts) / now.strftime("%Y-%m-%d")
    log_dir.mkdir(parents=True, exist_ok=True)

    keyword = _extract_keyword(payload)
    keyword_slug = _slugify(keyword) if keyword else "no-keyword"
    log_file = log_dir / f"{now.strftime('%H-%M-%S')}_{keyword_slug}.json"

    entry = {
        "timestamp": now.isoformat(),
        "endpoint": endpoint,
        "payload": payload,
        "result": result,
    }
    log_file.write_text(json.dumps(entry, indent=2, ensure_ascii=False))
    return log_file


def _extract_keyword(payload: list) -> Optional[str]:
    if not payload:
        return None
    first = payload[0] if isinstance(payload, list) else payload
    kws = first.get("keywords")
    if kws and isinstance(kws, list) and kws:
        return kws[0]
    if first.get("keyword"):
        return first.get("keyword")
    # ai_optimization/llm_mentions shape: `target` is a list of
    # {"keyword"|"domain": ...} dicts, not a scalar. Prefer a keyword
    # (the "what") over a domain (the "who") regardless of list order, so
    # the log lands under a readable slug.
    target = first.get("target")
    if isinstance(target, list):
        entries = [e for e in target if isinstance(e, dict)]
        for entry in entries:
            if entry.get("keyword"):
                return entry["keyword"]
        for entry in entries:
            if entry.get("domain"):
                return entry["domain"]
        return None
    if isinstance(target, str):
        return target
    return first.get("url")


def purge_stale_poll_logs(task_data: dict) -> int:
    """Delete not-ready task_get snapshots for a keyword/location after success.

    Called after a task_get returns status 20000 ("Ok."). Scans the same
    tag/keyword/location_code folder and removes any earlier poll files whose
    status_code is a not-ready code (40601 / 40602). The just-written success
    file is left intact.

    Args:
        task_data: A single task dict from data["tasks"][0] — must contain
                   ``data.tag``, ``data.keyword``, ``data.location_code``.

    Returns:
        Number of stale files deleted.
    """
    meta = task_data.get("data") or {}
    tag = meta.get("tag")
    keyword = meta.get("keyword")
    location_code = meta.get("location_code")
    if not (tag and keyword and location_code is not None):
        return 0

    log_dir = LOGS_DIR / _slugify(tag) / _slugify(keyword) / str(location_code)
    if not log_dir.exists():
        return 0

    deleted = 0
    for f in log_dir.glob("*task_get*.json"):
        try:
            content = json.loads(f.read_text(encoding="utf-8"))
            if content.get("status_code") in _NOT_READY_STATUS_CODES:
                f.unlink()
                deleted += 1
        except (json.JSONDecodeError, OSError):
            pass
    return deleted


def _slugify(text: str) -> str:
    # Defense in depth: a logging helper must never raise and discard a
    # paid API response, so coerce whatever reaches it to a string.
    text = str(text).lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text[:60]
