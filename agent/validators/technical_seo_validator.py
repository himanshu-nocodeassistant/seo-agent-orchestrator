"""
Technical SEO Agent Output Validator.

Validates schema markup, alt text, and internal link recommendations.
"""

import json
import logging
import re

from agent.specialists.base import AgentContext, AgentResult
from agent.validators.base import BaseValidator, ValidationResult

logger = logging.getLogger(__name__)

# Required schema.org fields by schema type
REQUIRED_SCHEMA_FIELDS: dict[str, list[str]] = {
    "Article": ["@type", "@context", "headline", "author"],
    "BlogPosting": ["@type", "@context", "headline", "author", "datePublished"],
    "Service": ["@type", "@context", "name", "provider"],
    "FAQPage": ["@type", "@context", "mainEntity"],
    "Organization": ["@type", "@context", "name", "url"],
    "BreadcrumbList": ["@type", "@context", "itemListElement"],
}


class TechnicalSEOValidator(BaseValidator):
    """
    Validator for TechnicalSEOAgent outputs.

    Checks for:
    - Valid JSON-LD schema markup
    - Proper schema.org field requirements
    - Complete alt text recommendations
    - Actionable internal link plans
    """

    name: str = "TechnicalSEOValidator"

    def validate(self, result: AgentResult, ctx: AgentContext) -> ValidationResult:
        """
        Validate technical SEO agent output quality.

        Args:
            result: AgentResult from TechnicalSEOAgent.
            ctx: AgentContext with task details.

        Returns:
            ValidationResult with quality assessment.
        """
        issues: list[str] = []
        suggestions: list[str] = []
        score = 1.0

        output = result.output
        execution_type = ctx.execution_type

        if execution_type == "update_schema":
            self._validate_schema_markup(output, issues, suggestions, score)
        elif execution_type == "alt_text":
            self._validate_alt_text(output, issues, suggestions, score)
        elif execution_type == "internal_links":
            self._validate_internal_links(output, issues, suggestions, score)
        else:
            # Generic validation
            if len(output) < 100:
                issues.append("Output too short for technical SEO recommendations")
                score -= 0.3

        is_valid = score >= 0.7

        return ValidationResult(
            is_valid=is_valid,
            score=max(0.0, score),
            issues=issues,
            suggestions=suggestions,
        )

    def _validate_schema_markup(
        self,
        output: str,
        issues: list[str],
        suggestions: list[str],
        score: float,
    ) -> None:
        """Validate JSON-LD schema markup."""
        # Try to extract JSON-LD block
        json_ld = self._extract_json_ld(output)

        if not json_ld:
            issues.append("No valid JSON-LD schema found in output")
            score -= 0.4
            return

        # Check @context uses https://schema.org (not http://)
        context = json_ld.get("@context", "")
        if context == "http://schema.org":
            issues.append("Schema uses http:// instead of https://")
            score -= 0.2

        # Check @type is present
        schema_type = json_ld.get("@type", "")
        if not schema_type:
            issues.append("Missing @type field")
            score -= 0.2

        # Validate required fields for schema type
        if schema_type in REQUIRED_SCHEMA_FIELDS:
            required = REQUIRED_SCHEMA_FIELDS[schema_type]
            missing = [f for f in required if f not in json_ld and f != "@type" and f != "@context"]
            if missing:
                issues.append(f"Missing required fields for {schema_type}: {', '.join(missing)}")
                score -= 0.15

        # Check for recommended fields (not just required)
        if schema_type in ("Article", "BlogPosting"):
            recommended = ["datePublished", "dateModified", "publisher", "image"]
            missing_rec = [f for f in recommended if f not in json_ld]
            if missing_rec:
                suggestions.append(f"Consider adding recommended fields: {', '.join(missing_rec)}")

        # Check that there's implementation guidance
        if "insert" not in output.lower() and "implement" not in output.lower() and "add" not in output.lower():
            suggestions.append("Add step-by-step implementation instructions")

    def _validate_alt_text(
        self,
        output: str,
        issues: list[str],
        suggestions: list[str],
        score: float,
    ) -> None:
        """Validate alt text recommendations."""
        # Check for table format
        has_table = bool(re.search(r"\|\s*Image.*\|\s*Alt\s*Text", output, re.IGNORECASE))

        if not has_table:
            issues.append("Missing expected table format for alt text recommendations")
            score -= 0.2

        # Count alt text entries
        alt_count = len(re.findall(r"alt[\s_-]?text", output, re.IGNORECASE))

        if alt_count < 1:
            issues.append("No alt text recommendations found")
            score -= 0.3
        elif alt_count < 3:
            suggestions.append(f"Consider adding more alt text recommendations (found {alt_count})")

        # Check for descriptive alt text (not just empty or generic)
        generic_patterns = [
            r'alt=["\']?\s*["\']?\s*[\s]*["\']?',  # empty alt
            r'alt=["\']image["\']',  # generic "image"
            r'alt=["\']photo["\']',  # generic "photo"
        ]

        for pattern in generic_patterns:
            if re.search(pattern, output, re.IGNORECASE):
                suggestions.append("Some alt text may be too generic - ensure each is descriptive")
                break

    def _validate_internal_links(
        self,
        output: str,
        issues: list[str],
        suggestions: list[str],
        score: float,
    ) -> None:
        """Validate internal link recommendations."""
        # Check for link plan table or structured format
        has_plan = bool(
            re.search(r"(?:source|target|anchor)", output, re.IGNORECASE)
        )

        if not has_plan:
            issues.append("Missing structured link plan with source, target, and anchor text")
            score -= 0.2

        # Check for URLs in output
        url_count = len(re.findall(r"https?://[^\s<>\"\']+", output))

        if url_count < 2:
            issues.append(f"Too few URLs in link plan: {url_count} (expected 2+)")
            score -= 0.15

        # Check for anchor text recommendations
        has_anchor = bool(re.search(r"anchor\s*text", output, re.IGNORECASE))
        if not has_anchor:
            suggestions.append("Include anchor text recommendations for each link")

        # Check for priority indicators
        has_priority = bool(re.search(r"(?:priorit|high\s*impact)", output, re.IGNORECASE))
        if not has_priority:
            suggestions.append("Consider adding priority indicators for most impactful links")

    def _extract_json_ld(self, output: str) -> dict | None:
        """Extract JSON-LD block from output."""
        # Look for <script type="application/ld+json"> or standalone JSON
        patterns = [
            r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>([\s\S]*?)</script>',
            r'`{3}json\s*([\s\S]*?)`{3}',
            r'```\s*([\s\S]*?)```',
        ]

        for pattern in patterns:
            match = re.search(pattern, output, re.IGNORECASE)
            if match:
                try:
                    json_str = match.group(1).strip()
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    continue

        # Try parsing entire output as JSON
        try:
            return json.loads(output.strip())
        except json.JSONDecodeError:
            pass

        return None