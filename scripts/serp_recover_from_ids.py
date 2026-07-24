"""
Recover SERP Standard Queue results from previously-submitted task IDs.

Reads task IDs out of a task manifest (written automatically by
agent/dataforseo/client.py._write_manifest on every task_post call) or a
legacy task_post log file, and fetches results via task_get without
resubmitting (and re-billing) the tasks. Network retries, rate-limit
backoff, and timeout handling are all inherited from DataForSEOClient.

Usage:
    python scripts/serp_recover_from_ids.py \
        --manifest dataforseo/manifests/<timestamp>_serp_google_organic_task_post.json \
        --output dataforseo/compiled/serp-recovered.csv

    python scripts/serp_recover_from_ids.py \
        --task-post-log dataforseo/raw/<tag>/<keyword>/<location>/<timestamp>_task_post.json \
        --output dataforseo/compiled/serp-recovered.csv \
        --target-domain example.com

Requires DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD in .env or environment.
"""

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests

from agent.dataforseo.serp.google_organic import GoogleOrganicSERP
from agent.dataforseo.client import TaskNotReadyError, DataForSEOError

# The domain whose rankings we're tracking. Set SEO_TARGET_DOMAIN in .env or
# pass --target-domain. When unset, the is_target_domain column is always False.
DEFAULT_TARGET_DOMAIN = os.environ.get("SEO_TARGET_DOMAIN", "")

CSV_COLUMNS = [
    "task_id",
    "keyword",
    "location_code",
    "language_code",
    "tag",
    "rank_absolute",
    "title",
    "url",
    "domain",
    "is_target_domain",
    "serp_features",
]


def load_task_meta_from_manifest(manifest_path: Path) -> dict:
    """Returns {task_id: {keyword, location_code, language_code, tag}} from
    a logs/task_manifests/ file written by DataForSEOClient._write_manifest."""
    manifest = json.loads(manifest_path.read_text())
    meta = {}
    for entry in manifest["tasks"]:
        req = entry["request"]
        meta[entry["task_id"]] = {
            "keyword": req.get("keyword", ""),
            "location_code": req.get("location_code", ""),
            "language_code": req.get("language_code", ""),
            "tag": req.get("tag", ""),
        }
    return meta


def load_task_meta_from_log(log_path: Path) -> dict:
    """Returns {task_id: {keyword, location_code, language_code, tag}} from
    a legacy logs/serp/.../task_post/ entry (pre-manifest runs)."""
    entry = json.loads(log_path.read_text())
    payload = entry["payload"]
    result_tasks = entry["result"]["tasks"]

    meta = {}
    for req, resp in zip(payload, result_tasks):
        meta[resp["id"]] = {
            "keyword": req.get("keyword", ""),
            "location_code": req.get("location_code", ""),
            "language_code": req.get("language_code", ""),
            "tag": req.get("tag", ""),
        }
    return meta


def extract_rows(
    result: dict, task_id: str, meta: dict, target_domain: str = ""
) -> list[dict]:
    """Flatten one task's organic SERP items into CSV rows.

    Args:
        result: A single task's `result` object from DataForSEO.
        task_id: The DataForSEO task ID the result came from.
        meta: Keyword/location/language/tag recorded at submit time.
        target_domain: Domain to flag in the is_target_domain column. An empty
            string (the default) flags nothing, rather than matching every row.

    Returns:
        One row per organic item, or a single empty row if the SERP had none.
    """
    items = result.get("items", []) if result else []
    rows = []
    for item in items:
        if item.get("type") != "organic":
            continue
        domain = item.get("domain", "")
        rows.append({
            "task_id": task_id,
            "keyword": meta["keyword"],
            "location_code": meta["location_code"],
            "language_code": meta["language_code"],
            "tag": meta["tag"],
            "rank_absolute": item.get("rank_absolute", ""),
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "domain": domain,
            "is_target_domain": bool(target_domain) and target_domain in domain,
            "serp_features": "",
        })

    serp_features = sorted({
        item.get("type") for item in items
        if item.get("type") and item.get("type") != "organic"
    })
    features_str = "; ".join(serp_features) if serp_features else ""
    for row in rows:
        row["serp_features"] = features_str

    if not rows:
        rows.append({
            "task_id": task_id,
            "keyword": meta["keyword"],
            "location_code": meta["location_code"],
            "language_code": meta["language_code"],
            "tag": meta["tag"],
            "rank_absolute": "",
            "title": "",
            "url": "",
            "domain": "",
            "is_target_domain": False,
            "serp_features": features_str,
        })
    return rows


def main():
    parser = argparse.ArgumentParser(description="Recover already-submitted SERP task results by ID")
    parser.add_argument("--manifest", help="Path to a logs/task_manifests/ file (preferred)")
    parser.add_argument("--task-post-log", help="Path to a legacy task_post log JSON file")
    parser.add_argument("--output", required=True, help="Output CSV path (e.g. dataforseo/compiled/serp-batch3-results.csv)")
    parser.add_argument("--poll-interval", type=float, default=20, help="Seconds between retry passes")
    parser.add_argument("--max-wait", type=float, default=1800, help="Max total seconds to keep retrying")
    parser.add_argument(
        "--target-domain",
        default=DEFAULT_TARGET_DOMAIN,
        help="Domain to flag in the is_target_domain column "
             f"(default: $SEO_TARGET_DOMAIN{f' = {DEFAULT_TARGET_DOMAIN!r}' if DEFAULT_TARGET_DOMAIN else ', currently unset'})",
    )
    args = parser.parse_args()

    if not args.manifest and not args.task_post_log:
        sys.exit("Provide either --manifest or --task-post-log")

    if args.manifest:
        source_path = Path(args.manifest)
        meta = load_task_meta_from_manifest(source_path)
    else:
        source_path = Path(args.task_post_log)
        meta = load_task_meta_from_log(source_path)

    pending = set(meta.keys())
    print(f"Loaded {len(pending)} task IDs from {source_path}")

    client = GoogleOrganicSERP()
    all_rows = []
    elapsed = 0.0

    while pending and elapsed < args.max_wait:
        still_pending = set()
        for task_id in pending:
            try:
                result = client.task_get(task_id)
                all_rows.extend(
                    extract_rows(result, task_id, meta[task_id], args.target_domain)
                )
            except TaskNotReadyError:
                still_pending.add(task_id)
            except DataForSEOError as e:
                print(f"  ! {task_id} errored: {e}")
            except requests.exceptions.RequestException as e:
                # Client already retries transient network errors internally;
                # this is a fallback for when even those retries are exhausted.
                print(f"  ! {task_id} connection error after retries, will retry: {e}")
                still_pending.add(task_id)

        print(f"Resolved {len(pending) - len(still_pending)} more, {len(still_pending)} still pending")
        pending = still_pending
        if pending:
            time.sleep(args.poll_interval)
            elapsed += args.poll_interval

    if pending:
        print(f"Gave up on {len(pending)} tasks still not ready after {elapsed:.0f}s: {sorted(pending)}")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    all_rows.sort(key=lambda r: (r["tag"], r["keyword"], r.get("rank_absolute") or 9999))

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"\nWrote {len(all_rows)} rows to {output_path}")


if __name__ == "__main__":
    main()
