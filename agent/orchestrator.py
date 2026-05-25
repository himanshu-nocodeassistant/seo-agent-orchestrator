"""
OrchestratorAgent — deterministic multi-specialist task router.

Routes tasks to specialist agents by execution_type using a static pipeline
registry. Unknown execution types fall back to the legacy SEOAgent.

Observable orchestration: posts progress comments to the Kanban UI via
the add_comment_fn callback passed at construction time.

Pipeline registry (deterministic, not AI-decided):

    execution_type          Pipeline
    --------------------    ----------------------------------------
    research                ResearchAgent
    rewrite_title           ResearchAgent → ContentAgent
    rewrite_meta_desc       ResearchAgent → ContentAgent
    rewrite_h1              ResearchAgent → ContentAgent
    blog_write              ResearchAgent → ContentAgent
    rewrite_blog_content    ResearchAgent → ContentAgent
    update_schema           TechnicalSEOAgent
    alt_text                TechnicalSEOAgent
    internal_links          ResearchAgent → TechnicalSEOAgent
    seo_impact_review       AnalyticsAgent
    (unknown)               legacy SEOAgent fallback
"""

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from .config import AgentConfig
from .feedback_loop import FeedbackLoopOrchestrator
from .specialists.base import AgentContext, AgentResult
from .specialists.research_agent import ResearchAgent
from .specialists.content_agent import ContentAgent
from .specialists.analytics_agent import AnalyticsAgent
from .specialists.technical_seo_agent import TechnicalSEOAgent
from .validators import (
    AnalyticsValidator,
    ContentValidator,
    ResearchValidator,
    TechnicalSEOValidator,
)

logger = logging.getLogger(__name__)

# Memory files
MEMORY_DIR = Path(__file__).parent.parent / "memory"
SUPERVISOR_LOG_FILE = MEMORY_DIR / "supervisor.log"


class SupervisorLogger:
    """
    Structured logging for orchestrator supervisor.

    Logs pipeline execution with correlation IDs, timing, and metrics.
    Format: {timestamp} | {task_id} | {execution_type} | {step} | {agent} | {status} | {duration_ms}
    """

    def __init__(self, log_file: Path = SUPERVISOR_LOG_FILE):
        self.log_file = log_file
        self._ensure_log_dir()

    def _ensure_log_dir(self):
        """Ensure log directory exists."""
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

    def _write_log(self, entry: dict) -> None:
        """Write a log entry as JSON line."""
        with open(self.log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def log_pipeline_start(
        self,
        task_id: int,
        execution_type: str,
        pipeline: list[str],
        correlation_id: str,
    ) -> None:
        """Log the start of a pipeline execution."""
        self._write_log({
            "timestamp": datetime.now().isoformat(),
            "correlation_id": correlation_id,
            "task_id": task_id,
            "execution_type": execution_type,
            "pipeline": pipeline,
            "event": "pipeline_start",
            "step": 0,
            "agent": "orchestrator",
            "status": "started",
            "duration_ms": 0,
        })

    def log_step_start(
        self,
        task_id: int,
        execution_type: str,
        step: int,
        agent: str,
        correlation_id: str,
        input_size: int = 0,
    ) -> None:
        """Log the start of an agent step."""
        self._write_log({
            "timestamp": datetime.now().isoformat(),
            "correlation_id": correlation_id,
            "task_id": task_id,
            "execution_type": execution_type,
            "event": "step_start",
            "step": step,
            "agent": agent,
            "status": "running",
            "duration_ms": 0,
            "input_size": input_size,
        })

    def log_step_complete(
        self,
        task_id: int,
        execution_type: str,
        step: int,
        agent: str,
        correlation_id: str,
        duration_ms: int,
        output_size: int,
        success: bool,
        retry_count: int = 0,
        validation_score: Optional[float] = None,
        validation_passed: Optional[bool] = None,
    ) -> None:
        """Log the completion of an agent step."""
        status = "success" if success else "failed"
        entry = {
            "timestamp": datetime.now().isoformat(),
            "correlation_id": correlation_id,
            "task_id": task_id,
            "execution_type": execution_type,
            "event": "step_complete",
            "step": step,
            "agent": agent,
            "status": status,
            "duration_ms": duration_ms,
            "output_size": output_size,
            "retry_count": retry_count,
        }
        if validation_score is not None:
            entry["validation_score"] = validation_score
            entry["validation_passed"] = validation_passed
        self._write_log(entry)

    def log_pipeline_complete(
        self,
        task_id: int,
        execution_type: str,
        correlation_id: str,
        duration_ms: int,
        total_steps: int,
        success: bool,
        change_ids: list[str] = None,
    ) -> None:
        """Log the completion of a pipeline execution."""
        status = "success" if success else "failed"
        entry = {
            "timestamp": datetime.now().isoformat(),
            "correlation_id": correlation_id,
            "task_id": task_id,
            "execution_type": execution_type,
            "event": "pipeline_complete",
            "step": total_steps,
            "agent": "orchestrator",
            "status": status,
            "duration_ms": duration_ms,
            "total_steps": total_steps,
        }
        if change_ids:
            entry["change_ids"] = change_ids
        self._write_log(entry)


# Validators registry - maps agent name to validator
AGENT_VALIDATORS = {
    "ResearchAgent": ResearchValidator(),
    "ContentAgent": ContentValidator(),
    "TechnicalSEOAgent": TechnicalSEOValidator(),
    "AnalyticsAgent": AnalyticsValidator(),
}

# ---------------------------------------------------------------------------
# Pipeline registry — maps execution_type → ordered list of agent names.
# Deterministic: no AI routing, no dynamic selection.
# ---------------------------------------------------------------------------
AGENT_PIPELINE: dict[str, list[str]] = {
    "research":             ["ResearchAgent"],
    "rewrite_title":        ["ResearchAgent", "ContentAgent"],
    "rewrite_meta_desc":    ["ResearchAgent", "ContentAgent"],
    "rewrite_h1":           ["ResearchAgent", "ContentAgent"],
    "blog_write":           ["ResearchAgent", "ContentAgent"],
    "rewrite_blog_content": ["ResearchAgent", "ContentAgent"],
    "update_schema":        ["TechnicalSEOAgent"],
    "alt_text":             ["TechnicalSEOAgent"],
    "internal_links":       ["ResearchAgent", "TechnicalSEOAgent"],
    "seo_impact_review":    ["AnalyticsAgent"],
    # Phase 5: Programmatic SEO pipelines
    "programmatic_seo":     ["ResearchAgent", "ContentAgent", "TechnicalSEOAgent"],
    "location_pages":       ["ResearchAgent", "ContentAgent", "TechnicalSEOAgent"],
    "comparison_pages":     ["ResearchAgent", "ContentAgent", "TechnicalSEOAgent"],
    "faq_pages":            ["ResearchAgent", "ContentAgent", "TechnicalSEOAgent"],
}

# ---------------------------------------------------------------------------
# Agent registry — maps agent name → specialist class.
# ---------------------------------------------------------------------------
AGENT_REGISTRY: dict[str, type] = {
    "ResearchAgent":     ResearchAgent,
    "ContentAgent":      ContentAgent,
    "AnalyticsAgent":    AnalyticsAgent,
    "TechnicalSEOAgent": TechnicalSEOAgent,
}


class OrchestratorAgent:
    """
    Deterministic multi-specialist orchestrator.

    Reads the task's execution_type, resolves a pipeline from AGENT_PIPELINE,
    runs each specialist in sequence (passing prior outputs forward), and posts
    progress comments via add_comment_fn.

    Unknown execution types fall back to the legacy SEOAgent.

    Features (Phases 1-5):
    - Supervisor logging with correlation IDs
    - Retry logic for failed tool calls
    - Validation layer between agents
    - Automated feedback loop integration

    Args:
        config: AgentConfig with site_url, site_name, and tool settings.
        add_comment_fn: Callable[str] that posts a comment to the Kanban task.
            Signature: add_comment_fn(body: str) -> None.
            Kept as a callback so the orchestrator stays DB-agnostic.
    """

    def __init__(
        self,
        config: AgentConfig,
        add_comment_fn: Callable[[str], None],
        supervisor_logger: SupervisorLogger | None = None,
        feedback_loop: FeedbackLoopOrchestrator | None = None,
    ):
        self.config = config
        self.add_comment_fn = add_comment_fn
        self.supervisor_logger = supervisor_logger or SupervisorLogger()
        self.feedback_loop = feedback_loop or FeedbackLoopOrchestrator()

    def get_pipeline(self, execution_type: str) -> list[str]:
        """
        Return the ordered agent pipeline for the given execution_type.

        Returns an empty list for unknown types (triggers legacy fallback).

        Args:
            execution_type: Task execution_type string.

        Returns:
            List of agent name strings (e.g. ["ResearchAgent", "ContentAgent"]).
        """
        return AGENT_PIPELINE.get(execution_type, [])

    async def run(self, task, user_comments: list) -> str:
        """
        Execute the task through the appropriate specialist pipeline.

        Routes by task.execution_type:
        - Known type → runs the registered pipeline of specialist agents.
        - Unknown type → falls back to legacy SEOAgent.

        Posts 🔄 (start) and ✅ (complete) progress comments for each agent.
        Posts ❌ comment and re-raises on specialist failure.

        Features:
        - Supervisor logging (Phase 1)
        - Validation layer after each step (Phase 3)
        - Automatic change extraction and logging (Phase 4)

        Args:
            task: TaskModel with .title, .description, .execution_type.
            user_comments: List of CommentModel objects (all comments on the task).

        Returns:
            Final output string from the last agent in the pipeline,
            or legacy SEOAgent output for unknown types.
        """
        pipeline = self.get_pipeline(task.execution_type)
        correlation_id = str(uuid.uuid4())[:8]
        start_time = time.time()

        if not pipeline:
            logger.info(
                "OrchestratorAgent: unknown execution_type '%s', using legacy fallback",
                task.execution_type,
            )
            return await self._run_legacy_fallback(task, user_comments)

        # Log pipeline start (Phase 1)
        if self.config.enable_supervisor_logging:
            self.supervisor_logger.log_pipeline_start(
                task_id=task.id,
                execution_type=task.execution_type,
                pipeline=pipeline,
                correlation_id=correlation_id,
            )

        # Build user notes list (author == "user")
        user_notes = [c.body for c in user_comments if c.author == "user"]

        # Initialize context
        ctx = AgentContext(
            task_id=task.id,
            task_title=task.title,
            task_description=task.description,
            execution_type=task.execution_type,
            pipeline_step=0,
            pipeline_total=len(pipeline),
            prior_outputs=[],
            user_notes=user_notes,
            site_url=self.config.site_url,
            site_name=self.config.site_name,
        )

        prior_outputs: list[dict] = []
        all_change_ids: list[str] = []

        for step_idx, agent_name in enumerate(pipeline):
            ctx.pipeline_step = step_idx
            ctx.prior_outputs = list(prior_outputs)  # snapshot — agents must not mutate this
            step_start_time = time.time()

            self.add_comment_fn(
                f"🔄 [{step_idx + 1}/{len(pipeline)}] Running {agent_name}..."
            )
            logger.info(
                "OrchestratorAgent: step %d/%d — %s",
                step_idx + 1,
                len(pipeline),
                agent_name,
            )

            # Log step start (Phase 1)
            if self.config.enable_supervisor_logging:
                input_size = sum(len(str(p.get("output", ""))) for p in prior_outputs)
                self.supervisor_logger.log_step_start(
                    task_id=task.id,
                    execution_type=task.execution_type,
                    step=step_idx + 1,
                    agent=agent_name,
                    correlation_id=correlation_id,
                    input_size=input_size,
                )

            agent_cls = AGENT_REGISTRY.get(agent_name)
            if agent_cls is None:
                err = f"Agent '{agent_name}' not found in AGENT_REGISTRY"
                self.add_comment_fn(f"❌ {agent_name} failed: {err}")
                if self.config.enable_supervisor_logging:
                    self.supervisor_logger.log_step_complete(
                        task_id=task.id,
                        execution_type=task.execution_type,
                        step=step_idx + 1,
                        agent=agent_name,
                        correlation_id=correlation_id,
                        duration_ms=int((time.time() - step_start_time) * 1000),
                        output_size=0,
                        success=False,
                    )
                raise RuntimeError(err)

            agent = agent_cls(self.config)
            step_success = False
            retry_count = 0
            validation_score: float | None = None
            validation_passed: bool | None = None

            try:
                result: AgentResult = await agent.run(ctx)
                step_success = True
                retry_count = getattr(result, "retry_count", 0)
            except Exception as e:
                err_msg = str(e)[:200]
                self.add_comment_fn(f"❌ {agent_name} failed: {err_msg}")
                logger.exception("OrchestratorAgent: %s raised an exception", agent_name)

                # Log failed step (Phase 1)
                if self.config.enable_supervisor_logging:
                    self.supervisor_logger.log_step_complete(
                        task_id=task.id,
                        execution_type=task.execution_type,
                        step=step_idx + 1,
                        agent=agent_name,
                        correlation_id=correlation_id,
                        duration_ms=int((time.time() - step_start_time) * 1000),
                        output_size=0,
                        success=False,
                        retry_count=0,
                    )
                raise

            # Run validation (Phase 3)
            if self.config.enable_validation and step_success:
                validator = AGENT_VALIDATORS.get(agent_name)
                if validator:
                    validation_result = validator.validate(result, ctx)
                    validation_score = validation_result.score
                    validation_passed = validation_result.is_valid

                    if not validation_passed:
                        issues_str = "; ".join(validation_result.issues[:3])
                        self.add_comment_fn(
                            f"⚠️ {agent_name} validation warning (score: {validation_score:.0%}): {issues_str}"
                        )

            prior_outputs.append({
                "agent": result.agent_name,
                "output": result.output,
                "structured": result.structured,
            })

            # Log step complete (Phase 1)
            if self.config.enable_supervisor_logging:
                self.supervisor_logger.log_step_complete(
                    task_id=task.id,
                    execution_type=task.execution_type,
                    step=step_idx + 1,
                    agent=agent_name,
                    correlation_id=correlation_id,
                    duration_ms=int((time.time() - step_start_time) * 1000),
                    output_size=len(result.output),
                    success=True,
                    retry_count=retry_count,
                    validation_score=validation_score,
                    validation_passed=validation_passed,
                )

            self.add_comment_fn(
                f"✅ [{step_idx + 1}/{len(pipeline)}] {agent_name} complete"
            )
            logger.info(
                "OrchestratorAgent: step %d/%d — %s complete (%d chars)",
                step_idx + 1,
                len(pipeline),
                agent_name,
                len(result.output),
            )

            # Extract and log changes (Phase 4)
            if step_success:
                changes = self.feedback_loop.extract_changes_from_output(result, ctx)
                if changes:
                    change_ids = self.feedback_loop.log_changes(changes)
                    all_change_ids.extend(change_ids)

        # Log pipeline complete (Phase 1)
        total_duration_ms = int((time.time() - start_time) * 1000)
        if self.config.enable_supervisor_logging:
            self.supervisor_logger.log_pipeline_complete(
                task_id=task.id,
                execution_type=task.execution_type,
                correlation_id=correlation_id,
                duration_ms=total_duration_ms,
                total_steps=len(pipeline),
                success=True,
                change_ids=all_change_ids,
            )

        # Post supervisor summary (Phase 1)
        seconds_total = total_duration_ms / 1000
        summary = f"Completed in {len(pipeline)} steps, {seconds_total:.1f} seconds total"
        if all_change_ids:
            summary += f". Changes logged: {len(all_change_ids)}"
        self.add_comment_fn(f"📊 {summary}")

        # Schedule impact review if needed (Phase 4)
        should_review, reason = self.feedback_loop.should_trigger_impact_review()
        if should_review:
            self.feedback_loop.update_context_for_review()
            self.add_comment_fn(f"⏰ Impact review scheduled: {reason}")

        # Return the final agent's output
        return prior_outputs[-1]["output"] if prior_outputs else ""

    async def _run_legacy_fallback(self, task, user_comments: list) -> str:
        """
        Fall back to the monolithic SEOAgent for unknown execution types.

        Uses build_execution_prompt() from main.py and SEOAgent.create_and_run().

        Args:
            task: TaskModel instance.
            user_comments: List of CommentModel objects.

        Returns:
            SEOAgent output string.
        """
        from agent.seo_agent import SEOAgent
        from agent.api.main import build_execution_prompt

        prompt = build_execution_prompt(task, comments=user_comments, config=self.config)

        fallback_config = AgentConfig.from_env()
        fallback_config.cwd = self.config.cwd
        fallback_config.setting_sources = []
        fallback_config.system_prompt = (
            "You are an autonomous SEO agent. Execute the given task completely "
            "and autonomously. Use the tools available to you. Report what you did "
            "and the outcome clearly at the end."
        )

        return await SEOAgent.create_and_run(prompt, fallback_config)
