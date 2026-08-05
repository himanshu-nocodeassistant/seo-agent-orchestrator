#!/usr/bin/env python3
"""
AI Optimization: AI Keyword Data pipeline.

Wraps agent.dataforseo.ai_optimization.ai_keyword_data.AIKeywordData.
Estimated monthly search volume for keywords as asked of AI assistants
(distinct from traditional Google Ads volume). Subcommands:
locations_and_languages (free), keywords_search_volume_live (~$0.0007/keyword, observed).

Usage:
    python scripts/pipelines/ai_keyword_data.py --help
    python scripts/pipelines/ai_keyword_data.py keywords_search_volume_live --task '{"keywords": ["no-code agency", "bubble developer"], "location_code": 2840}'

Requires DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD in .env or environment.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from agent.dataforseo.ai_optimization.ai_keyword_data import AIKeywordData
from scripts.pipelines._cli import run_pipeline

if __name__ == "__main__":
    run_pipeline(AIKeywordData, "ai-keyword-data")
