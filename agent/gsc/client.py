"""
Google Search Console API client for the SEO Agent.

Read-only: queries search analytics, inspects URLs, lists sitemaps.
No write operations are exposed.
"""

import logging
from datetime import date, timedelta
from typing import Any, Optional

from google.oauth2 import service_account
from googleapiclient import discovery

from .config import GscConfig

logger = logging.getLogger(__name__)

# Read-only scope — never request write access
_GSC_SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"


class GscAPIError(Exception):
    """Exception raised for Google Search Console API errors."""

    def __init__(self, message: str, status: int = 0, response: Optional[dict] = None):
        super().__init__(message)
        self.status = status
        self.response = response


class GscAPIClient:
    """
    Read-only client for Google Search Console API.

    Methods:
    - query_search_analytics: clicks/impressions/CTR/position by page or query
    - inspect_url: indexing status for a single URL
    - list_sitemaps: sitemaps submitted for the property
    """

    def __init__(self, config: GscConfig):
        self.config = config
        self._service: Optional[Any] = None

    async def _get_service(self) -> Any:
        if self._service is None:
            credentials = service_account.Credentials.from_service_account_file(
                str(self.config.credentials_path),
                scopes=[_GSC_SCOPE],
            )
            self._service = discovery.build(
                "searchconsole",
                "v1",
                credentials=credentials,
                cache_discovery=False,
                num_retries=3,
            )
        return self._service

    async def close(self):
        self._service = None

    async def get_page_metrics(
        self,
        url: str,
        start_date: str,
        end_date: str,
    ) -> dict[str, Any]:
        """Return aggregate Search Console metrics for one page and period."""
        response = await self.query_search_analytics(
            start_date=start_date,
            end_date=end_date,
            dimensions=["page"],
            row_limit=1,
            dimension_filter_groups=[
                {
                    "groupType": "and",
                    "filters": [
                        {
                            "dimension": "page",
                            "operator": "equals",
                            "expression": url,
                        }
                    ],
                }
            ],
        )
        rows = response.get("rows", [])
        if not rows:
            return {"clicks": 0, "impressions": 0, "ctr": 0.0, "position": 0.0}
        row = rows[0]
        return {
            "clicks": int(row.get("clicks", 0)),
            "impressions": int(row.get("impressions", 0)),
            "ctr": float(row.get("ctr", 0.0)),
            "position": float(row.get("position", 0.0)),
        }

    async def get_page_metrics_range(
        self,
        url: str,
        change_date: str,
        days: int = 28,
    ) -> dict[str, Any]:
        """Compare equal before/after periods around an SEO change."""
        if days < 1 or days > 90:
            raise ValueError("days must be between 1 and 90")
        change = date.fromisoformat(change_date)
        data_cutoff = date.today() - timedelta(days=3)
        before_end = change - timedelta(days=1)
        before_start = before_end - timedelta(days=days - 1)
        after_start = change
        after_end = min(change + timedelta(days=days - 1), data_cutoff)
        periods = {
            "before_period": {"start": str(before_start), "end": str(before_end)},
            "after_period": {"start": str(after_start), "end": str(after_end)},
        }
        empty = {"clicks": 0, "impressions": 0, "ctr": 0.0, "position": 0.0}
        if after_start > after_end:
            return {
                "url": url,
                "before": empty,
                "after": empty,
                "delta": {
                    "clicks_delta": 0,
                    "impressions_delta": 0,
                    "ctr_delta": 0.0,
                    "position_delta": 0.0,
                },
                **periods,
                "data_available": False,
            }
        before = await self.get_page_metrics(url, str(before_start), str(before_end))
        after = await self.get_page_metrics(url, str(after_start), str(after_end))
        return {
            "url": url,
            "before": before,
            "after": after,
            "delta": {
                "clicks_delta": after["clicks"] - before["clicks"],
                "impressions_delta": after["impressions"] - before["impressions"],
                "ctr_delta": round(after["ctr"] - before["ctr"], 8),
                "position_delta": round(after["position"] - before["position"], 8),
            },
            **periods,
            "data_available": True,
        }

    # -------------------------------------------------------------------------
    # Search Analytics
    # -------------------------------------------------------------------------

    async def query_search_analytics(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        dimensions: Optional[list[str]] = None,
        row_limit: int = 25,
        start_row: int = 0,
        dimension_filter_groups: Optional[list[dict]] = None,
    ) -> dict[str, Any]:
        """
        Run a Search Analytics query.

        Args:
            start_date: ISO date string (YYYY-MM-DD). Defaults to 28 days ago.
            end_date: ISO date string (YYYY-MM-DD). Defaults to yesterday.
            dimensions: List of dimensions to group by.
                Valid values: "query", "page", "country", "device", "date".
                Defaults to ["query"].
            row_limit: Max rows to return (1-25000). Defaults to 25.
            start_row: Zero-based offset for pagination.
            dimension_filter_groups: Optional GSC dimension filter groups
                (see GSC API docs for schema).

        Returns:
            Dict with "rows" list and metadata.
        """
        service = await self._get_service()

        today = date.today()
        default_end = (today - timedelta(days=3)).isoformat()
        default_start = (today - timedelta(days=31)).isoformat()

        body: dict[str, Any] = {
            "startDate": start_date or default_start,
            "endDate": end_date or default_end,
            "dimensions": dimensions or ["query"],
            "rowLimit": min(max(1, row_limit), 25000),
            "startRow": start_row,
        }

        if dimension_filter_groups:
            body["dimensionFilterGroups"] = dimension_filter_groups

        try:
            response = (
                service.searchanalytics()
                .query(siteUrl=self.config.site_url, body=body)
                .execute()
            )
            return response
        except Exception as e:
            logger.error("GSC search analytics query failed: %s", e)
            raise GscAPIError(f"Search analytics query failed: {e}")

    # -------------------------------------------------------------------------
    # URL Inspection
    # -------------------------------------------------------------------------

    async def inspect_url(self, inspection_url: str) -> dict[str, Any]:
        """
        Inspect a URL's indexing status via the URL Inspection API.

        Args:
            inspection_url: The full URL to inspect.

        Returns:
            Dict with indexStatusResult and related fields.
        """
        service = await self._get_service()

        try:
            response = (
                service.urlInspection()
                .index()
                .inspect(
                    body={
                        "inspectionUrl": inspection_url,
                        "siteUrl": self.config.site_url,
                    }
                )
                .execute()
            )
            return response
        except Exception as e:
            logger.error("GSC URL inspection failed for %s: %s", inspection_url, e)
            raise GscAPIError(f"URL inspection failed: {e}")

    # -------------------------------------------------------------------------
    # Sitemaps
    # -------------------------------------------------------------------------

    async def list_sitemaps(self, sitemap_index: Optional[str] = None) -> dict[str, Any]:
        """
        List sitemaps submitted for the property.

        Args:
            sitemap_index: Optional — filter to sitemaps in this index URL.

        Returns:
            Dict with "sitemap" list.
        """
        service = await self._get_service()

        try:
            kwargs: dict[str, Any] = {"siteUrl": self.config.site_url}
            if sitemap_index:
                kwargs["sitemapIndex"] = sitemap_index

            response = service.sitemaps().list(**kwargs).execute()
            return response
        except Exception as e:
            logger.error("GSC sitemaps list failed: %s", e)
            raise GscAPIError(f"Sitemaps list failed: {e}")
