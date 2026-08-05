#!/usr/bin/env python3
"""
SERP (Google organic) pipeline.

Wraps agent.dataforseo.serp.google_organic.GoogleOrganicSERP. Subcommands:
task_post, task_get, search (Standard Queue, ~$0.0006/SERP — submit + poll
in one call), live_advanced (instant, ~$0.002/SERP).

Usage:
    python scripts/pipelines/serp_google_organic.py --help
    python scripts/pipelines/serp_google_organic.py search --task '{"keyword": "no-code agency", "location_code": 2840, "language_code": "en"}'
    python scripts/pipelines/serp_google_organic.py search --tasks-file keywords.json --tag my-campaign

Requires DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD in .env or environment.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from agent.dataforseo.serp.google_organic import GoogleOrganicSERP
from scripts.pipelines._cli import run_pipeline

if __name__ == "__main__":
    run_pipeline(GoogleOrganicSERP, "serp-google-organic")
