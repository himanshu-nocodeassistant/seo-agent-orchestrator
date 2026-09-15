"""
Google Search Console configuration for the SEO Agent.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class GscConfig:
    """Configuration for Google Search Console API integration."""

    # The property URL as it appears in GSC.
    # Format: "sc-domain:example.com" (domain property)
    #      or "https://www.example.com/" (URL-prefix property)
    site_url: str

    # Path to Google Service Account credentials JSON file.
    # The same SA credential used for Google Docs works here —
    # just grant it access to the GSC property in Search Console settings.
    credentials_path: Path

    def __post_init__(self):
        if isinstance(self.credentials_path, str):
            self.credentials_path = Path(self.credentials_path)

        if not self.credentials_path.exists():
            raise FileNotFoundError(
                f"GSC credentials file not found: {self.credentials_path}"
            )

        if not self.site_url:
            raise ValueError("GSC site_url must not be empty.")

    def __repr__(self) -> str:
        return (
            f"GscConfig(site_url={self.site_url!r}, "
            f"credentials_path={self.credentials_path.name!r})"
        )

    @classmethod
    def from_env(cls) -> Optional["GscConfig"]:
        """
        Create config from environment variables.

        Environment variables:
        - GSC_SITE_URL: The GSC property URL (required)
        - GSC_CREDENTIALS_PATH: Path to service account JSON (optional,
          falls back to GOOGLE_DOCS_CREDENTIALS_PATH then
          GOOGLE_APPLICATION_CREDENTIALS)

        Returns:
            GscConfig instance, or None if GSC_SITE_URL is not set.
        """
        site_url = os.environ.get("GSC_SITE_URL")
        if not site_url:
            return None

        credentials_path = (
            os.environ.get("GSC_CREDENTIALS_PATH")
            or os.environ.get("GOOGLE_DOCS_CREDENTIALS_PATH")
            or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        )
        if not credentials_path:
            return None

        return cls(site_url=site_url, credentials_path=credentials_path)
