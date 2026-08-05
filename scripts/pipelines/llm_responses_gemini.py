#!/usr/bin/env python3
"""
AI Optimization: Gemini LLM Responses pipeline.

Wraps agent.dataforseo.ai_optimization.llm_responses.gemini.GeminiResponses.
Sends a prompt to Gemini and returns its response, optionally with web
search grounding. Subcommands: models (free), live, task_post, tasks_ready
(free), task_get.

Results carry real per-call token usage and spend (input_tokens,
output_tokens, money_spent) — this pipeline sums and prints those in
addition to the DataForSEO API call cost, since for LLM completions the
token spend is the number that actually matters.

Usage:
    python scripts/pipelines/llm_responses_gemini.py --help
    python scripts/pipelines/llm_responses_gemini.py live --task '{"user_prompt": "What is the best no-code agency?", "web_search": true}'

Requires DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD in .env or environment.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from agent.dataforseo.ai_optimization.llm_responses.gemini import GeminiResponses
from scripts.pipelines._cli import run_pipeline

if __name__ == "__main__":
    run_pipeline(GeminiResponses, "llm-responses-gemini")
