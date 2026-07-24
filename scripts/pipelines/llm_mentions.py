#!/usr/bin/env python3
"""
AI Optimization: LLM Mentions pipeline.

Wraps agent.dataforseo.ai_optimization.llm_mentions.LLMMentions. Finds
mentions of a domain/keyword in AI-generated answers (Google AI Overviews,
ChatGPT, etc.). Subcommands: locations_and_languages (free), available_filters
(free), search_live (~$0.10/call flat, observed), aggregated_metrics_live,
cross_aggregated_metrics_live, top_domains_live, top_pages_live.

Notes learned from prior use (see the source project's cost ledger for
full detail): exactly one task per search_live call; `search_scope` takes
ONE value, `["any"]` disables filtering; `match_type: "partial_match"` for
phrase semantics ("word_match" matches words independently — noisy); for
domain targets always set `include_subdomains: true` or citations under
`www.` are missed; `items_list_limit` max 10 on top_domains/top_pages.

Usage:
    python scripts/pipelines/llm_mentions.py --help
    python scripts/pipelines/llm_mentions.py search_live --task '{"target": [{"keyword": "no-code agency", "search_scope": ["question"], "match_type": "partial_match"}], "platform": "google"}'

Requires DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD in .env or environment.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from agent.dataforseo.ai_optimization.llm_mentions import LLMMentions
from scripts.pipelines._cli import run_pipeline

if __name__ == "__main__":
    run_pipeline(LLMMentions, "llm-mentions")
