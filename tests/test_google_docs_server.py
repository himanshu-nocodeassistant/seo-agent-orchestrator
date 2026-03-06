"""
Tests for Google Docs MCP server.

Red/Green TDD - These tests should FAIL initially (Red),
then pass when server.py is implemented (Green).
"""

import pytest
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock


class TestGoogleDocsServer:
    """Test MCP server creation."""

    @pytest.fixture
    def credentials_path(self):
        """Return path to test credentials."""
        return Path(__file__).parent.parent / "Google SA Credentials" / "tinyclaw-487419-d5ab318833bb.json"

    def test_server_module_exists(self):
        """Test server module can be imported."""
        from agent.google_docs import server
        
        assert server is not None

    def test_create_google_docs_server_function_exists(self):
        """Test create_google_docs_server function exists."""
        from agent.google_docs import create_google_docs_server
        
        assert callable(create_google_docs_server)

    def test_create_server_returns_mcp_server(self, credentials_path):
        """Test create_google_docs_server returns an MCP server."""
        from agent.google_docs import GoogleDocsConfig, create_google_docs_server
        
        config = GoogleDocsConfig(credentials_path=credentials_path)
        mcp_server = create_google_docs_server(config)
        
        # Should return an MCP server object
        assert mcp_server is not None

    def test_server_has_tools(self, credentials_path):
        """Test server has Google Docs tools."""
        from agent.google_docs import GoogleDocsConfig, create_google_docs_server
        
        config = GoogleDocsConfig(credentials_path=credentials_path)
        mcp_server = create_google_docs_server(config)
        
        # Should return an MCP server object
        assert mcp_server is not None
        # Server wrapper should have 'name' key or attribute
        assert mcp_server.get('name') == 'google-docs' or getattr(mcp_server, 'name', None) == 'google-docs'


class TestGoogleDocsAgentIntegration:
    """Test integration with AgentConfig."""

    def test_agent_config_from_env_no_google_docs(self, monkeypatch):
        """Test AgentConfig without Google Docs env vars."""
        monkeypatch.delenv("GOOGLE_DOCS_CREDENTIALS_PATH", raising=False)
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        
        from agent.config import AgentConfig
        
        config = AgentConfig.from_env()
        
        assert config.google_docs_config is None

    def test_agent_config_from_env_with_google_docs(self, monkeypatch):
        """Test AgentConfig with Google Docs env vars."""
        monkeypatch.setenv("GOOGLE_DOCS_CREDENTIALS_PATH", "Google SA Credentials/tinyclaw-487419-d5ab318833bb.json")
        
        from agent.config import AgentConfig
        
        config = AgentConfig.from_env()
        
        assert config.google_docs_config is not None

    def test_agent_config_google_docs_none_by_default(self):
        """Test AgentConfig has no Google Docs by default."""
        from agent.config import AgentConfig
        
        config = AgentConfig()
        
        assert config.google_docs_config is None

    def test_agent_config_mcp_servers_google_docs(self, monkeypatch):
        """Test that Google Docs MCP server is added when configured."""
        monkeypatch.setenv("GOOGLE_DOCS_CREDENTIALS_PATH", "Google SA Credentials/tinyclaw-487419-d5ab318833bb.json")
        
        from agent.config import AgentConfig
        
        config = AgentConfig.from_env()
        
        # MCP server should be set up
        assert "google_docs" in config.mcp_servers

    def test_google_docs_tools_in_allowed_tools(self, monkeypatch):
        """Test that Google Docs tools are added to allowed_tools."""
        monkeypatch.setenv("GOOGLE_DOCS_CREDENTIALS_PATH", "Google SA Credentials/tinyclaw-487419-d5ab318833bb.json")
        
        from agent.config import AgentConfig
        
        config = AgentConfig.from_env()
        
        # Check Google Docs tool names are in allowed_tools
        google_docs_tools = [t for t in config.allowed_tools if 'google_docs' in t]
        assert len(google_docs_tools) >= 4  # All 4 tools should be added


class TestGoogleDocsServerAsync:
    """Test async server creation."""

    @pytest.fixture
    def credentials_path(self):
        """Return path to test credentials."""
        return Path(__file__).parent.parent / "Google SA Credentials" / "tinyclaw-487419-d5ab318833bb.json"

    @pytest.mark.asyncio
    async def test_create_server_async(self, credentials_path):
        """Test async server creation."""
        from agent.google_docs import GoogleDocsConfig
        from agent.google_docs.server import create_google_docs_server_async
        
        config = GoogleDocsConfig(credentials_path=credentials_path)
        server, client = await create_google_docs_server_async(config)
        
        assert server is not None
        assert client is not None
