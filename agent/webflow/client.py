"""
Webflow API Client for managing CMS collections.

This module provides the WebflowAPIClient class that wraps
the Webflow Data API v2.0 for CRUD operations on CMS items.
"""

import json
import logging
import asyncio
import random
from typing import Any, Optional

import aiohttp

from .config import WebflowConfig

logger = logging.getLogger(__name__)

# Retryable transient statuses (rate limits + upstream hiccups).
_RETRYABLE_STATUSES = {429, 502, 503, 504}
_MAX_ATTEMPTS = 4


class WebflowAPIError(Exception):
    """Exception raised for Webflow API errors."""

    def __init__(self, message: str, status: int = 0, response: Optional[dict] = None):
        super().__init__(message)
        self.status = status
        self.response = response


class WebflowAPIClient:
    """
    Async client for Webflow CMS API.

    Provides methods for managing collection items:
    - list_items: Get all items in a collection
    - get_item: Get a single item by ID
    - create_item: Create a new item
    - update_item: Update an existing item
    - publish_item: Publish item to live site
    """

    def __init__(self, config: WebflowConfig):
        """Initialize the Webflow API client."""
        self.config = config
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={
                    "Authorization": f"Bearer {self.config.access_token}",
                    "Content-Type": "application/json",
                    "User-Agent": self.config.user_agent,
                }
            )
        return self._session

    async def close(self):
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> dict[str, Any]:
        """
        Make an API request to Webflow.

        Args:
            method: HTTP method (GET, POST, PATCH, DELETE)
            endpoint: API endpoint path
            data: Request body (for POST/PATCH)
            params: Query parameters

        Returns:
            Response JSON as dict

        Raises:
            WebflowAPIError: If the API returns an error
        """
        url = f"{self.config.base_url}{endpoint}"
        session = await self._get_session()

        logger.debug(f"Webflow API: {method} {url}")

        for attempt in range(_MAX_ATTEMPTS):
            try:
                async with session.request(
                    method,
                    url,
                    json=data,
                    params=params,
                ) as response:
                    response_data = (
                        await response.json()
                        if response.content_type == "application/json"
                        else {}
                    )

                    if response.status in _RETRYABLE_STATUSES and attempt < _MAX_ATTEMPTS - 1:
                        await self._backoff(response, attempt)
                        continue

                    if not response.ok:
                        error_msg = response_data.get("msg", f"HTTP {response.status}")
                        raise WebflowAPIError(
                            f"Webflow API error: {error_msg}",
                            status=response.status,
                            response=response_data,
                        )

                    logger.debug(f"Webflow API response: {response_data}")
                    return response_data

            except aiohttp.ClientError as e:
                if attempt < _MAX_ATTEMPTS - 1:
                    logger.warning(
                        "Webflow request failed (attempt %d/%d): %s — retrying",
                        attempt + 1,
                        _MAX_ATTEMPTS,
                        e,
                    )
                    await asyncio.sleep(min(2 ** attempt, 30) * (0.5 + random.random() / 2))
                    continue
                logger.error(f"Webflow API request failed: {e}")
                raise WebflowAPIError(f"Request failed: {e}")

        raise WebflowAPIError("Webflow API request failed after retries")

    @staticmethod
    async def _backoff(response, attempt: int) -> None:
        """Sleep honoring Retry-After when present, else jittered exponential."""
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                delay = float(retry_after)
            except ValueError:
                delay = min(2 ** attempt, 30)
        else:
            delay = min(2 ** attempt, 30) * (0.5 + random.random() / 2)
        await asyncio.sleep(delay)

    # -------------------------------------------------------------------------
    # CMS Collection Item Operations
    # -------------------------------------------------------------------------

    async def list_items(
        self,
        limit: int = 100,
        offset: int = 0,
        sort_by: Optional[str] = None,
        sort_order: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        List all items in the collection (live items).

        Args:
            limit: Number of items to return (default 100)
            offset: Offset for pagination (default 0)
            sort_by: Field to sort by (e.g., "_createdOn", "name")
            sort_order: Sort direction ("asc" or "desc")

        Returns:
            Dict with items array and pagination info
        """
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if sort_by:
            params["sortBy"] = sort_by
        if sort_order:
            params["sortOrder"] = sort_order

        return await self._request(
            "GET",
            f"/collections/{self.config.collection_id}/items/live",
            params=params,
        )

    async def get_item(self, item_id: str) -> dict[str, Any]:
        """
        Get a single item by ID.

        Args:
            item_id: The item's unique identifier

        Returns:
            Item data as dict
        """
        return await self._request(
            "GET",
            f"/collections/{self.config.collection_id}/items/{item_id}",
        )

    async def create_item(
        self,
        field_data: dict[str, Any],
        is_draft: bool = False,
        is_archived: bool = False,
    ) -> dict[str, Any]:
        """
        Create a new item in the collection.

        Args:
            field_data: Dict of field names and values (e.g., {"name": "Title", "slug": "my-post"})
            is_draft: Create as draft (default False)
            is_archived: Create as archived (default False)

        Returns:
            Created item data as dict
        """
        data = {
            "fieldData": field_data,
            "isDraft": is_draft,
            "isArchived": is_archived,
        }

        return await self._request(
            "POST",
            f"/collections/{self.config.collection_id}/items",
            data=data,
        )

    async def update_item(
        self,
        item_id: str,
        field_data: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Update an existing item.

        Args:
            item_id: The item's unique identifier
            field_data: Dict of field names and values to update

        Returns:
            Updated item data as dict
        """
        data = {
            "items": [
                {
                    "id": item_id,
                    "fieldData": field_data,
                }
            ]
        }

        return await self._request(
            "PATCH",
            f"/collections/{self.config.collection_id}/items",
            data=data,
        )

    async def publish_item(self, item_id: str) -> dict[str, Any]:
        """
        Publish an item to the live site.

        Args:
            item_id: The item's unique identifier

        Returns:
            Publish response as dict
        """
        data = {"itemIds": [item_id]}

        return await self._request(
            "POST",
            f"/collections/{self.config.collection_id}/items/publish",
            data=data,
        )

    # -------------------------------------------------------------------------
    # Collection Operations
    # -------------------------------------------------------------------------

    async def get_collection(self) -> dict[str, Any]:
        """
        Get collection details including field schema.

        Returns:
            Collection data as dict
        """
        return await self._request(
            "GET",
            f"/collections/{self.config.collection_id}",
        )

    async def list_collections(self) -> dict[str, Any]:
        """
        List all collections in the site.

        Returns:
            Dict with collections array
        """
        return await self._request(
            "GET",
            f"/sites/{self.config.site_id}/collections",
        )
