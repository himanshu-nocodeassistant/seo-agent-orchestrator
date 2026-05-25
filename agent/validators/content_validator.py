"""
Content Agent Output Validator.

Validates blog posts, title rewrites, meta descriptions, and H1 rewrites.
"""

import logging
import re

from agent.specialists.base import AgentContext, AgentResult
from agent.validators.base import BaseValidator, ValidationResult

logger = logging.getLogger(__name__)

# Minimum quality thresholds by content type
THRESHOLDS: dict[str, dict[str, int | float]] = {
    "blog_write": {
        "min_word_count": 800,
        "max_word_count": 5000,
        "min_h2_count": 3,
        "required_fields": ["title", "meta_description", "slug"],
    },
    "rewrite_title": {
        "min_length": 50,
        "max_length": 60,
    },
    "rewrite_meta_desc": {
        "min_length": 150,
        "max_length": 160,
    },
    "rewrite_h1": {
        "min_length": 10,
        "max_length": 70,
    },
    "rewrite_blog_content": {
        "min_word_count": 500,
    },
}


class ContentValidator(BaseValidator):
    """
    Validator for ContentAgent outputs.

    Checks for:
    - Proper length for titles, meta descriptions
    - Sufficient word count for blog posts
    - Proper heading structure (H1, H2s)
    - Required fields present
    """

    name: str = "ContentValidator"

    def validate(self, result: AgentResult, ctx: AgentContext) -> ValidationResult:
        """
        Validate content agent output quality.

        Args:
            result: AgentResult from ContentAgent.
            ctx: AgentContext with task details.

        Returns:
            ValidationResult with quality assessment.
        """
        issues: list[str] = []
        suggestions: list[str] = []
        score = 1.0

        output = result.output
        execution_type = ctx.execution_type

        # Get thresholds for this execution type
        thresholds = THRESHOLDS.get(execution_type, THRESHOLDS["blog_write"])

        if execution_type == "blog_write":
            self._validate_blog_post(output, thresholds, issues, suggestions, score)
        elif execution_type == "rewrite_title":
            self._validate_title(output, thresholds, issues, suggestions, score)
        elif execution_type == "rewrite_meta_desc":
            self._validate_meta_desc(output, thresholds, issues, suggestions, score)
        elif execution_type == "rewrite_h1":
            self._validate_h1(output, thresholds, issues, suggestions, score)
        else:
            # Generic validation for other content types
            word_count = self._count_words(output)
            if word_count < 200:
                issues.append(f"Output too short: {word_count} words (minimum: 200)")
                score -= 0.2

        # Check for brand voice application (mentions in output)
        if "brand" not in output.lower() and "voice" not in output.lower():
            suggestions.append("Consider verifying brand voice was applied")

        is_valid = score >= 0.7

        return ValidationResult(
            is_valid=is_valid,
            score=max(0.0, score),
            issues=issues,
            suggestions=suggestions,
        )

    def _validate_blog_post(
        self,
        output: str,
        thresholds: dict[str, int],
        issues: list[str],
        suggestions: list[str],
        score: float,
    ) -> None:
        """Validate blog post content."""
        word_count = self._count_words(output)

        min_words = thresholds.get("min_word_count", 800)
        max_words = thresholds.get("max_word_count", 5000)

        if word_count < min_words:
            issues.append(f"Word count too low: {word_count} words (minimum: {min_words})")
            score -= 0.2
        elif word_count > max_words:
            issues.append(f"Word count too high: {word_count} words (maximum: {max_words})")
            score -= 0.1

        # Check for H1
        if not re.search(r"^#\s+", output, re.MULTILINE):
            issues.append("Missing H1 heading")
            score -= 0.1

        # Check for H2 sections
        h2_count = len(re.findall(r"^##\s+", output, re.MULTILINE))
        min_h2 = thresholds.get("min_h2_count", 3)
        if h2_count < min_h2:
            issues.append(f"Too few H2 sections: {h2_count} (minimum: {min_h2})")
            score -= 0.1

        # Check for required fields
        required_fields = thresholds.get("required_fields", [])
        for field in required_fields:
            field_patterns = {
                "title": r"(?i)(?:seo\s+)?title\s*[:\-]\s*[^\n]{10,}",
                "meta_description": r"(?i)meta\s*description\s*[:\-]\s*[^\n]{50,}",
                "slug": r"(?i)(?:url\s+)?slug\s*[:\-]\s*[^\n]+",
            }
            pattern = field_patterns.get(field, "")
            if pattern and not re.search(pattern, output):
                issues.append(f"Missing or incomplete {field}")
                score -= 0.05

        # Check for keyword in first 100 words
        first_100 = " ".join(output.split()[:100]).lower()
        # This is a placeholder - actual keyword should come from context
        if "keyword" not in first_100 and "primary" not in first_100:
            suggestions.append("Consider ensuring primary keyword appears in first 100 words")

    def _validate_title(
        self,
        output: str,
        thresholds: dict[str, int],
        issues: list[str],
        suggestions: list[str],
        score: float,
    ) -> None:
        """Validate title rewrite."""
        # Extract title from output (look for "Title:" or similar pattern)
        title_match = re.search(
            r"(?:final\s+)?title\s*[:\-]\s*([^\n]{10,70})",
            output,
            re.IGNORECASE,
        )

        if title_match:
            title = title_match.group(1).strip()
            length = len(title)

            min_len = thresholds.get("min_length", 50)
            max_len = thresholds.get("max_length", 60)

            if length < min_len:
                issues.append(f"Title too short: {length} chars (minimum: {min_len})")
                score -= 0.2
            elif length > max_len:
                issues.append(f"Title too long: {length} chars (maximum: {max_len})")
                score -= 0.2
        else:
            issues.append("Could not extract final title from output")
            score -= 0.3

    def _validate_meta_desc(
        self,
        output: str,
        thresholds: dict[str, int],
        issues: list[str],
        suggestions: list[str],
        score: float,
    ) -> None:
        """Validate meta description rewrite."""
        meta_match = re.search(
            r"meta\s*description\s*[:\-]\s*([^\n]{50,200})",
            output,
            re.IGNORECASE,
        )

        if meta_match:
            meta = meta_match.group(1).strip()
            length = len(meta)

            min_len = thresholds.get("min_length", 150)
            max_len = thresholds.get("max_length", 160)

            if length < min_len:
                issues.append(f"Meta description too short: {length} chars (minimum: {min_len})")
                score -= 0.2
            elif length > max_len:
                issues.append(f"Meta description too long: {length} chars (maximum: {max_len})")
                score -= 0.2
        else:
            issues.append("Could not extract meta description from output")
            score -= 0.3

    def _validate_h1(
        self,
        output: str,
        thresholds: dict[str, int],
        issues: list[str],
        suggestions: list[str],
        score: float,
    ) -> None:
        """Validate H1 rewrite."""
        h1_match = re.search(
            r"(?:final\s+)?h1\s*[:\-]\s*([^\n]{5,100})",
            output,
            re.IGNORECASE,
        )

        if h1_match:
            h1 = h1_match.group(1).strip()
            length = len(h1)

            min_len = thresholds.get("min_length", 10)
            max_len = thresholds.get("max_length", 70)

            if length < min_len:
                issues.append(f"H1 too short: {length} chars (minimum: {min_len})")
                score -= 0.2
            elif length > max_len:
                issues.append(f"H1 too long: {length} chars (maximum: {max_len})")
                score -= 0.2
        else:
            issues.append("Could not extract H1 from output")
            score -= 0.3

    def _count_words(self, text: str) -> int:
        """Count words in text."""
        return len(text.split())