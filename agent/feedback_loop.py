"""
Automated Feedback Loop Orchestrator.

Coordinates between change logging and impact review.
Triggers impact review after changes are implemented.
"""

import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from agent.specialists.base import AgentContext, AgentResult

logger = logging.getLogger(__name__)

# Memory files
MEMORY_DIR = Path(__file__).parent.parent / "memory"
SEO_CHANGES_FILE = MEMORY_DIR / "seo-changes.json"
SEO_CONTEXT_FILE = MEMORY_DIR / "seo-context.md"
SEO_LEARNINGS_FILE = MEMORY_DIR / "seo-learnings.json"

# Default review interval
DEFAULT_REVIEW_INTERVAL_DAYS = 14
DEFAULT_PENDING_THRESHOLD = 5


@dataclass
class ChangeEntry:
    """Represents a logged SEO change."""

    id: str
    task_id: int
    task_title: str
    execution_type: str
    change_type: str
    url: Optional[str] = None
    before: Optional[dict] = None
    after: Optional[dict] = None
    extraction_status: str = "auto"
    is_backfilled: bool = False
    logged_at: str = field(default_factory=lambda: datetime.now().isoformat())
    attempts: int = 1
    status: str = "pending-review"
    review_notes: Optional[str] = None
    reviewed_at: Optional[str] = None
    learning_ids: list[str] = field(default_factory=list)
    failure_reason: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "task_id": self.task_id,
            "task_title": self.task_title,
            "execution_type": self.execution_type,
            "change_type": self.change_type,
            "url": self.url,
            "before": self.before,
            "after": self.after,
            "extraction_status": self.extraction_status,
            "is_backfilled": self.is_backfilled,
            "logged_at": self.logged_at,
            "attempts": self.attempts,
            "status": self.status,
            "review_notes": self.review_notes,
            "reviewed_at": self.reviewed_at,
            "learning_ids": self.learning_ids,
            "failure_reason": self.failure_reason,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ChangeEntry":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            task_id=data["task_id"],
            task_title=data["task_title"],
            execution_type=data["execution_type"],
            change_type=data["change_type"],
            url=data.get("url"),
            before=data.get("before"),
            after=data.get("after"),
            extraction_status=data.get("extraction_status", "auto"),
            is_backfilled=data.get("is_backfilled", False),
            logged_at=data.get("logged_at", datetime.now().isoformat()),
            attempts=data.get("attempts", 1),
            status=data.get("status", "pending-review"),
            review_notes=data.get("review_notes"),
            reviewed_at=data.get("reviewed_at"),
            learning_ids=data.get("learning_ids", []),
            failure_reason=data.get("failure_reason"),
        )


class FeedbackLoopOrchestrator:
    """
    Orchestrates automated feedback loop between change logging and impact review.

    Features:
    - Automatic change detection from agent output
    - Change logging to seo-changes.json
    - Scheduled impact review triggering
    - Learning attribution
    """

    def __init__(
        self,
        changes_file: Path = SEO_CHANGES_FILE,
        context_file: Path = SEO_CONTEXT_FILE,
        learnings_file: Path = SEO_LEARNINGS_FILE,
        review_interval_days: int = DEFAULT_REVIEW_INTERVAL_DAYS,
        pending_threshold: int = DEFAULT_PENDING_THRESHOLD,
    ):
        self.changes_file = changes_file
        self.context_file = context_file
        self.learnings_file = learnings_file
        self.review_interval_days = review_interval_days
        self.pending_threshold = pending_threshold

    def extract_changes_from_output(
        self, result: AgentResult, ctx: AgentContext
    ) -> list[ChangeEntry]:
        """
        Parse agent output for change log blocks.

        Looks for <!-- CHANGE_LOG {...} --> blocks.

        Args:
            result: Agent result from an agent.
            ctx: Agent context with task details.

        Returns:
            List of ChangeEntry objects found in output.
        """
        changes: list[ChangeEntry] = []
        output = result.output

        # Pattern to match CHANGE_LOG blocks
        pattern = r"<!--\s*CHANGE_LOG\s*([\s\S]*?)\s*-->"
        matches = re.finditer(pattern, output, re.IGNORECASE)

        for match in matches:
            try:
                json_str = match.group(1).strip()
                change_data = json.loads(json_str)

                entry = ChangeEntry(
                    id=change_data.get(
                        "id",
                        f"{ctx.task_id}-{ctx.execution_type}-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    ),
                    task_id=ctx.task_id,
                    task_title=ctx.task_title,
                    execution_type=ctx.execution_type,
                    change_type=change_data.get("change_type", "unknown"),
                    url=change_data.get("url"),
                    before=change_data.get("before"),
                    after=change_data.get("after"),
                    extraction_status="auto",
                )
                changes.append(entry)

            except (json.JSONDecodeError, KeyError) as e:
                logger.debug("Failed to parse CHANGE_LOG block: %s", e)
                continue

        return changes

    def log_changes(self, changes: list[ChangeEntry]) -> list[str]:
        """
        Store changes in seo-changes.json.

        Args:
            changes: List of ChangeEntry to log.

        Returns:
            List of new change IDs.
        """
        if not changes:
            return []

        # Ensure memory directory exists
        self.changes_file.parent.mkdir(parents=True, exist_ok=True)

        # Load existing changes
        existing_changes = []
        if self.changes_file.exists():
            try:
                with open(self.changes_file) as f:
                    existing_changes = json.load(f)
            except json.JSONDecodeError:
                logger.warning("Corrupted seo-changes.json, starting fresh")
                existing_changes = []

        # Check for duplicates
        existing_ids = {c.get("id") for c in existing_changes}
        new_changes = []

        for change in changes:
            if change.id not in existing_ids:
                new_changes.append(change.to_dict())
                existing_ids.add(change.id)

        if not new_changes:
            return []

        # Append new changes
        existing_changes.extend(new_changes)

        # Write atomically
        temp_file = self.changes_file.with_suffix(".json.tmp")
        with open(temp_file, "w") as f:
            json.dump(existing_changes, f, indent=2)
        temp_file.replace(self.changes_file)

        logger.info("Logged %d new changes to seo-changes.json", len(new_changes))
        return [c["id"] for c in new_changes]

    def should_trigger_impact_review(self) -> tuple[bool, str]:
        """
        Check if impact review should be triggered.

        Returns:
            Tuple of (should_trigger, reason).
        """
        # Check last review date
        last_review_date = self._get_last_review_date()
        days_since_review = (datetime.now() - last_review_date).days

        if days_since_review >= self.review_interval_days:
            return True, f"{days_since_review} days since last review"

        # Check pending changes count
        pending_count = self._get_pending_changes_count()
        if pending_count >= self.pending_threshold:
            return True, f"{pending_count} pending changes"

        return False, ""

    def _get_last_review_date(self) -> datetime:
        """Get the date of the last impact review."""
        # Try to read from seo-context.md
        if self.context_file.exists():
            content = self.context_file.read_text()
            match = re.search(
                r"last_impact_review_date\s*[:\-]\s*(\d{4}-\d{2}-\d{2})",
                content,
                re.IGNORECASE,
            )
            if match:
                return datetime.fromisoformat(match.group(1))

        # Fall back to file modification time of seo-changes.json
        if self.changes_file.exists():
            return datetime.fromtimestamp(self.changes_file.stat().st_mtime)

        return datetime.now() - timedelta(days=self.review_interval_days)

    def _get_pending_changes_count(self) -> int:
        """Count changes pending review."""
        if not self.changes_file.exists():
            return 0

        try:
            with open(self.changes_file) as f:
                changes = json.load(f)
            return sum(1 for c in changes if c.get("status") == "pending-review")
        except (json.JSONDecodeError, OSError):
            return 0

    def update_context_for_review(self, scheduled_date: Optional[datetime] = None) -> None:
        """
        Update seo-context.md with review scheduling info.

        Args:
            scheduled_date: Date to schedule the review. Defaults to now + interval.
        """
        if scheduled_date is None:
            scheduled_date = datetime.now() + timedelta(days=self.review_interval_days)

        scheduled_str = scheduled_date.strftime("%Y-%m-%d")

        # Read existing context
        content = ""
        if self.context_file.exists():
            content = self.context_file.read_text()

        # Update or add scheduled review
        if "next_impact_review_date" in content:
            content = re.sub(
                r"next_impact_review_date\s*[:\-]\s*\d{4}-\d{2}-\d{2}",
                f"next_impact_review_date: {scheduled_str}",
                content,
                flags=re.IGNORECASE,
            )
        else:
            content += f"\n\n## Scheduled Reviews\n\n- next_impact_review_date: {scheduled_str}\n"

        self.context_file.write_text(content)
        logger.info("Scheduled impact review for %s", scheduled_str)

    def link_learning_to_change(
        self, change_id: str, learning_id: str, confidence: str
    ) -> None:
        """
        Link a learning back to a specific change.

        Args:
            change_id: ID of the change entry.
            learning_id: ID of the learning.
            confidence: Confidence level (low/medium/high).
        """
        if not self.changes_file.exists():
            return

        try:
            with open(self.changes_file) as f:
                changes = json.load(f)

            for change in changes:
                if change["id"] == change_id:
                    if "learning_ids" not in change:
                        change["learning_ids"] = []
                    change["learning_ids"].append(
                        f"{learning_id}:{confidence}"
                    )
                    break

            with open(self.changes_file, "w") as f:
                json.dump(changes, f, indent=2)

        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to link learning to change: %s", e)