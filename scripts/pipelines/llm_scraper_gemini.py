#!/usr/bin/env python3
"""
AI Optimization: Gemini LLM Scraper pipeline.

Wraps agent.dataforseo.ai_optimization.llm_scraper.gemini.GeminiScraper.
Scrapes the Gemini web UI directly (distinct from llm_responses, which
uses the API) — captures rendered HTML/advanced output as an end user
would see it. Subcommands: live_advanced, live_html, task_post,
tasks_ready (free), task_get_advanced, task_get_html, locations (free),
languages (free).

Usage:
    python scripts/pipelines/llm_scraper_gemini.py --help
    python scripts/pipelines/llm_scraper_gemini.py live_advanced --task '{"user_prompt": "What is the best no-code agency?"}'

Requires DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD in .env or environment.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from agent.dataforseo.ai_optimization.llm_scraper.gemini import GeminiScraper
from scripts.pipelines._cli import run_pipeline

if __name__ == "__main__":
    run_pipeline(GeminiScraper, "llm-scraper-gemini")
