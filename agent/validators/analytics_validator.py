"""
Analytics Agent Output Validator.

Validates GSC data integrity and impact review completeness.
"""

import json
import logging
import re

from agent.specialists.base import AgentContext, AgentResult
from agent.validators.base import BaseValidator, ValidationResult

logger = logging.getLogger(__name__)


class AnalyticsValidator(BaseValidator):
    """
    Validator for AnalyticsAgent outputs.

    Checks for:
    - Complete impact review with all phases
    - Proper structured summary
    - Learning attribution
    - Actionable next steps
    """

    name: str = "AnalyticsValidator"

    def validate(self, result: AgentResult, ctx: AgentContext) -> ValidationResult:
        """
        Validate analytics agent output quality.

        Args:
            result: AgentResult from AnalyticsAgent.
            ctx: AgentContext with task details.

        Returns:
            ValidationResult with quality assessment.
        """
        issues: list[str] = []
        suggestions: list[str] = []
        score = 1.0

        output = result.output

        # 1. Check for structured summary
        has_summary = bool(
            re.search(r"(?:positive|negative|neutral|inconclusive)", output, re.IGNORECASE)
        )

        if not has_summary:
            issues.append("Missing structured summary of review outcomes")
            score -= 0.25

        # 2. Check for learning extraction
        has_learning = bool(
            re.search(r"(?:learning|principle|pattern)", output, re.IGNORECASE)
        )

        if not has_learning:
            suggestions.append("Consider extracting learnings from positive outcomes")

        # 3. Check for next steps
        has_next_steps = bool(
            re.search(r"(?:next|task|recommend)", output, re.IGNORECASE)
        )

        if not has_next_steps:
            suggestions.append("Include recommended next tasks based on findings")

        # 4. Validate required phases were executed
        phases = [
            ("backfill", r"(?:backfill|backfill)"),
            ("batch", r"(?:batch|process)"),
            ("evaluat", r"(?:evaluat|classif)"),
            ("learn", r"(?:learn)"),
        ]

        for phase_name, pattern in phases:
            if not re.search(pattern, output, re.IGNORECASE):
                suggestions.append(f"Phase '{phase_name}' appears incomplete")

        # 5. Check output is substantial enough
        if len(output) < 300:
            issues.append("Output too short for comprehensive impact review")
            score -= 0.2

        # 6. Check for JSON update confirmation
        has_json_update = bool(
            re.search(r"(?:wrote|updated|saved).*(?:seo-changes|seo-learnings)", output, re.IGNORECASE)
        )

        if not has_json_update:
            suggestions.append("Confirm that memory files were updated")

        is_valid = score >= 0.7

        return ValidationResult(
            is_valid=is_valid,
            score=max(0.0, score),
            issues=issues,
            suggestions=suggestions,
        )

    def validate_gsc_data(self, data: dict) -> ValidationResult:
        """
        Validate GSC (Google Search Console) data integrity.

        Args:
            data: GSC data dictionary.

        Returns:
            ValidationResult for data quality.
        """
        issues: list[str] = []
        suggestions: list[str] = []
        score = 1.0

        required_fields = ["clicks", "impressions", "ctr", "position"]
        for field in required_fields:
            if field not in data:
                issues.append(f"Missing required GSC field: {field}")
                score -= 0.15

        # Validate data types
        if "clicks" in data and not isinstance(data["clicks"], (int, float)):
            issues.append("Invalid clicks data type")
            score -= 0.1

        if "impressions" in data and not isinstance(data["impressions"], (int, float)):
            issues.append("Invalid impressions data type")
            score -= 0.1

        # Validate reasonable ranges
        if "position" in data:
            pos = data["position"]
            if isinstance(pos, (int, float)) and (pos < 1 or pos > 100):
                suggestions.append("Position outside typical SERP range")

        return ValidationResult(
            is_valid=score >= 0.7,
            score=max(0.0, score),
            issues=issues,
            suggestions=suggestions,
        )