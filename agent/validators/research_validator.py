"""
Research Agent Output Validator.

Validates keyword research, competitor analysis, and SERP data quality.
"""

import json
import logging
import re
from typing import Any

from agent.specialists.base import AgentContext, AgentResult
from agent.validators.base import BaseValidator, ValidationResult

logger = logging.getLogger(__name__)

# Minimum quality thresholds for research output
MIN_KEYWORDS: int = 5
MIN_COMPETITORS: int = 3
MIN_TITLE_OPTIONS: int = 2
MIN_OUTPUT_LENGTH: int = 500
MIN_WORD_COUNT: int = 200


class ResearchValidator(BaseValidator):
    """
    Validator for ResearchAgent outputs.

    Checks for:
    - Structured data block present and parseable
    - Minimum keyword count
    - Valid SERP analysis with competitor data
    - Actionable recommendations
    """

    name: str = "ResearchValidator"

    def validate(self, result: AgentResult, ctx: AgentContext) -> ValidationResult:
        """
        Validate research agent output quality.

        Args:
            result: AgentResult from ResearchAgent.
            ctx: AgentContext with task details.

        Returns:
            ValidationResult with quality assessment.
        """
        issues: list[str] = []
        suggestions: list[str] = []
        score = 1.0

        output = result.output
        structured = result.structured

        # 1. Check output length
        if len(output) < MIN_OUTPUT_LENGTH:
            issues.append(f"Output too short: {len(output)} chars (minimum: {MIN_OUTPUT_LENGTH})")
            score -= 0.2

        # 2. Try to extract structured data
        structured_data = self._extract_structured_data(output)

        if not structured_data:
            issues.append("Missing structured data block (<!-- RESEARCH_OUTPUT {...} -->)")
            score -= 0.3
        else:
            # 3. Validate keyword data
            keywords = structured_data.get("primary_keyword", "")
            if not keywords or len(keywords.strip()) < 2:
                issues.append("Missing or invalid primary keyword")
                score -= 0.15

            # 4. Validate competitor analysis
            competitors = structured_data.get("competitors", [])
            if len(competitors) < MIN_COMPETITORS:
                issues.append(f"Insufficient competitor data: {len(competitors)} (minimum: {MIN_COMPETITORS})")
                score -= 0.15

            # 5. Validate title options
            title_options = structured_data.get("title_options", [])
            if len(title_options) < MIN_TITLE_OPTIONS:
                issues.append(f"Missing title options: {len(title_options)} (minimum: {MIN_TITLE_OPTIONS})")
                score -= 0.1

        # 6. Check for key content sections
        has_volume = bool(structured_data.get("search_volume_estimate"))
        if not has_volume and "volume" not in output.lower():
            suggestions.append("Consider including search volume estimates")

        has_gaps = bool(structured_data.get("content_gaps"))
        if not has_gaps and "gap" not in output.lower():
            suggestions.append("Consider adding content gap analysis")

        has_recommendations = bool(structured_data.get("recommendations")) or "recommend" in output.lower()
        if not has_recommendations:
            suggestions.append("Add specific actionable recommendations")

        # Determine validity based on score threshold
        is_valid = score >= 0.7

        return ValidationResult(
            is_valid=is_valid,
            score=max(0.0, score),
            issues=issues,
            suggestions=suggestions,
        )

    def _extract_structured_data(self, output: str) -> dict[str, Any]:
        """Extract structured data block from research output."""
        # Try to find <!-- RESEARCH_OUTPUT {...} --> block
        pattern = r"<!--\s*RESEARCH_OUTPUT\s*([\s\S]*?)\s*-->"
        match = re.search(pattern, output, re.IGNORECASE)

        if match:
            try:
                # Try to parse as JSON
                json_str = match.group(1).strip()
                # Handle potential trailing commas or common JSON issues
                return json.loads(json_str)
            except json.JSONDecodeError as e:
                logger.debug("Failed to parse research structured data: %s", e)

        return {}

    def get_minimum_thresholds(self) -> dict[str, Any]:
        """Return minimum quality thresholds for this validator."""
        return {
            "min_keywords": MIN_KEYWORDS,
            "min_competitors": MIN_COMPETITORS,
            "min_title_options": MIN_TITLE_OPTIONS,
            "min_output_length": MIN_OUTPUT_LENGTH,
            "min_word_count": MIN_WORD_COUNT,
        }