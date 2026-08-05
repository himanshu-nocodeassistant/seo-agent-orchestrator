#!/usr/bin/env python3
"""
Refresh DataForSEO measurements on a schedule.

Reads ``dataforseo/refresh.tasks.json`` and runs:
  - SERP Google Organic standard-queue searches (GoogleOrganicSERP.search)
  - Google Ads keyword volumes (GoogleAdsKeywords.search_volume)

Rollups are written to ``dataforseo/compiled/`` with the same
``<pipeline>-<method>-<date>.json`` naming that the agent's measurement
memory layer reads (agent/dataforseo/memory.py). API cost is printed at the
end, exactly like the one-off pipeline scripts.

Schedule with cron/launchd, e.g. daily at 2am:

    0 2 * * * cd /path/to/seo-bot-orchestrator && \\
        .venv/bin/python scripts/pipelines/refresh.py >> dataforseo/refresh.log 2>&1

Requires DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD in .env or the environment.
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from agent.dataforseo.keywords_data.google_ads import GoogleAdsKeywords
from agent.dataforseo.serp.google_organic import GoogleOrganicSERP


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
COMPILED_DIR = PROJECT_ROOT / "dataforseo" / "compiled"
DEFAULT_CONFIG = PROJECT_ROOT / "dataforseo" / "refresh.tasks.json"


def _write_rollup(name: str, payload) -> Path:
    """Write a rollup using the pipeline naming the measurement layer reads."""
    path = COMPILED_DIR / f"{name}-{date.today()}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG),
        help="Path to refresh.tasks.json (default: dataforseo/refresh.tasks.json)",
    )
    args = parser.parse_args()

    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    total_cost = 0.0

    serp_tasks = config.get("serp", [])
    if serp_tasks:
        client = GoogleOrganicSERP()
        results = client.search(tasks=serp_tasks)
        path = _write_rollup("serp-google-organic-search", results)
        print(f"Wrote {len(results)} SERP result(s) to {path}")
        total_cost += client.total_cost

    keyword_tasks = config.get("keyword_volume", [])
    if keyword_tasks:
        client = GoogleAdsKeywords()
        results = client.search_volume(tasks=keyword_tasks)
        path = _write_rollup("keywords-google-ads-search-volume", results)
        print(f"Wrote {len(results)} keyword-volume result(s) to {path}")
        total_cost += client.total_cost

    print(f"DataForSEO API cost this run: ${total_cost:.4f}")


if __name__ == "__main__":
    main()
