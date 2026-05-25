"""
Specialist agent package for the Multi-Channel Agent Orchestrator.

Each specialist has a distinct identity, system prompt, tool whitelist,
and MCP server subset. The OrchestratorAgent routes tasks to specialists
based on the AGENT_PIPELINE registry in agent/orchestrator.py.
"""

from .base import AgentContext, AgentResult, BaseSpecialistAgent
from .research_agent import ResearchAgent
from .content_agent import ContentAgent
from .analytics_agent import AnalyticsAgent
from .technical_seo_agent import TechnicalSEOAgent

__all__ = [
    "AgentContext",
    "AgentResult",
    "BaseSpecialistAgent",
    "ResearchAgent",
    "ContentAgent",
    "AnalyticsAgent",
    "TechnicalSEOAgent",
]
