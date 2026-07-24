#!/usr/bin/env python3
"""
Keywords Data (Google Trends) pipeline.

Wraps agent.dataforseo.keywords_data.google_trends.GoogleTrends. Subcommands:
explore (Standard Queue), explore_live.

Usage:
    python scripts/pipelines/keywords_google_trends.py --help
    python scripts/pipelines/keywords_google_trends.py explore_live --task '{"keywords": ["no-code agency"], "type": "web"}'

Requires DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD in .env or environment.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from agent.dataforseo.keywords_data.google_trends import GoogleTrends
from scripts.pipelines._cli import run_pipeline

if __name__ == "__main__":
    run_pipeline(GoogleTrends, "keywords-google-trends")
