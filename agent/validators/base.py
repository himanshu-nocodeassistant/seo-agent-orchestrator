"""
Base Validation Components for Agent Output Validation.

Defines the ValidationResult dataclass and base validator protocol.
"""

from dataclasses import dataclass, field
from typing import Protocol

from agent.specialists.base import AgentContext, AgentResult


@dataclass
class ValidationResult:
    """
    Result from validating an agent's output.

    Attributes:
        is_valid: Whether the output meets minimum quality threshold.
        score: Quality score from 0.0 to 1.0.
        issues: List of specific issues found in the output.
        suggestions: List of suggestions for improving the output.
    """

    is_valid: bool
    score: float
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)

    def __post_init__(self):
        """Clamp score to valid range."""
        self.score = max(0.0, min(1.0, self.score))

    @property
    def quality_rating(self) -> str:
        """Get human-readable quality rating."""
        if self.score >= 0.9:
            return "Excellent"
        elif self.score >= 0.8:
            return "Good"
        elif self.score >= 0.6:
            return "Acceptable"
        elif self.score >= 0.4:
            return "Needs Improvement"
        else:
            return "Poor"


class BaseValidator(Protocol):
    """Protocol for agent output validators."""

    def validate(
        self, result: AgentResult, ctx: AgentContext
    ) -> ValidationResult:
        """
        Validate the output from an agent.

        Args:
            result: The agent's output result.
            ctx: The agent context with task details.

        Returns:
            ValidationResult with quality assessment.
        """
        ...