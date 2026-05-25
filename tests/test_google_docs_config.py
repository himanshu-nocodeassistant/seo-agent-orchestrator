"""
Tests for Google Docs configuration.

Red/Green TDD - These tests should FAIL initially (Red),
then pass when config.py is implemented (Green).
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestGoogleDocsConfig:
    """Test GoogleDocsConfig dataclass."""

    def test_google_docs_config_missing_credentials_path(self, monkeypatch):
        """Test GoogleDocsConfig returns None from_env when credentials path is missing."""
        monkeypatch.delenv("GOOGLE_DOCS_CREDENTIALS_PATH", raising=False)
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)

        from agent.google_docs import GoogleDocsConfig

        # Should return None when no credentials path is set
        config = GoogleDocsConfig.from_env()
        assert config is None

    def test_google_docs_config_from_env(self, monkeypatch):
        """Test GoogleDocsConfig creates from environment variable without requiring file to exist."""
        monkeypatch.setenv("GOOGLE_DOCS_CREDENTIALS_PATH", "Google SA Credentials/your-service-account.json")

        from agent.google_docs import GoogleDocsConfig

        config = GoogleDocsConfig.from_env()

        assert config is not None
        assert "your-service-account.json" in str(config.credentials_path)

    def test_google_docs_config_validation_missing_file(self):
        """Test GoogleDocsConfig.validate() raises FileNotFoundError for missing file."""
        from agent.google_docs import GoogleDocsConfig

        # Construction succeeds even if file doesn't exist
        config = GoogleDocsConfig(credentials_path="nonexistent/credentials.json")
        assert config is not None

        # validate() raises when file is missing
        with pytest.raises(FileNotFoundError):
            config.validate()

    def test_google_docs_config_with_placeholder_credentials(self, monkeypatch):
        """Test GoogleDocsConfig constructs successfully with a placeholder path."""
        monkeypatch.setenv("GOOGLE_DOCS_CREDENTIALS_PATH", "Google SA Credentials/your-service-account.json")

        from agent.google_docs import GoogleDocsConfig

        config = GoogleDocsConfig.from_env()

        assert config is not None
        assert config.credentials_path.name == "your-service-account.json"

    def test_google_docs_config_masked_in_repr(self, monkeypatch):
        """Test that sensitive data is masked in repr."""
        monkeypatch.setenv("GOOGLE_DOCS_CREDENTIALS_PATH", "Google SA Credentials/your-service-account.json")

        from agent.google_docs import GoogleDocsConfig

        config = GoogleDocsConfig.from_env()
        repr_str = repr(config)

        # Should not expose full path details inappropriately
        assert "GoogleDocsConfig" in repr_str


class TestGoogleDocsConfigImports:
    """Test that config can be imported properly."""

    def test_import_google_docs_config(self):
        """Test GoogleDocsConfig can be imported."""
        from agent.google_docs import GoogleDocsConfig

        assert GoogleDocsConfig is not None

    def test_google_docs_config_is_dataclass(self):
        """Test GoogleDocsConfig is a dataclass."""
        from agent.google_docs import GoogleDocsConfig

        # Should construct without file existing
        config = GoogleDocsConfig(
            credentials_path=Path("Google SA Credentials/your-service-account.json")
        )

        assert hasattr(config, 'credentials_path')
