"""
Programmatic SEO Support Module.

Provides templated page generation for location pages, comparison pages,
and FAQ pages. Supports bulk operations with configurable concurrency.
"""

import asyncio
import csv
import io
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# Memory files
MEMORY_DIR = Path(__file__).parent.parent / "memory"
REFERENCES_DIR = MEMORY_DIR.parent / "Skills" / "programmatic-seo" / "references"


@dataclass
class PageTemplate:
    """Template for generating programmatic SEO pages."""

    name: str
    type: str  # "location", "comparison", "faq", "custom"
    url_pattern: str
    title_pattern: str
    meta_description_pattern: str
    content_template: str
    schema_template: Optional[str] = None
    h1_pattern: Optional[str] = None


@dataclass
class PageData:
    """Data for populating a template."""

    variables: dict[str, str]
    url: str
    title: str
    meta_description: str
    h1: str
    content: str
    schema: Optional[str] = None


@dataclass
class BulkJobProgress:
    """Progress tracking for bulk operations."""

    total: int
    completed: int = 0
    failed: int = 0
    pending: int = 0
    errors: list[dict] = field(default_factory=list)

    @property
    def progress_percent(self) -> float:
        if self.total == 0:
            return 0.0
        return (self.completed / self.total) * 100

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "completed": self.completed,
            "failed": self.failed,
            "pending": self.pending,
            "progress_percent": self.progress_percent,
            "errors": self.errors,
        }


class TemplatedPageGenerator:
    """
    Generator for programmatic SEO pages using templates.

    Supports:
    - Location page templates (city + service)
    - Comparison page templates (A vs B)
    - FAQ page templates (topic clusters)
    - CSV/data import for bulk generation
    """

    # Built-in templates
    LOCATION_TEMPLATE = PageTemplate(
        name="location_page",
        type="location",
        url_pattern="{service_slug}/{location_slug}",
        title_pattern="{service} in {city} | {site_name}",
        meta_description_pattern="Find the best {service} in {city}. {unique_value}. Serving {city} and surrounding areas. Book now!",
        h1_pattern="{service} in {city}",
        content_template="""# {h1}

## Why Choose Our {service} Services in {city}?

{intro_paragraph}

## Our {service} Services in {city}

We offer comprehensive {service_lower} solutions:

{service_list}

## {city} {service} Process

1. **Consultation** - Free assessment of your needs
2. **Custom Plan** - Tailored solution for your {city} property
3. **Implementation** - Professional service delivery
4. **Follow-up** - Quality guarantee and support

## Areas We Serve in {city}

- {primary_area}
{additional_areas}

## FAQ About {service} in {city}

{faq_section}

## Ready to Get Started?

Contact us today for a free consultation in {city}.

{cta_section}
""",
        schema_template="""{
  "@context": "https://schema.org",
  "@type": "LocalBusiness",
  "name": "{business_name}",
  "areaServed": {
    "@type": "City",
    "name": "{city}"
  },
  "serviceType": "{service}"
}
""",
    )

    COMPARISON_TEMPLATE = PageTemplate(
        name="comparison_page",
        type="comparison",
        url_pattern="{slug_a}-vs-{slug_b}",
        title_pattern="{name_a} vs {name_b}: Which is Better for {use_case}?",
        meta_description_pattern="Compare {name_a} and {name_b} for {use_case}. Features, pricing, pros and cons. Find the best choice for your needs.",
        h1_pattern="{name_a} vs {name_b}",
        content_template="""# {h1}

## Quick Verdict

{quick_verdict}

## Feature Comparison

| Feature | {name_a} | {name_b} |
|---------|----------|----------|
{feature_rows}

## {name_a} Overview

{name_a_overview}

### {name_a} Pros
{pros_a}

### {name_a} Cons
{cons_a}

## {name_b} Overview

{name_b_overview}

### {name_b} Pros
{pros_b}

### {name_b} Cons
{cons_b}

## Pricing Comparison

{pricing_section}

## Use Case Analysis

{use_case_section}

## FAQ: {name_a} vs {name_b}

{faq_section}

## Conclusion: Which Should You Choose?

{conclusion}
""",
    )

    FAQ_TEMPLATE = PageTemplate(
        name="faq_page",
        type="faq",
        url_pattern="faq/{topic_slug}",
        title_pattern="{topic} FAQ: Common Questions Answered",
        meta_description_pattern="Find answers to common questions about {topic}. Expert guidance on {topic_lower}. Everything you need to know.",
        h1_pattern="Frequently Asked Questions About {topic}",
        content_template="""# {h1}

## Common Questions About {topic}

{intro}

{faqs}

## Still Have Questions?

If you couldn't find the answer to your question, please contact us.

{contact_section}

## Related Topics

{related_topics}
""",
        schema_template="""{
  "@context": "https://schema.org",
  "@type": "FAQPage",
  "mainEntity": [
{faq_schema_items}
  ]
}
""",
    )

    def __init__(self, site_name: str, site_url: str):
        self.site_name = site_name
        self.site_url = site_url

    def generate_location_page(self, data: dict[str, Any]) -> PageData:
        """
        Generate a location page from data.

        Args:
            data: Dictionary with location/service variables.

        Returns:
            PageData ready for content generation.
        """
        template = self.LOCATION_TEMPLATE
        return self._generate_from_template(template, data)

    def generate_comparison_page(self, data: dict[str, Any]) -> PageData:
        """
        Generate a comparison page from data.

        Args:
            data: Dictionary with comparison variables.

        Returns:
            PageData ready for content generation.
        """
        template = self.COMPARISON_TEMPLATE
        return self._generate_from_template(template, data)

    def generate_faq_page(self, data: dict[str, Any]) -> PageData:
        """
        Generate an FAQ page from data.

        Args:
            data: Dictionary with FAQ variables.

        Returns:
            PageData ready for content generation.
        """
        template = self.FAQ_TEMPLATE
        return self._generate_from_template(template, data)

    def _generate_from_template(self, template: PageTemplate, data: dict[str, Any]) -> PageData:
        """Generate page data from a template."""
        # Build variables with site defaults
        variables = {
            "site_name": self.site_name,
            "site_url": self.site_url,
            **data,
        }

        # Generate URL
        url = self._interpolate(template.url_pattern, variables)

        # Generate title
        title = self._interpolate(template.title_pattern, variables)

        # Generate meta description
        meta_description = self._interpolate(template.meta_description_pattern, variables)

        # Generate H1
        h1 = self._interpolate(template.h1_pattern or title, variables)

        # Generate content
        content = self._interpolate(template.content_template, variables)

        # Generate schema if available
        schema = None
        if template.schema_template:
            schema = self._interpolate(template.schema_template, variables)

        return PageData(
            variables=variables,
            url=url,
            title=title,
            meta_description=meta_description,
            h1=h1,
            content=content,
            schema=schema,
        )

    def _interpolate(self, template: str, variables: dict[str, Any]) -> str:
        """Simple template interpolation."""
        result = template
        for key, value in variables.items():
            placeholder = "{" + key + "}"
            placeholder_lower = "{" + key.lower() + "}"
            result = result.replace(placeholder, str(value))
            result = result.replace(placeholder_lower, str(value).lower())
        return result

    def load_data_from_csv(self, csv_content: str) -> list[dict[str, Any]]:
        """
        Parse CSV data for bulk generation.

        Args:
            csv_content: CSV string content.

        Returns:
            List of dictionaries, one per row.
        """
        reader = csv.DictReader(io.StringIO(csv_content))
        return list(reader)

    def load_data_from_json(self, json_content: str) -> list[dict[str, Any]]:
        """
        Parse JSON data for bulk generation.

        Args:
            json_content: JSON string content (array of objects).

        Returns:
            List of dictionaries.
        """
        data = json.loads(json_content)
        if isinstance(data, list):
            return data
        return [data]


class BulkPageProcessor:
    """
    Process multiple pages concurrently with progress tracking.

    Supports configurable concurrency and error handling.
    """

    def __init__(
        self,
        generator: TemplatedPageGenerator,
        concurrency: int = 3,
        progress_callback: Optional[Callable[[BulkJobProgress], None]] = None,
    ):
        self.generator = generator
        self.concurrency = concurrency
        self.progress_callback = progress_callback
        self._progress: Optional[BulkJobProgress] = None

    async def process_pages(
        self,
        pages_data: list[dict[str, Any]],
        page_type: str = "location",
    ) -> tuple[list[PageData], list[dict]]:
        """
        Process multiple pages concurrently.

        Args:
            pages_data: List of data dictionaries for each page.
            page_type: Type of page to generate ("location", "comparison", "faq").

        Returns:
            Tuple of (successful_pages, errors).
        """
        self._progress = BulkJobProgress(total=len(pages_data), pending=len(pages_data))
        successful: list[PageData] = []
        errors: list[dict] = []

        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(self.concurrency)

        async def process_single(data: dict[str, Any], index: int) -> tuple[Optional[PageData], Optional[dict]]:
            async with semaphore:
                try:
                    if page_type == "location":
                        page = self.generator.generate_location_page(data)
                    elif page_type == "comparison":
                        page = self.generator.generate_comparison_page(data)
                    elif page_type == "faq":
                        page = self.generator.generate_faq_page(data)
                    else:
                        page = self.generator._generate_from_template(
                            PageTemplate(
                                name="custom",
                                type="custom",
                                url_pattern=data.get("url_pattern", ""),
                                title_pattern=data.get("title_pattern", ""),
                                meta_description_pattern=data.get("meta_description_pattern", ""),
                                content_template=data.get("content_template", ""),
                            ),
                            data,
                        )
                    return page, None
                except Exception as e:
                    return None, {
                        "index": index,
                        "data": data,
                        "error": str(e),
                    }

        # Create tasks
        tasks = [process_single(data, i) for i, data in enumerate(pages_data)]
        results = await asyncio.gather(*tasks)

        # Process results
        for page, error in results:
            self._progress.pending -= 1
            if error:
                self._progress.failed += 1
                self._progress.errors.append(error)
                errors.append(error)
            else:
                self._progress.completed += 1
                successful.append(page)

            # Report progress
            if self.progress_callback:
                self.progress_callback(self._progress)

        return successful, errors

    def get_progress(self) -> Optional[BulkJobProgress]:
        """Get current progress."""
        return self._progress


def get_programmatic_seo_prompt(
    site_name: str,
    site_url: str,
    page_type: str,
    keywords: list[str],
    location: Optional[str] = None,
    comparison_items: Optional[list[str]] = None,
) -> str:
    """
    Generate a prompt for programmatic SEO tasks.

    Args:
        site_name: Name of the site.
        site_url: URL of the site.
        page_type: Type of pages to generate.
        keywords: Target keywords.
        location: Optional location for location pages.
        comparison_items: Optional items for comparison pages.

    Returns:
        Formatted prompt string.
    """
    if page_type == "location" and location:
        return f"""## Programmatic SEO: Location Page Generation

Generate location pages for {site_name} ({site_url}).

Target keywords: {', '.join(keywords)}
Location: {location}

Use the Skills/programmatic-seo skill for guidance on:
- Location page best practices
- Unique content per page
- Internal linking strategy
- Local business schema

Generate {len(keywords)} location page variations targeting different service/location combinations.
"""
    elif page_type == "comparison":
        items = comparison_items or keywords[:2]
        return f"""## Programmatic SEO: Comparison Page Generation

Generate comparison pages for {site_name} ({site_url}).

Items to compare: {', '.join(items)}
Target keywords: {', '.join(keywords)}

Use the Skills/programmatic-seo skill for guidance on:
- Comparison page structure
- Feature matrix formatting
- Unbiased content guidelines
- Schema markup for comparisons

Generate {len(items)} comparison pages (one per item pair).
"""
    else:
        return f"""## Programmatic SEO: Bulk Page Generation

Generate bulk pages for {site_name} ({site_url}).

Target keywords: {', '.join(keywords)}
Page type: {page_type}

Use the Skills/programmatic-seo skill for guidance on:
- Template selection
- Content uniqueness
- Quality thresholds
- Indexation strategy

Generate pages targeting all provided keywords.
"""