#!/usr/bin/env python3
"""Compile SERP results from logs/ into a single shareable JSON file.

Reads every completed task_get log (status_code 20000) from the logs/ tree
and packages them into one JSON array — no API calls, no re-billing.

When multiple runs exist for the same keyword+location, the most recent
result is used (latest file by timestamp in the filename).

Output structure (one object per keyword+location):
    {
      "keyword":         "weweb agency",
      "tag":             "tier1_service_weweb",
      "location_code":   2840,
      "language_code":   "en",
      "fetched_at":      "2026-07-01 13:02:03 +00:00",
      "logged_at":       "2026-07-01T14:23:08.496625+00:00",
      "se_results_count": 127,
      "serp_features":   ["organic", "video", "paid", "related_searches"],
      "items_count":     113,
      "items":           [ ...full organic item objects... ]
    }

Usage:
    python scripts/compile_serp_results.py
    python scripts/compile_serp_results.py --tag-prefix tier1_
    python scripts/compile_serp_results.py --output reports/serp-july.json
"""
import argparse
import json
from datetime import date
from pathlib import Path

LOGS_DIR = Path(__file__).parent.parent / "dataforseo" / "raw"
READY_STATUS = 20000


def collect_log_files(logs_dir: Path) -> list[Path]:
    """Return all task_get log files with a completed (20000) status."""
    files = []
    for f in logs_dir.rglob("*task_get*.json"):
        try:
            status = json.loads(f.read_text(encoding="utf-8")).get("status_code")
            if status == READY_STATUS:
                files.append(f)
        except (json.JSONDecodeError, OSError):
            pass
    return files


def latest_per_keyword_location(files: list[Path]) -> list[Path]:
    """Keep only the most recent file per (keyword, location_code) pair.

    Files are named <YYYY-MM-DD_HH-MM-SS>_task_get*.json so lexicographic
    sort on the filename gives chronological order.
    """
    groups: dict[tuple, Path] = {}
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            meta = data.get("data") or {}
            key = (meta.get("keyword"), meta.get("location_code"))
            if key[0] is None:
                continue
            existing = groups.get(key)
            if existing is None or f.name > existing.name:
                groups[key] = f
        except (json.JSONDecodeError, OSError):
            pass
    return list(groups.values())


def build_entry(f: Path) -> dict | None:
    """Convert a single log file into a compiled entry dict."""
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    meta = data.get("data") or {}
    results = data.get("result") or []
    if not results:
        return None

    serp = results[0]
    return {
        "keyword":          meta.get("keyword"),
        "tag":              meta.get("tag"),
        "location_code":    meta.get("location_code"),
        "language_code":    meta.get("language_code"),
        "fetched_at":       serp.get("datetime"),
        "logged_at":        data.get("timestamp"),
        "se_results_count": serp.get("se_results_count"),
        "serp_features":    serp.get("item_types") or [],
        "items_count":      serp.get("items_count"),
        "items":            serp.get("items") or [],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--logs-dir",
        default=str(LOGS_DIR),
        help=f"Root logs directory (default: {LOGS_DIR})",
    )
    parser.add_argument(
        "--tag-prefix",
        default=None,
        help="Only include entries whose tag starts with this prefix, e.g. 'tier1_'",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output JSON path (default: dataforseo/compiled/serp-compiled-YYYY-MM-DD.json)",
    )
    args = parser.parse_args()

    logs_dir = Path(args.logs_dir)
    output_path = Path(args.output) if args.output else Path(f"dataforseo/compiled/serp-compiled-{date.today()}.json")

    print(f"Scanning {logs_dir} ...")
    files = collect_log_files(logs_dir)
    print(f"Found {len(files)} completed task_get file(s)")

    files = latest_per_keyword_location(files)
    print(f"Deduplicated to {len(files)} unique keyword+location result(s)")

    entries = []
    for f in files:
        entry = build_entry(f)
        if entry is None:
            continue
        if args.tag_prefix and not (entry.get("tag") or "").startswith(args.tag_prefix):
            continue
        entries.append(entry)

    entries.sort(key=lambda e: (e.get("tag") or "", e.get("keyword") or "", e.get("location_code") or 0))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\nWrote {len(entries)} entries to {output_path}")


if __name__ == "__main__":
    main()
