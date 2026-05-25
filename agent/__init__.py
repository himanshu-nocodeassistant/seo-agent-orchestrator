"""Multi-Channel SEO Agent Orchestrator using Claude Agent SDK."""

from .config import AgentConfig, RetryConfig
from .seo_agent import SEOAgent
from .orchestrator import OrchestratorAgent, SupervisorLogger
from .retry import RetryConfig, RetryMetrics, with_retry
from .feedback_loop import FeedbackLoopOrchestrator, ChangeEntry
from .programmatic import (
    TemplatedPageGenerator,
    BulkPageProcessor,
    PageTemplate,
    PageData,
    BulkJobProgress,
)
from .specialists import (
    AgentContext,
    AgentResult,
    ResearchAgent,
    ContentAgent,
    AnalyticsAgent,
    TechnicalSEOAgent,
)

__all__ = [
    # Core
    "SEOAgent",
    "AgentConfig",
    "RetryConfig",
    # Orchestration
    "OrchestratorAgent",
    "SupervisorLogger",
    "AgentContext",
    "AgentResult",
    # Retry
    "RetryMetrics",
    "with_retry",
    # Feedback Loop
    "FeedbackLoopOrchestrator",
    "ChangeEntry",
    # Programmatic SEO
    "TemplatedPageGenerator",
    "BulkPageProcessor",
    "PageTemplate",
    "PageData",
    "BulkJobProgress",
    # Specialists
    "ResearchAgent",
    "ContentAgent",
    "AnalyticsAgent",
    "TechnicalSEOAgent",
]
