"""
Google Search Console configuration for the SEO Agent.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class GoogleSearchConsoleConfig:
    """Configuration for Google Search Console API integration."""

    credentials_path: Path

    # Must exactly match the property registered in Search Console.
    # Domain property:  "sc-domain:nocodeassistant.agency"
    # URL-prefix:       "https://www.nocodeassistant.agency/"
    site_url: str

    app_name: str = "SEO-Agent"

    def __post_init__(self):
        if isinstance(self.credentials_path, str):
            self.credentials_path = Path(self.credentials_path)
        if not self.credentials_path.exists():
            raise FileNotFoundError(
                f"GSC credentials file not found: {self.credentials_path}"
            )

    def __repr__(self) -> str:
        return (
            f"GoogleSearchConsoleConfig(credentials_path={self.credentials_path.name}, "
            f"site_url='{self.site_url}')"
        )

    @classmethod
    def from_env(cls) -> Optional["GoogleSearchConsoleConfig"]:
        """
        Create config from environment variables.

        Reads GOOGLE_APPLICATION_CREDENTIALS (or GOOGLE_DOCS_CREDENTIALS_PATH) and GSC_SITE_URL.
        Returns None if either is missing.
        """
        credentials_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or os.environ.get(
            "GOOGLE_DOCS_CREDENTIALS_PATH"
        )
        site_url = os.environ.get("GSC_SITE_URL")
        if credentials_path and site_url:
            return cls(credentials_path=credentials_path, site_url=site_url)
        return None
