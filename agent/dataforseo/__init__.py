"""
DataForSEO integration for the SEO Agent.

This is a batch extraction pipeline, not an agent-facing MCP tool set. Scripts
drive these classes to pull live SERP, keyword, backlink, and AI-visibility data
from the DataForSEO API; every call is logged under `dataforseo/raw/` and rolled
up into `dataforseo/compiled/`. The agent reads the compiled output rather than
guessing keyword volumes or rankings.

Deliberately NOT re-exported from `agent/__init__.py`: importing the agent must
not require the `requests`/`python-dotenv` dependencies this pipeline needs.

Credentials come from DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD.
"""

from agent.dataforseo.client import DataForSEOClient, DataForSEOError, TaskNotReadyError
from agent.dataforseo.serp.google_organic import GoogleOrganicSERP
from agent.dataforseo.keywords_data.google_ads import GoogleAdsKeywords
from agent.dataforseo.keywords_data.bing import BingKeywords
from agent.dataforseo.keywords_data.google_trends import GoogleTrends
from agent.dataforseo.dataforseo_labs.google import GoogleLabs
from agent.dataforseo.backlinks.backlinks import BacklinksAPI
from agent.dataforseo.ai_optimization.llm_mentions import LLMMentions
from agent.dataforseo.ai_optimization.ai_keyword_data import AIKeywordData
from agent.dataforseo.ai_optimization.llm_responses.chat_gpt import ChatGPTResponses
from agent.dataforseo.ai_optimization.llm_responses.claude import ClaudeResponses
from agent.dataforseo.ai_optimization.llm_responses.gemini import GeminiResponses
from agent.dataforseo.ai_optimization.llm_responses.perplexity import PerplexityResponses
from agent.dataforseo.ai_optimization.llm_scraper.chat_gpt import ChatGPTScraper
from agent.dataforseo.ai_optimization.llm_scraper.gemini import GeminiScraper

__all__ = [
    "DataForSEOClient",
    "DataForSEOError",
    "TaskNotReadyError",
    "GoogleOrganicSERP",
    "GoogleAdsKeywords",
    "BingKeywords",
    "GoogleTrends",
    "GoogleLabs",
    "BacklinksAPI",
    "LLMMentions",
    "AIKeywordData",
    "ChatGPTResponses",
    "ClaudeResponses",
    "GeminiResponses",
    "PerplexityResponses",
    "ChatGPTScraper",
    "GeminiScraper",
]
