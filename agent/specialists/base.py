"""
Base classes for specialist agents in the Multi-Channel Agent Orchestrator.

Defines the inter-agent handoff contract (AgentContext / AgentResult) and the
BaseSpecialistAgent abstract class that all specialists extend.

Phase 2: Integrates retry logic for failed tool calls
Phase 6: Enforces tool whitelisting per specialist
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from claude_agent_sdk import query, ClaudeAgentOptions
from claude_agent_sdk.types import AssistantMessage, TextBlock, ResultMessage
from claude_agent_sdk._errors import MessageParseError

# Ensure SDK compatibility patch is applied before any SDK usage
from agent import sdk_compat  # noqa: F401
from agent.retry import RetryConfig, RetryMetrics
from agent.specialists.config import (
    get_allowed_tools_for_specialist,
    validate_tool_access,
)

logger = logging.getLogger(__name__)


@dataclass
class AgentContext:
    """
    Inter-agent handoff contract.

    Passed between specialists in a pipeline so each agent has full context
    about the task, its stage in the pipeline, and all prior outputs.

    Attributes:
        task_id: Database ID of the Kanban task.
        task_title: Human-readable task title.
        task_description: Optional extended task description.
        execution_type: Task execution type (e.g. "blog_write", "research").
        pipeline_step: 0-indexed current stage in the pipeline.
        pipeline_total: Total number of stages in the pipeline.
        prior_outputs: Outputs from all preceding pipeline stages.
            Each entry: {"agent": str, "output": str, "structured": dict}.
        user_notes: User comments on the task (author="user").
        site_url: Target site URL from env TARGET_SITE_URL.
        site_name: Target site name from env TARGET_SITE_NAME.
    """

    task_id: int
    task_title: str
    execution_type: str
    pipeline_step: int
    pipeline_total: int
    task_description: Optional[str] = None
    prior_outputs: list = field(default_factory=list)
    user_notes: list = field(default_factory=list)
    site_url: str = "https://example.com"
    site_name: str = "My Site"


@dataclass
class AgentResult:
    """
    Output from a single specialist agent.

    Attributes:
        agent_name: Name of the specialist that produced this result.
        output: Prose/markdown output for task notes and comments.
        structured: Optional machine-readable payload (e.g. parsed research data).
        retry_count: Number of retries performed during execution.
        metrics: Optional metrics from retry operations.
    """

    agent_name: str
    output: str
    structured: dict = field(default_factory=dict)
    retry_count: int = 0
    metrics: RetryMetrics | None = None


class BaseSpecialistAgent(ABC):
    """
    Abstract base class for all specialist agents.

    Subclasses must define:
        name: str — class-level display name for logging and comments.
        _build_options(self) -> ClaudeAgentOptions — SDK options for this specialist.
        _build_prompt(self, ctx: AgentContext) -> str — prompt for this specialist.

    The run() method streams query() and returns an AgentResult.

    Phase 2: Integrates retry logic with exponential backoff
    Phase 6: Enforces tool whitelisting per specialist
    """

    name: str = "BaseSpecialist"

    def __init__(self, base_config):
        """
        Initialize the specialist with an AgentConfig.

        Args:
            base_config: AgentConfig instance (from agent.config).
        """
        self.base_config = base_config

    @abstractmethod
    def _build_options(self) -> ClaudeAgentOptions:
        """Build ClaudeAgentOptions with this specialist's tool whitelist and system prompt."""
        ...

    @abstractmethod
    def _build_prompt(self, ctx: AgentContext) -> str:
        """Build the full prompt for this specialist given the pipeline context."""
        ...

    def _enforce_tool_whitelist(self, options: ClaudeAgentOptions) -> ClaudeAgentOptions:
        """
        Enforce tool whitelisting for this specialist (Phase 6).

        Validates that the agent's allowed tools match the specialist's strict whitelist.

        Args:
            options: The ClaudeAgentOptions built by the specialist.

        Returns:
            Updated options with enforced whitelist. Logs warning if discrepancies found.
        """
        allowed_tools = options.allowed_tools or []
        is_valid, disallowed = validate_tool_access(self.name, allowed_tools)

        if not is_valid:
            logger.warning(
                "%s: requested disallowed tools %s. Using specialist whitelist only.",
                self.name,
                disallowed,
            )
            # Fall back to strict whitelist
            strict_tools = get_allowed_tools_for_specialist(self.name)
            # But always include Skill tool if requested (needed for skill loading)
            if "Skill" in allowed_tools:
                strict_tools = strict_tools + ["Skill"]
            options.allowed_tools = list(set(strict_tools))

        return options

    async def run(self, ctx: AgentContext) -> AgentResult:
        """
        Execute the specialist against the given context.

        Streams query() and collects all text output into an AgentResult.
        Integrates retry logic for failed queries (Phase 2).

        Args:
            ctx: AgentContext with task details, prior outputs, and pipeline metadata.

        Returns:
            AgentResult with the specialist's output, agent name, and retry metrics.

        Raises:
            RuntimeError: If the SDK raises an unrecoverable error after all retries.
        """
        prompt = self._build_prompt(ctx)
        options = self._build_options()

        # Phase 6: Enforce tool whitelisting
        options = self._enforce_tool_whitelist(options)

        # Phase 2: Get retry configuration from base_config
        retry_config: RetryConfig = getattr(self.base_config, "retry_config", RetryConfig())

        result_text = ""
        retry_count = 0
        last_error: Exception | None = None

        # Retry loop with exponential backoff
        for attempt in range(1, retry_config.max_attempts + 1):
            try:
                async for message in query(prompt=prompt, options=options):
                    if message is None:
                        continue
                    if isinstance(message, AssistantMessage):
                        for block in message.content:
                            if isinstance(block, TextBlock):
                                result_text += block.text
                    elif isinstance(message, ResultMessage):
                        if message.result:
                            result_text += message.result

                # Success on this attempt
                if attempt > 1:
                    logger.info("%s: succeeded on retry attempt %d", self.name, attempt)
                break

            except MessageParseError as e:
                last_error = e
                retry_count = attempt - 1
                logger.warning("%s: SDK message parse error on attempt %d: %s", self.name, attempt, e)

                if attempt < retry_config.max_attempts:
                    delay = min(
                        retry_config.initial_delay_ms * (retry_config.backoff_multiplier ** (attempt - 1)),
                        retry_config.max_delay_ms,
                    ) / 1000.0
                    import asyncio
                    await asyncio.sleep(delay)
                    logger.info("%s: retrying in %.1f seconds...", self.name, delay)
                else:
                    raise RuntimeError(f"{self.name}: failed after {attempt} attempts") from e

            except Exception as e:
                last_error = e
                retry_count = attempt - 1
                logger.warning("%s: exception on attempt %d: %s", self.name, attempt, e)

                if attempt < retry_config.max_attempts:
                    delay = min(
                        retry_config.initial_delay_ms * (retry_config.backoff_multiplier ** (attempt - 1)),
                        retry_config.max_delay_ms,
                    ) / 1000.0
                    import asyncio
                    await asyncio.sleep(delay)
                    logger.info("%s: retrying in %.1f seconds...", self.name, delay)
                else:
                    raise RuntimeError(f"{self.name}: failed after {attempt} attempts") from e

        metrics = RetryMetrics(
            total_attempts=max(1, retry_count + 1),
            retry_count=retry_count,
            success=True,
        )

        return AgentResult(
            agent_name=self.name,
            output=result_text,
            structured={},
            retry_count=retry_count,
            metrics=metrics,
        )
