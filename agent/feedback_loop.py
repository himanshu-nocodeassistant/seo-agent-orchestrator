"""SEO feedback loop: deterministic change logging and learnings.

Extracted from the former agent/api/main.py monolith (see git history).
"""

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# Single registry: execution types that mutate live CMS content and should be change-logged.
# All feedback-loop logic derives from this map — do not hardcode elsewhere.
CMS_CHANGE_FIELD_MAP = {
    "rewrite_title":        "title tag",
    "rewrite_meta_desc":    "meta description",
    "rewrite_h1":           "heading structure",
    "blog_write":           "content",
    "rewrite_blog_content": "content",
    "webflow_publish":      "publish",
    "internal_links":       "internal linking",
}

# Valid statuses for seo-changes.json entries. Enforced on write.
VALID_REVIEW_STATUSES = {
    "pending-review",
    "reviewed-positive",
    "reviewed-negative",
    "reviewed-neutral",
    "reviewed-inconclusive",
}

# Paths for SEO feedback loop persistence.
# Relative to cwd (project root). Single uvicorn worker assumed; add file lock if multi-worker.
# Scalability note (#8): _atomic_json_write uses os.replace() which is atomic on POSIX but
# not safe under concurrent workers. For multi-worker deployments, wrap writes with
# fcntl.flock() (Unix) or replace file-based storage with a DB column or Redis key.
SEO_CHANGES_PATH = Path("memory/seo-changes.json")
SEO_LEARNINGS_PATH = Path("memory/seo-learnings.json")
SEO_CHANGES_MD_PATH = Path(".claude/seo-changes-log.md")
SEO_LEARNINGS_MD_PATH = Path(".claude/seo-learnings.md")
SEO_REVIEW_BATCH_SIZE = int(os.environ.get("SEO_REVIEW_BATCH_SIZE", "20"))


# ============================================================================
# SEO FEEDBACK LOOP — APPLICATION-LAYER PERSISTENCE
# ============================================================================

def _atomic_json_write(path: Path, data: dict) -> None:
    """Write JSON to path atomically via temp file + os.replace().

    Single uvicorn worker assumed. Add a file lock here if multi-worker is needed.
    Creates parent directories if they don't exist.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    os.replace(tmp, path)


def _load_seo_changes() -> dict:
    """Load memory/seo-changes.json. Returns empty structure if file missing."""
    if not SEO_CHANGES_PATH.exists():
        return {"version": 1, "entries": []}
    return json.loads(SEO_CHANGES_PATH.read_text())


def _load_seo_learnings() -> dict:
    """Load memory/seo-learnings.json. Returns empty structure if file missing."""
    if not SEO_LEARNINGS_PATH.exists():
        return {"version": 1, "learnings": {}}
    return json.loads(SEO_LEARNINGS_PATH.read_text())


def _parse_change_log_block(agent_output: str) -> dict:
    """Extract and parse the structured CHANGE_LOG block from agent output.

    The agent is instructed to emit a block of the form:
        <!-- CHANGE_LOG
        { ... json ... }
        -->
    as the very last thing in its response.

    Returns a dict with extraction_status="ok" on success, or
    extraction_status="failed" with a failure_reason on any failure.

    failure_reason values:
        "missing_block"           — CHANGE_LOG comment not found
        "invalid_json"            — block found but JSON parse failed
        "missing_required_fields" — url, field, and after are all null
        "field_mismatch"          — field value present but empty string

    Never raises.
    """
    _null = {"extraction_status": "failed", "url": None, "field": None,
             "before": None, "after": None, "webflow_item_id": None,
             "webflow_status": None, "failure_reason": None}

    try:
        match = re.search(r'<!--\s*CHANGE_LOG\s*\n(.*?)\n-->', agent_output, re.DOTALL)
        if not match:
            return {**_null, "failure_reason": "missing_block"}

        raw = match.group(1).strip()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return {**_null, "failure_reason": "invalid_json"}

        # Check that at least one of url/field/after has a usable value
        url = payload.get("url") or None
        field = payload.get("field") or None
        after = payload.get("after") or None
        if url is None and field is None and after is None:
            return {**_null, "failure_reason": "missing_required_fields"}

        # field present but empty string
        if field is not None and field.strip() == "":
            return {**_null, "failure_reason": "field_mismatch"}

        return {
            "extraction_status": "ok",
            "failure_reason": None,
            "url": url,
            "field": field,
            "before": payload.get("before") or None,
            "after": after,
            "webflow_item_id": payload.get("webflow_item_id") or None,
            "webflow_status": payload.get("webflow_status") or None,
        }
    except Exception:
        return {**_null, "failure_reason": "missing_block"}


def _build_change_id(task_id: int, execution_type: str, url: str | None) -> str:
    """Build a deterministic, idempotent change ID for a task execution.

    Format: "{task_id}-{execution_type}-{url_slug}"
    Slug is derived from the URL path, lowercased, non-alphanumeric replaced with hyphens,
    truncated to 40 chars. Falls back to "unknown" when url is None.
    """
    raw = (url or "unknown").lower()
    # Strip scheme and domain, keep path
    raw = raw.split("//")[-1]  # remove https://
    slug = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")[:40]
    return f"{task_id}-{execution_type}-{slug}"


def _write_change_log_entry(task, agent_output: str, user_comments: list) -> None:
    """Parse agent output for a CHANGE_LOG block and persist a change entry.

    - If execution_type is not in CMS_CHANGE_FIELD_MAP: no-op.
    - Parses the structured block from agent_output deterministically.
    - If block is absent/invalid: writes entry with extraction_status="failed" and failure_reason.
    - Upserts by change ID: on re-execution, increments attempts and preserves review state.
    - Writes atomically and refreshes markdown views.

    Args:
        task: TaskModel instance (id, title, execution_type)
        agent_output: Full string output from the agent
        user_comments: List of CommentModel instances (author, body)
    """
    if task.execution_type not in CMS_CHANGE_FIELD_MAP:
        return

    payload = _parse_change_log_block(agent_output)
    change_id = _build_change_id(task.id, task.execution_type, payload.get("url"))

    data = _load_seo_changes()
    existing_index = {e["id"]: i for i, e in enumerate(data["entries"])}

    entry = {
        "id": change_id,
        "task_id": task.id,
        "task_title": task.title,
        "execution_type": task.execution_type,
        "change_type": CMS_CHANGE_FIELD_MAP[task.execution_type],
        "url": payload.get("url"),
        "webflow_item_id": payload.get("webflow_item_id"),
        "before": payload.get("before"),
        "after": payload.get("after"),
        "extraction_status": payload["extraction_status"],
        "failure_reason": payload.get("failure_reason"),
        "is_backfilled": False,
        "user_notes": [
            {"author": c.author, "body": c.body}
            for c in user_comments
            if c.author == "user"
        ],
        "logged_at": _utcnow_iso() + "Z",
        "attempts": 1,
        "status": "pending-review",
        "review_notes": None,
        "reviewed_at": None,
        "learning_ids": [],
    }

    if change_id in existing_index:
        old = data["entries"][existing_index[change_id]]
        entry["attempts"] = old.get("attempts", 1) + 1
        entry["status"] = old.get("status", "pending-review")
        entry["review_notes"] = old.get("review_notes")
        entry["reviewed_at"] = old.get("reviewed_at")
        entry["learning_ids"] = old.get("learning_ids", [])
        entry["logged_at"] = old.get("logged_at", entry["logged_at"])
        data["entries"][existing_index[change_id]] = entry
    else:
        data["entries"].append(entry)

    _atomic_json_write(SEO_CHANGES_PATH, data)
    _refresh_markdown_views()


def _render_changes_markdown(entries: list) -> str:
    """Render seo-changes.json entries to human/agent-readable markdown.

    Groups entries by status. Each entry shows key fields in a compact block.
    Returns a string suitable for writing to .claude/seo-changes-log.md.
    """
    if not entries:
        return "# SEO Changes Log\n\n_No entries yet._\n"

    # Group by status
    groups: dict[str, list] = {}
    for e in entries:
        groups.setdefault(e.get("status", "unknown"), []).append(e)

    # Order: pending first, then reviewed-*, then others
    status_order = [
        "pending-review",
        "reviewed-positive",
        "reviewed-negative",
        "reviewed-neutral",
        "reviewed-inconclusive",
    ]
    lines = ["# SEO Changes Log\n"]
    for status in status_order + [s for s in groups if s not in status_order]:
        if status not in groups:
            continue
        lines.append(f"\n## {status} ({len(groups[status])})\n")
        for e in sorted(groups[status], key=lambda x: x.get("logged_at", "")):
            lines.append(f"### {e.get('logged_at', '')[:10]} — {e.get('task_title', 'Untitled')}")
            lines.append(f"- **ID:** `{e.get('id', '')}`")
            lines.append(f"- **Page:** {e.get('url', 'unknown')}")
            lines.append(f"- **Change type:** {e.get('change_type', '')}")
            lines.append(f"- **Before:** {e.get('before', 'null')}")
            lines.append(f"- **After:** {e.get('after', 'null')}")
            lines.append(f"- **Extraction:** {e.get('extraction_status', '')} / {e.get('failure_reason', 'n/a')}")
            if e.get("review_notes"):
                lines.append(f"- **Review notes:** {e['review_notes']}")
            if e.get("user_notes"):
                notes = "; ".join(n["body"] for n in e["user_notes"])
                lines.append(f"- **User notes:** {notes}")
            lines.append("")

    return "\n".join(lines)


def _render_learnings_markdown(learnings: dict) -> str:
    """Render seo-learnings.json to human/agent-readable markdown.

    Sorted by confidence (high → medium → low). Returns a string suitable
    for writing to .claude/seo-learnings.md.
    """
    if not learnings:
        return "# SEO Learnings\n\n_No learnings extracted yet._\n"

    conf_order = {"high": 0, "medium": 1, "low": 2}
    sorted_items = sorted(
        learnings.values(),
        key=lambda x: (conf_order.get(x.get("confidence", "low"), 2), x.get("id", ""))
    )

    lines = ["# SEO Learnings\n",
             "_Principles extracted from measured ranking changes on this site._\n"]
    for l in sorted_items:
        lines.append(f"## {l.get('id', 'unknown')} [{l.get('confidence', '?')} confidence, {l.get('hit_count', 0)} hits]")
        lines.append(f"- **Discovered:** {l.get('discovered', '')}")
        lines.append(f"- **Principle:** {l.get('principle', '')}")
        lines.append(f"- **Evidence:** {l.get('evidence', '')}")
        lines.append(f"- **Applicable when:** {l.get('applicable_when', '')}")
        lines.append(f"- **Not applicable when:** {l.get('not_applicable_when', '')}")
        lines.append("")

    return "\n".join(lines)


def _refresh_markdown_views() -> None:
    """Regenerate .claude/seo-changes-log.md and .claude/seo-learnings.md from JSON sources.

    Called after every JSON write to keep markdown views in sync.
    """
    changes = _load_seo_changes()
    learnings = _load_seo_learnings()

    changes_md = _render_changes_markdown(changes["entries"])
    learnings_md = _render_learnings_markdown(learnings["learnings"])

    SEO_CHANGES_MD_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Use plain write for markdown (not JSON, so _atomic_json_write not applicable)
    _md_write(SEO_CHANGES_MD_PATH, changes_md)
    _md_write(SEO_LEARNINGS_MD_PATH, learnings_md)


def _md_write(path: Path, content: str) -> None:
    """Write markdown atomically via temp file + os.replace()."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def _change_log_block_instruction(execution_type: str) -> str:
    """Return the per-type CHANGE_LOG block instruction to append to agent prompts.

    Returns "" for non-CMS types. Each type specifies exactly which fields to
    populate and where to find them in the workflow output — no ambiguity.
    """
    if execution_type not in CMS_CHANGE_FIELD_MAP:
        return ""

    field = CMS_CHANGE_FIELD_MAP[execution_type]

    per_type_guidance = {
        "rewrite_title": (
            "Extract url and webflow_item_id from Step 4 (Webflow lookup). "
            "Set before = current title from get_cms_item (or null if static page). "
            "Set after = the final title you wrote in Step 3."
        ),
        "rewrite_meta_desc": (
            "Extract url and webflow_item_id from Step 4 (Webflow lookup). "
            "Set before = current seo-desc from get_cms_item (or null if static). "
            "Set after = the final meta description from Step 3."
        ),
        "rewrite_h1": (
            "Extract url and webflow_item_id from Step 5 (Webflow lookup). "
            "Set before = old H1 from Step 1 (WebFetch). "
            "Set after = the final H1 from Step 4."
        ),
        "blog_write": (
            "Set url = the live URL of the newly created post (slug-based). "
            "Set before = null (new post). "
            "Set after = the SEO title of the new post."
        ),
        "rewrite_blog_content": (
            "Extract url and webflow_item_id from Step 5 (Webflow lookup). "
            "Set before = old SEO title or slug from Step 1. "
            "Set after = new SEO title if changed, or 'content updated'."
        ),
        "webflow_publish": (
            "Set url = the live URL of the published item. "
            "Set before = null. Set after = 'published'."
        ),
        "internal_links": (
            "Set url = comma-separated list of all URLs updated. "
            "Set before = null. "
            "Set after = 'N links added: [anchor text → target URL, ...]'."
        ),
    }

    guidance = per_type_guidance.get(execution_type, "Populate all fields from your work above.")

    return f"""

---
**Required: append this block as the very last content in your response.**
{guidance}

<!-- CHANGE_LOG
{{
  "url": "<page URL>",
  "field": "{field}",
  "before": "<previous value, or null>",
  "after": "<new value>",
  "webflow_item_id": "<Webflow item ID, or null>",
  "webflow_status": "<published|updated|manual-only>"
}}
-->"""



def _utcnow_iso() -> str:
    """Naive UTC ISO timestamp (matches legacy datetime.utcnow output)."""
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
