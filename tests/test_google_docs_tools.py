"""
Tests for Google Docs MCP tools.

Red/Green TDD - These tests should FAIL initially (Red),
then pass when tools.py is implemented (Green).

NOTE: No delete tool - documents cannot be deleted by design.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock


class TestGoogleDocsTools:
    """Test MCP tools for Google Docs."""

    @pytest.fixture
    def credentials_path(self):
        """Return path to test credentials."""
        return Path(__file__).parent.parent / "Google SA Credentials" / "tinyclaw-487419-d5ab318833bb.json"

    @pytest.fixture
    def client(self, credentials_path):
        """Create mock client."""
        from agent.google_docs import GoogleDocsConfig, GoogleDocsAPIClient
        
        config = GoogleDocsConfig(credentials_path=credentials_path)
        return GoogleDocsAPIClient(config)

    def test_tools_module_exists(self):
        """Test tools module can be imported."""
        from agent.google_docs import tools
        
        assert tools is not None

    def test_set_client_function_exists(self):
        """Test set_client function exists."""
        from agent.google_docs import set_client
        
        assert callable(set_client)

    def test_get_client_function_exists(self):
        """Test get_client function exists."""
        from agent.google_docs import get_client
        
        assert callable(get_client)

    def test_google_docs_tools_list_exists(self):
        """Test GOOGLE_DOCS_TOOLS list exists."""
        from agent.google_docs import GOOGLE_DOCS_TOOLS
        
        assert isinstance(GOOGLE_DOCS_TOOLS, list)
        assert len(GOOGLE_DOCS_TOOLS) > 0

    def test_create_document_tool_exists(self):
        """Test create_document tool exists."""
        from agent.google_docs import GOOGLE_DOCS_TOOLS
        
        tool_names = [t.name for t in GOOGLE_DOCS_TOOLS]
        assert any('create' in name.lower() for name in tool_names)

    def test_get_document_tool_exists(self):
        """Test get_document tool exists."""
        from agent.google_docs import GOOGLE_DOCS_TOOLS
        
        tool_names = [t.name for t in GOOGLE_DOCS_TOOLS]
        assert any('get' in name.lower() for name in tool_names)

    def test_append_content_tool_exists(self):
        """Test append_content tool exists."""
        from agent.google_docs import GOOGLE_DOCS_TOOLS
        
        tool_names = [t.name for t in GOOGLE_DOCS_TOOLS]
        assert any('append' in name.lower() for name in tool_names)

    def test_no_delete_tool_in_list(self):
        """Test that NO delete tool exists (by design)."""
        from agent.google_docs import GOOGLE_DOCS_TOOLS
        
        tool_names = [t.name for t in GOOGLE_DOCS_TOOLS]
        assert not any('delete' in name.lower() for name in tool_names)


class TestCreateDocumentTool:
    """Test create_document tool function."""

    @pytest.fixture
    def credentials_path(self):
        """Return path to test credentials."""
        return Path(__file__).parent.parent / "Google SA Credentials" / "tinyclaw-487419-d5ab318833bb.json"

    def test_create_document_tool_exists(self):
        """Test create_document tool is defined."""
        from agent.google_docs.tools import create_document
        assert create_document is not None


class TestAppendContentTool:
    """Test append_content tool function."""

    @pytest.fixture
    def credentials_path(self):
        """Return path to test credentials."""
        return Path(__file__).parent.parent / "Google SA Credentials" / "tinyclaw-487419-d5ab318833bb.json"

    def test_append_content_tool_exists(self):
        """Test append_content tool is defined."""
        from agent.google_docs.tools import append_content
        assert append_content is not None


class TestGetDocumentTool:
    """Test get_document tool function."""

    @pytest.fixture
    def credentials_path(self):
        """Return path to test credentials."""
        return Path(__file__).parent.parent / "Google SA Credentials" / "tinyclaw-487419-d5ab318833bb.json"

    def test_get_document_tool_exists(self):
        """Test get_document tool is defined."""
        from agent.google_docs.tools import get_document
        assert get_document is not None


class TestToolErrors:
    """Test error handling in tools."""

    @pytest.fixture
    def credentials_path(self):
        """Return path to test credentials."""
        return Path(__file__).parent.parent / "Google SA Credentials" / "tinyclaw-487419-d5ab318833bb.json"

    def test_get_client_raises_when_not_initialized(self):
        """Test get_client raises error when not initialized."""
        # Reset the global client
        import agent.google_docs.tools as tools_module
        tools_module._google_docs_client = None
        
        from agent.google_docs.tools import get_client
        
        # Should raise RuntimeError when client not set
        with pytest.raises(RuntimeError):
            get_client()
