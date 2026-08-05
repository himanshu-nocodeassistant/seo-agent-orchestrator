"""
Load DataForSEO compiled measurements into agent memory context.

The module itself only uses the stdlib (json/re/pathlib), and it is imported
lazily at prompt-build time inside ``fetch_semantic_context`` — never at
``import agent`` time. Note that importing it does trigger
``agent.dataforseo.__init__`` (which pulls the requests-based client), so the
measurement layer intentionally runs only on the server/CLI paths that already
have the full dependency stack.

Pipeline scripts write rollups to ``dataforseo/compiled/<pipeline>-<method>-<date>.json``;
this module picks the newest file per pipeline and renders a compact
``## Measured Data`` section for the agent prompt.
"""

import json
import re
from pathlib import Path


_COMPILED_DIR = "dataforseo/compiled"
_DATE_SUFFIX = re.compile(r"-\d{4}-\d{2}-\d{2}\.json$")

_MAX_ROWS_PER_PIPELINE = 20
_MAX_FIELDS_PER_ROW = 5


def _group_key(path: Path) -> str:
    """Pipeline identifier for a compiled file, e.g. serp-google-organic-search."""
    return _DATE_SUFFIX.sub("", path.name)


def _scalar_fields(item) -> dict:
    """Flatten a result row to a handful of scalar fields."""
    out = {}
    if not isinstance(item, dict):
        return out
    for key, value in item.items():
        if isinstance(value, (str, int, float, bool)) and value not in ("", None):
            out[key] = value
        if len(out) >= _MAX_FIELDS_PER_ROW:
            break
    return out


def _render_rows(rows: list) -> str:
    if not isinstance(rows, list):
        return ""
    lines = []
    for item in rows[:_MAX_ROWS_PER_PIPELINE]:
        fields = _scalar_fields(item)
        if fields:
            lines.append("  " + "; ".join(f"{k}={v}" for k, v in fields.items()))
    return "\n".join(lines)


def _extract_rows(data) -> list:
    """Dig a result list out of any compiled shape (list, result dict, tasks)."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("result", "items", "results", "rows"):
            value = data.get(key)
            if isinstance(value, list):
                return value
        tasks = data.get("tasks")
        if isinstance(tasks, list) and tasks:
            for key in ("result", "items", "results", "rows"):
                value = tasks[0].get(key)
                if isinstance(value, list):
                    return value
    return []


def load_measurement_snapshot(cwd: str, char_limit: int = 2000) -> str:
    """Render the newest compiled DataForSEO output per pipeline.

    Returns an empty string when no compiled files exist. Never raises: a
    corrupt file for one pipeline is skipped rather than losing the rest.
    """
    compiled_dir = Path(cwd) / _COMPILED_DIR
    if not compiled_dir.exists():
        return ""
    files = [p for p in compiled_dir.glob("*.json") if p.is_file()]
    if not files:
        return ""

    newest_by_group: dict[str, Path] = {}
    for path in files:
        group = _group_key(path)
        current = newest_by_group.get(group)
        if current is None or path.stat().st_mtime > current.stat().st_mtime:
            newest_by_group[group] = path

    budget = max(200, char_limit)
    sections = []
    for group in sorted(newest_by_group):
        path = newest_by_group[group]
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        rows = _extract_rows(data)
        rows_text = _render_rows(rows) if rows else ""
        block = f"### {group} ({path.name})"
        if rows_text:
            block += "\n" + rows_text
        # Always include at least one section, then respect the char budget.
        if sections and sum(len(s) for s in sections) + len(block) > budget:
            break
        sections.append(block)

    return "\n\n".join(sections) if sections else ""
