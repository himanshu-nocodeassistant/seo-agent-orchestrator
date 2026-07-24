#!/usr/bin/env python3
"""
DataForSEO Labs (Google) pipeline.

Wraps agent.dataforseo.dataforseo_labs.google.GoogleLabs. Subcommands:
related_keywords_live, keyword_suggestions_live, keyword_ideas_live,
ranked_keywords_live, competitors_domain_live, domain_intersection_live,
domain_rank_overview_live.

Usage:
    python scripts/pipelines/labs_google.py --help
    python scripts/pipelines/labs_google.py ranked_keywords_live --task '{"target": "example.com", "location_code": 2840, "language_code": "en", "limit": 500}'

Requires DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD in .env or environment.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from agent.dataforseo.dataforseo_labs.google import GoogleLabs
from scripts.pipelines._cli import run_pipeline

if __name__ == "__main__":
    run_pipeline(GoogleLabs, "labs-google")
