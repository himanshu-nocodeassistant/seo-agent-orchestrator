"""
Google Search Console MCP tools for Claude Agent SDK.

All tools are read-only. No write or delete operations are exposed.
"""

import json
import logging
from typing import Any, Optional

from claude_agent_sdk import tool

from .client import GscAPIClient, GscAPIError

logger = logging.getLogger(__name__)

_gsc_client: Optional[GscAPIClient] = None


def set_client(client: GscAPIClient) -> None:
    global _gsc_client
    _gsc_client = client


def get_client() -> GscAPIClient:
    if _gsc_client is None:
        raise RuntimeError("GSC client not initialized. Call set_client() first.")
    return _gsc_client


# =============================================================================
# Tools
# =============================================================================


@tool(
    "gsc_query_search_analytics",
    (
        "Query Google Search Console search analytics. Returns clicks, impressions, CTR, "
        "and average position grouped by query, page, country, device, or date. "
        "Use this to identify ranking opportunities, traffic trends, and CTR gaps."
    ),
    {
        "start_date": str,
        "end_date": str,
        "dimensions": list,
        "row_limit": int,
        "start_row": int,
        "dimension_filter_groups": list,
    },
)
async def query_search_analytics(args: dict[str, Any]) -> dict[str, Any]:
    """
    Query GSC Search Analytics.

    Args:
        start_date: ISO date (YYYY-MM-DD). Defaults to 28 days ago.
        end_date: ISO date (YYYY-MM-DD). Defaults to 3 days ago (GSC data lag).
        dimensions: Group-by dimensions. Valid: "query", "page", "country",
            "device", "date". Defaults to ["query"].
        row_limit: Rows to return (1-25000). Defaults to 25.
        start_row: Pagination offset. Defaults to 0.
        dimension_filter_groups: Optional GSC filter groups.

    Returns:
        JSON with rows array containing keys, clicks, impressions, ctr, position.
    """
    try:
        client = get_client()
        result = await client.query_search_analytics(
            start_date=args.get("start_date"),
            end_date=args.get("end_date"),
            dimensions=args.get("dimensions"),
            row_limit=args.get("row_limit", 25),
            start_row=args.get("start_row", 0),
            dimension_filter_groups=args.get("dimension_filter_groups"),
        )
        return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}
    except GscAPIError as e:
        return {"content": [{"type": "text", "text": f"Error: {e}"}]}
    except Exception as e:
        logger.exception("Unexpected error in gsc_query_search_analytics")
        return {"content": [{"type": "text", "text": f"Unexpected error: {e}"}]}


@tool(
    "gsc_inspect_url",
    (
        "Inspect a URL's indexing status in Google Search Console. "
        "Returns whether the URL is indexed, coverage state, canonical URL, "
        "and any crawl or indexing issues."
    ),
    {"inspection_url": str},
)
async def inspect_url(args: dict[str, Any]) -> dict[str, Any]:
    """
    Inspect a URL's indexing status.

    Args:
        inspection_url: Full URL to inspect (must belong to the configured property).

    Returns:
        JSON with indexStatusResult including verdict, coverageState, robotsTxtState, etc.
    """
    try:
        client = get_client()
        result = await client.inspect_url(args["inspection_url"])
        return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}
    except GscAPIError as e:
        return {"content": [{"type": "text", "text": f"Error: {e}"}]}
    except Exception as e:
        logger.exception("Unexpected error in gsc_inspect_url")
        return {"content": [{"type": "text", "text": f"Unexpected error: {e}"}]}


@tool(
    "gsc_list_sitemaps",
    (
        "List sitemaps submitted to Google Search Console for the configured property. "
        "Returns each sitemap's URL, type, last download time, and error counts."
    ),
    {"sitemap_index": str},
)
async def list_sitemaps(args: dict[str, Any]) -> dict[str, Any]:
    """
    List sitemaps for the GSC property.

    Args:
        sitemap_index: Optional URL of a sitemap index to filter results.

    Returns:
        JSON with sitemap array.
    """
    try:
        client = get_client()
        result = await client.list_sitemaps(sitemap_index=args.get("sitemap_index"))
        return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}
    except GscAPIError as e:
        return {"content": [{"type": "text", "text": f"Error: {e}"}]}
    except Exception as e:
        logger.exception("Unexpected error in gsc_list_sitemaps")
        return {"content": [{"type": "text", "text": f"Unexpected error: {e}"}]}


GSC_TOOLS = [
    query_search_analytics,
    inspect_url,
    list_sitemaps,
]
