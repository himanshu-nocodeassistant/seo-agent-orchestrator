#!/usr/bin/env python3
"""
Keywords Data (Google Ads) pipeline.

Wraps agent.dataforseo.keywords_data.google_ads.GoogleAdsKeywords. Subcommands:
search_volume/search_volume_live, keywords_for_site/_live,
keywords_for_keywords/_live, ad_traffic_by_keywords/_live. The non-`_live`
variants use the cheaper Standard Queue (submit + poll); `_live` variants
return instantly at a higher per-call cost.

Usage:
    python scripts/pipelines/keywords_google_ads.py --help
    python scripts/pipelines/keywords_google_ads.py search_volume_live --task '{"keywords": ["no-code agency", "bubble developer"], "location_code": 2840}'

Requires DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD in .env or environment.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from agent.dataforseo.keywords_data.google_ads import GoogleAdsKeywords
from scripts.pipelines._cli import run_pipeline

if __name__ == "__main__":
    run_pipeline(GoogleAdsKeywords, "keywords-google-ads")
