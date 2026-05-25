"""
Google Docs configuration for the SEO Agent.

This module provides the GoogleDocsConfig dataclass that holds
configuration for interacting with the Google Docs API.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class GoogleDocsConfig:
    """Configuration for Google Docs API integration."""

    # Path to the Google Service Account credentials JSON file
    credentials_path: Path

    # Default folder ID for saving documents (optional)
    folder_id: Optional[str] = None

    # Application name for API requests
    app_name: str = "SEO-Agent"

    def __post_init__(self):
        """Validate configuration after initialization."""
        # Convert string to Path if needed
        if isinstance(self.credentials_path, str):
            self.credentials_path = Path(self.credentials_path)
        
        # Validate credentials file exists
        if not self.credentials_path.exists():
            raise FileNotFoundError(
                f"Google Docs credentials file not found: {self.credentials_path}"
            )
    
    def __repr__(self) -> str:
        """Custom repr that masks sensitive information."""
        return (
            f"GoogleDocsConfig(credentials_path={self.credentials_path.name}, "
            f"folder_id={self.folder_id}, app_name='{self.app_name}')"
        )

    @classmethod
    def from_env(cls) -> Optional["GoogleDocsConfig"]:
        """
        Create config from environment variables.
        
        Environment variables:
        - GOOGLE_DOCS_CREDENTIALS_PATH: Path to credentials JSON file
        - GOOGLE_APPLICATION_CREDENTIALS: Alternative env var (same purpose)
        
        Returns:
            GoogleDocsConfig instance if credentials path present, None otherwise
        """
        # Check for credentials path in environment
        credentials_path = os.environ.get("GOOGLE_DOCS_CREDENTIALS_PATH")
        
        # Fall back to GOOGLE_APPLICATION_CREDENTIALS if not set
        if not credentials_path:
            credentials_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        
        # Only create if we have a credentials path
        if credentials_path:
            return cls(credentials_path=credentials_path)
        
        return None
