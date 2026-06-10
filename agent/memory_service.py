"""
Layered memory helpers for prompt composition and host-managed views.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from .runtime_profiles import ExecutionProfile


SEMANTIC_FILES = {
    "project_overview": "memory/CLAUDE.md",
    "strategy": "memory/seo-strategy.md",
    "context_view": "memory/seo-context.md",
    "learnings_view": ".claude/seo-learnings.md",
}


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _truncate(text: str, limit: int) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."


def _extract_relevant_lines(text: str, hints: list[str], fallback_chars: int) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    lowered_hints = [hint.lower() for hint in hints if hint]
    matches = [line for line in lines if any(hint in line.lower() for hint in lowered_hints)]
    source = "\n".join(matches if matches else lines[:20])
    return _truncate(source, fallback_chars)


@dataclass
class ShortTermContext:
    run_id: str
    task_id: Optional[int]
    execution_type: str
    trigger_source: str
    session_id: Optional[str]
    validator_status: Optional[str]
    task_title: str
    task_description: Optional[str]
    user_comments: list[str] = field(default_factory=list)
    active_notes: Optional[str] = None


@dataclass
class EpisodicItem:
    run_id: str
    status: str
    trigger_source: str
    result_summary: Optional[str]
    validator_status: Optional[str]
    created_at: str
    finished_at: Optional[str]


@dataclass
class EpisodicContext:
    task_id: Optional[int]
    execution_type: str
    items: list[EpisodicItem] = field(default_factory=list)


@dataclass
class SemanticContext:
    project_overview: str
    strategy: str
    learnings: str
    context_view: str


@dataclass
class ProceduralContext:
    execution_type: str
    profile_name: str
    tool_policy: list[str]
    validator_name: str
    max_turns: int
    timeout_seconds: int
    procedural_tags: list[str]
    workflow_prompt: str


@dataclass
class ComposedPromptContext:
    short_term: ShortTermContext
    episodic: EpisodicContext
    semantic: SemanticContext
    procedural: ProceduralContext

    def to_prompt(self) -> str:
        sections = [
            "## Short-Term Memory",
            f"- Run ID: {self.short_term.run_id}",
            f"- Task ID: {self.short_term.task_id if self.short_term.task_id is not None else 'n/a'}",
            f"- Trigger Source: {self.short_term.trigger_source}",
            f"- Execution Type: {self.short_term.execution_type}",
            f"- Session ID: {self.short_term.session_id or 'new-session'}",
            f"- Validator Status: {self.short_term.validator_status or 'pending'}",
            f"- Task Title: {self.short_term.task_title}",
        ]
        if self.short_term.task_description:
            sections.append(f"- Task Description: {self.short_term.task_description}")
        if self.short_term.user_comments:
            sections.append("- User Comments:")
            sections.extend([f"  - {comment}" for comment in self.short_term.user_comments])
        if self.short_term.active_notes:
            sections.append(f"- Existing Task Notes: {self.short_term.active_notes}")

        sections.extend(["", "## Episodic Memory"])
        if self.episodic.items:
            for item in self.episodic.items:
                sections.append(
                    f"- [{item.created_at}] {item.trigger_source}/{item.status}"
                    f" validator={item.validator_status or 'n/a'} summary={item.result_summary or 'n/a'}"
                )
        else:
            sections.append("- No relevant prior runs.")

        sections.extend(
            [
                "",
                "## Semantic Memory",
                f"Project Overview: {self.semantic.project_overview or 'n/a'}",
                f"Strategy: {self.semantic.strategy or 'n/a'}",
                f"Learnings: {self.semantic.learnings or 'n/a'}",
            ]
        )
        if self.semantic.context_view:
            sections.append(f"Current Context View: {self.semantic.context_view}")

        procedural_lines = [
            "",
            "## Procedural Memory",
            f"- Profile: {self.procedural.profile_name}",
            f"- Tools: {', '.join(self.procedural.tool_policy)}",
            f"- Max Turns: {self.procedural.max_turns}",
            f"- Timeout Seconds: {self.procedural.timeout_seconds}",
            f"- Tags: {', '.join(self.procedural.procedural_tags) if self.procedural.procedural_tags else 'n/a'}",
            f"- Validator: {self.procedural.validator_name}",
        ]
        if "grounding-required" in self.procedural.procedural_tags:
            procedural_lines.append(
                "- Grounding rule: Every factual claim, keyword volume, or competitor"
                " reference MUST cite a source URL. Use WebSearch or WebFetch to retrieve"
                " evidence before stating conclusions. Do not assert facts without a cited source."
            )
        procedural_lines.extend([
            "",
            "## Workflow",
            self.procedural.workflow_prompt,
        ])
        sections.extend(procedural_lines)
        return "\n".join(sections)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_short_term_context(run, task, comments) -> ShortTermContext:
    return ShortTermContext(
        run_id=run.run_id,
        task_id=getattr(run, "task_id", None),
        execution_type=run.execution_type or getattr(task, "execution_type", None) or "manual",
        trigger_source=run.trigger_source,
        session_id=run.session_id,
        validator_status=run.validator_status,
        task_title=getattr(task, "title", ""),
        task_description=getattr(task, "description", None),
        user_comments=[comment.body for comment in comments if comment.author == "user"],
        active_notes=getattr(task, "notes", None),
    )


def fetch_episodic_context(db, task_id: Optional[int], execution_type: str, limit: int):
    from .api.main import AgentRunModel

    if task_id is None:
        return EpisodicContext(task_id=None, execution_type=execution_type, items=[])

    runs = (
        db.query(AgentRunModel)
        .filter(AgentRunModel.task_id == task_id, AgentRunModel.execution_type == execution_type)
        .order_by(AgentRunModel.started_at.desc())
        .limit(limit)
        .all()
    )
    items = [
        EpisodicItem(
            run_id=run.run_id,
            status=run.status,
            trigger_source=run.trigger_source,
            result_summary=_truncate(run.result_summary or "", 240) if run.result_summary else None,
            validator_status=run.validator_status,
            created_at=run.started_at,
            finished_at=run.finished_at,
        )
        for run in reversed(runs)
    ]
    return EpisodicContext(task_id=task_id, execution_type=execution_type, items=items)


def fetch_semantic_context(task, execution_type: str, cwd: str, char_limit: int) -> SemanticContext:
    root = Path(cwd)
    hints = [
        execution_type or "",
        getattr(task, "title", "") or "",
        getattr(task, "description", "") or "",
    ]
    project_overview = _extract_relevant_lines(_read_text(root / SEMANTIC_FILES["project_overview"]), hints, char_limit)
    strategy = _extract_relevant_lines(_read_text(root / SEMANTIC_FILES["strategy"]), hints, char_limit)
    learnings = _extract_relevant_lines(_read_text(root / SEMANTIC_FILES["learnings_view"]), hints, char_limit)
    context_view = _extract_relevant_lines(_read_text(root / SEMANTIC_FILES["context_view"]), hints, min(1200, char_limit))
    return SemanticContext(
        project_overview=project_overview,
        strategy=strategy,
        learnings=learnings,
        context_view=context_view,
    )


def fetch_procedural_context(execution_type: str, workflow_prompt: str, profile: ExecutionProfile) -> ProceduralContext:
    return ProceduralContext(
        execution_type=execution_type or "manual",
        profile_name=profile.execution_type,
        tool_policy=profile.allowed_tools,
        validator_name=profile.validator.__name__,
        max_turns=profile.max_turns,
        timeout_seconds=profile.timeout_seconds,
        procedural_tags=profile.procedural_tags,
        workflow_prompt=workflow_prompt,
    )


def compose_prompt_context(
    short_term: ShortTermContext,
    episodic: EpisodicContext,
    semantic: SemanticContext,
    procedural: ProceduralContext,
) -> ComposedPromptContext:
    return ComposedPromptContext(
        short_term=short_term,
        episodic=episodic,
        semantic=semantic,
        procedural=procedural,
    )


def generate_context_view_markdown(db, task_id: Optional[int] = None, limit: int = 25) -> str:
    from .api.main import AgentRunModel, TaskModel

    query = db.query(AgentRunModel).order_by(AgentRunModel.started_at.desc())
    if task_id is not None:
        query = query.filter(AgentRunModel.task_id == task_id)
    runs = query.limit(limit).all()

    lines = ["# SEO Context View", "", "## Recent Runs", ""]
    if not runs:
        lines.append("_No runs recorded yet._")
    for run in runs:
        task_title = "Unknown Task"
        if run.task_id is not None:
            task = db.query(TaskModel).filter(TaskModel.id == run.task_id).first()
            if task:
                task_title = task.title
        lines.extend(
            [
                f"### {run.started_at[:19]} - {task_title}",
                f"- Run ID: `{run.run_id}`",
                f"- Status: {run.status}",
                f"- Trigger: {run.trigger_source}",
                f"- Execution Type: {run.execution_type}",
                f"- Session ID: {run.session_id or 'n/a'}",
                f"- Validator Status: {run.validator_status or 'pending'}",
                f"- Summary: {_truncate(run.result_summary or run.error or '', 220) or 'n/a'}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"
