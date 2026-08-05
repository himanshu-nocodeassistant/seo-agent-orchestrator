#!/usr/bin/env python3
"""
Keywords Data (Bing) pipeline.

Wraps agent.dataforseo.keywords_data.bing.BingKeywords. Subcommands:
search_volume/_live, keywords_for_site/_live, keywords_for_keywords/_live,
keyword_performance/_live.

Usage:
    python scripts/pipelines/keywords_bing.py --help
    python scripts/pipelines/keywords_bing.py search_volume_live --task '{"keywords": ["no-code agency"], "location_code": 2840}'

Requires DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD in .env or environment.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from agent.dataforseo.keywords_data.bing import BingKeywords
from scripts.pipelines._cli import run_pipeline

if __name__ == "__main__":
    run_pipeline(BingKeywords, "keywords-bing")
