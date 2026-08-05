#!/usr/bin/env python3
"""
AI Optimization: ChatGPT LLM Scraper pipeline.

Wraps agent.dataforseo.ai_optimization.llm_scraper.chat_gpt.ChatGPTScraper.
Scrapes the ChatGPT web UI directly (distinct from llm_responses, which
uses the API) — captures rendered HTML/advanced output as an end user
would see it. Subcommands: live_advanced, live_html, task_post,
tasks_ready (free), task_get_advanced, task_get_html, locations (free),
languages (free).

Usage:
    python scripts/pipelines/llm_scraper_chat_gpt.py --help
    python scripts/pipelines/llm_scraper_chat_gpt.py live_advanced --task '{"user_prompt": "What is the best no-code agency?"}'

Requires DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD in .env or environment.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from agent.dataforseo.ai_optimization.llm_scraper.chat_gpt import ChatGPTScraper
from scripts.pipelines._cli import run_pipeline

if __name__ == "__main__":
    run_pipeline(ChatGPTScraper, "llm-scraper-chat-gpt")
