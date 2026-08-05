#!/usr/bin/env python3
"""One-time purge of not-ready task_get poll snapshots from logs/.

Files where status_code is 40601 ("Task In Queue") or 40602 ("Task In Progress")
are transient polling snapshots. Every completed task supersedes them with a
final "Ok." (20000) file in the same folder. These intermediate files have no
informational value once the task completes.

Safe to re-run: only deletes files whose status_code is a known not-ready code.

Usage:
    python scripts/purge_stale_poll_logs.py
    python scripts/purge_stale_poll_logs.py --dry-run
"""
import argparse
import json
from pathlib import Path

LOGS_DIR = Path(__file__).parent.parent / "dataforseo" / "raw"
NOT_READY_STATUS_CODES = {40601, 40602}


def main(dry_run: bool = False) -> None:
    deleted = 0
    errors = 0

    for f in sorted(LOGS_DIR.rglob("*task_get*.json")):
        try:
            content = json.loads(f.read_text(encoding="utf-8"))
            if content.get("status_code") in NOT_READY_STATUS_CODES:
                rel = f.relative_to(LOGS_DIR)
                if dry_run:
                    print(f"[dry-run] would delete: {rel}")
                else:
                    f.unlink()
                    print(f"Deleted: {rel}")
                deleted += 1
        except (json.JSONDecodeError, OSError) as e:
            print(f"Error reading {f}: {e}")
            errors += 1

    label = "Would delete" if dry_run else "Deleted"
    print(f"\nDone. {label} {deleted} stale file(s). Errors: {errors}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Print files that would be deleted without removing them")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
