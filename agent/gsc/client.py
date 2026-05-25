"""
Google Search Console API Client for the SEO Agent.

Wraps two GSC APIs:
  - Search Analytics (webmasters v3) — clicks, impressions, CTR, position
  - URL Inspection (searchconsole v1) — indexed status, crawl errors, canonical

NOTE: This client is intentionally read-only. No write methods are provided.
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from typing import Any, Optional

from google.oauth2 import service_account
from googleapiclient import discovery

from .config import GoogleSearchConsoleConfig

# Thread pool for running blocking Google API calls without blocking the event loop
_executor = ThreadPoolExecutor(max_workers=10)

logger = logging.getLogger(__name__)

# Search Analytics requires webmasters.readonly; URL Inspection requires the broader scope.
_GSC_SCOPES = [
    "https://www.googleapis.com/auth/webmasters.readonly",
    "https://www.googleapis.com/auth/webmasters",
]
_GSC_DATA_LAG_DAYS = 3


class GoogleSearchConsoleError(Exception):
    """Exception raised for Google Search Console API errors."""

    def __init__(self, message: str, status: int = 0, response: Optional[dict] = None):
        super().__init__(message)
        self.status = status
        self.response = response


class GoogleSearchConsoleClient:
    """
    Read-only client for the Google Search Console APIs.

    Search Analytics: before/after CTR and click metrics for the seo_impact_review workflow.
    URL Inspection:   indexed status, coverage state, and crawl info for individual URLs.
    """

    def __init__(self, config: GoogleSearchConsoleConfig):
        self.config = config
        self._webmasters_service: Optional[Any] = None
        self._searchconsole_service: Optional[Any] = None

    def _build_credentials(self):
        return service_account.Credentials.from_service_account_file(
            str(self.config.credentials_path),
            scopes=_GSC_SCOPES,
        )

    async def _get_webmasters_service(self) -> Any:
        """Lazy-load the webmasters v3 service (Search Analytics)."""
        if self._webmasters_service is None:
            self._webmasters_service = discovery.build(
                "webmasters",
                "v3",
                credentials=self._build_credentials(),
                cache_discovery=False,
            )
        return self._webmasters_service

    async def _get_searchconsole_service(self) -> Any:
        """Lazy-load the searchconsole v1 service (URL Inspection)."""
        if self._searchconsole_service is None:
            self._searchconsole_service = discovery.build(
                "searchconsole",
                "v1",
                credentials=self._build_credentials(),
                cache_discovery=False,
            )
        return self._searchconsole_service

    async def close(self):
        self._webmasters_service = None
        self._searchconsole_service = None

    # -------------------------------------------------------------------------
    # Search Analytics
    # -------------------------------------------------------------------------

    async def get_page_metrics(self, url: str, start_date: str, end_date: str) -> dict[str, Any]:
        """
        Fetch aggregated Search Analytics metrics for a single page URL.

        Args:
            url:        Full page URL.
            start_date: ISO date string "YYYY-MM-DD" (inclusive).
            end_date:   ISO date string "YYYY-MM-DD" (inclusive).

        Returns:
            Dict with keys: clicks, impressions, ctr, position.
            All values are 0 / 0.0 if no data exists.
        """
        service = await self._get_webmasters_service()
        body = {
            "startDate": start_date,
            "endDate": end_date,
            "dimensions": ["page"],
            "dimensionFilterGroups": [
                {
                    "filters": [
                        {"dimension": "page", "operator": "equals", "expression": url}
                    ]
                }
            ],
            "rowLimit": 1,
        }
        try:
            response = (
                service.searchanalytics()
                .query(siteUrl=self.config.site_url, body=body)
                .execute()
            )
        except Exception as exc:
            logger.error("GSC Search Analytics error for %s: %s", url, exc)
            raise GoogleSearchConsoleError(f"GSC API error: {exc}") from exc

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
        self, url: str, change_date: str, days: int = 28
    ) -> dict[str, Any]:
        """
        Fetch before/after GSC metrics for a page around a given change date.

        Args:
            url:         Full page URL.
            change_date: ISO date string of when the SEO change was logged.
            days:        Comparison window size in days (default 28).

        Returns:
            Dict with keys: url, before, after, delta, before_period, after_period, data_available.
        """
        change = date.fromisoformat(change_date)
        today = date.today()
        data_cutoff = today - timedelta(days=_GSC_DATA_LAG_DAYS)

        before_end = change - timedelta(days=1)
        before_start = before_end - timedelta(days=days - 1)
        after_start = change
        after_end = min(change + timedelta(days=days - 1), data_cutoff)

        if after_start > after_end:
            return {
                "url": url,
                "before": {"clicks": 0, "impressions": 0, "ctr": 0.0, "position": 0.0},
                "after": {"clicks": 0, "impressions": 0, "ctr": 0.0, "position": 0.0},
                "delta": {"clicks_delta": 0, "impressions_delta": 0, "ctr_delta": 0.0, "position_delta": 0.0},
                "before_period": {"start": str(before_start), "end": str(before_end)},
                "after_period": {"start": str(after_start), "end": str(after_end)},
                "data_available": False,
            }

        before = await self.get_page_metrics(url, str(before_start), str(before_end))
        after = await self.get_page_metrics(url, str(after_start), str(after_end))

        delta = {
            "clicks_delta": after["clicks"] - before["clicks"],
            "impressions_delta": after["impressions"] - before["impressions"],
            "ctr_delta": round(after["ctr"] - before["ctr"], 8),
            "position_delta": round(after["position"] - before["position"], 8),
        }

        return {
            "url": url,
            "before": before,
            "after": after,
            "delta": delta,
            "before_period": {"start": str(before_start), "end": str(before_end)},
            "after_period": {"start": str(after_start), "end": str(after_end)},
            "data_available": True,
        }

    # -------------------------------------------------------------------------
    # URL Inspection
    # -------------------------------------------------------------------------

    async def inspect_url(self, url: str) -> dict[str, Any]:
        """
        Inspect a single URL using the GSC URL Inspection API.

        Returns a normalised dict with the most actionable fields:
            url, verdict, coverage_state, robots_txt_state, indexing_state,
            last_crawl_time, page_fetch_state, google_canonical, user_canonical,
            sitemap_urls, referring_urls, rich_results.

        Verdict values: PASS | NEUTRAL | FAIL | VERDICT_UNSPECIFIED
        Coverage state examples: Submitted and indexed, Crawled - currently not indexed,
            Discovered - currently not indexed, Duplicate without canonical, etc.

        Args:
            url: Full page URL to inspect (must belong to the configured site_url property).

        Raises:
            GoogleSearchConsoleError: on API failure.
        """
        service = await self._get_searchconsole_service()
        body = {
            "inspectionUrl": url,
            "siteUrl": self.config.site_url,
        }
        try:
            loop = asyncio.get_event_loop()
            creds_path = str(self.config.credentials_path)
            site_url = self.config.site_url

            def _call():
                # Build a fresh service per call so concurrent threads don't share state
                _creds = service_account.Credentials.from_service_account_file(
                    creds_path, scopes=_GSC_SCOPES
                )
                _svc = discovery.build(
                    "searchconsole", "v1", credentials=_creds, cache_discovery=False
                )
                return _svc.urlInspection().index().inspect(body=body).execute()

            response = await loop.run_in_executor(_executor, _call)
        except Exception as exc:
            logger.error("GSC URL Inspection error for %s: %s", url, exc)
            raise GoogleSearchConsoleError(f"GSC URL Inspection error: {exc}") from exc

        result = response.get("inspectionResult", {})
        index_status = result.get("indexStatusResult", {})
        mobile = result.get("mobileUsabilityResult", {})
        rich = result.get("richResultsResult", {})

        return {
            "url": url,
            "verdict": index_status.get("verdict", "VERDICT_UNSPECIFIED"),
            "coverage_state": index_status.get("coverageState", ""),
            "robots_txt_state": index_status.get("robotsTxtState", ""),
            "indexing_state": index_status.get("indexingState", ""),
            "last_crawl_time": index_status.get("lastCrawlTime"),
            "page_fetch_state": index_status.get("pageFetchState", ""),
            "google_canonical": index_status.get("googleCanonical"),
            "user_canonical": index_status.get("userCanonical"),
            "sitemap_urls": index_status.get("sitemap", []),
            "referring_urls": index_status.get("referringUrls", []),
            "mobile_usability_verdict": mobile.get("verdict"),
            "rich_results_verdict": rich.get("verdict"),
            "is_indexed": index_status.get("verdict") == "PASS",
        }

    async def inspect_urls(self, urls: list[str], concurrency: int = 5) -> list[dict[str, Any]]:
        """
        Inspect multiple URLs concurrently.

        The URL Inspection API has a quota of 2,000 requests/day. Concurrency is
        capped at 5 by default to stay within rate limits while being fast enough
        for bulk sitemap audits.

        Args:
            urls:        List of full page URLs to inspect.
            concurrency: Max parallel requests (default 5).

        Returns:
            List of inspection result dicts in the same order as input.
            Failed individual URLs are returned with verdict=ERROR and an error key.
        """
        semaphore = asyncio.Semaphore(concurrency)

        async def _inspect_one(url: str) -> dict[str, Any]:
            async with semaphore:
                try:
                    return await self.inspect_url(url)
                except GoogleSearchConsoleError as exc:
                    return {
                        "url": url,
                        "verdict": "ERROR",
                        "is_indexed": False,
                        "error": str(exc),
                    }

        return list(await asyncio.gather(*[_inspect_one(u) for u in urls]))
