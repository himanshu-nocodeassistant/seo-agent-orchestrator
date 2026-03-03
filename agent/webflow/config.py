"""
Webflow configuration for the SEO Agent.

This module provides the WebflowConfig dataclass that holds
configuration for interacting with the Webflow CMS API.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class WebflowConfig:
    """Configuration for Webflow CMS integration."""

    # Webflow API access token (get from Webflow developer settings)
    access_token: str

    # Site ID from Webflow
    site_id: str

    # Collection ID for the CMS collection to manage
    collection_id: str

    # Base URL for Webflow API v2
    base_url: str = "https://api.webflow.com/v2"

    # User agent for API requests
    user_agent: str = "SEO-Agent/1.0"

    def __post_init__(self):
        """Validate configuration after initialization."""
        if not self.access_token:
            raise ValueError("Webflow access_token is required")
        if not self.site_id:
            raise ValueError("Webflow site_id is required")
        if not self.collection_id:
            raise ValueError("Webflow collection_id is required")
    
    def __repr__(self) -> str:
        """Custom repr that masks sensitive credentials."""
        # Mask the access token for security
        masked_token = self.access_token[:4] + "****" if len(self.access_token) > 4 else "****"
        return (
            f"WebflowConfig(access_token='{masked_token}', "
            f"site_id='{self.site_id}', collection_id='{self.collection_id}', "
            f"base_url='{self.base_url}', user_agent='{self.user_agent}')"
        )

    @classmethod
    def from_env(cls) -> Optional["WebflowConfig"]:
        """
        Create config from environment variables.
        
        Environment variables:
        - WEBFLOW_ACCESS_TOKEN: API token (required)
        - WEBFLOW_SITE_ID: Site ID (required)
        - WEBFLOW_COLLECTION_ID: Collection ID (required)
        
        Returns:
            WebflowConfig instance if all env vars present, None otherwise
        """
        import os
        access_token = os.environ.get("WEBFLOW_ACCESS_TOKEN", "")
        site_id = os.environ.get("WEBFLOW_SITE_ID", "")
        collection_id = os.environ.get("WEBFLOW_COLLECTION_ID", "")
        
        # Only create if we have all required credentials
        if access_token and site_id and collection_id:
            return cls(
                access_token=access_token,
                site_id=site_id,
                collection_id=collection_id,
            )
        return None
