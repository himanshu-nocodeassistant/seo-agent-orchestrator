"""
Tests for Google Docs API client.

Red/Green TDD - These tests should FAIL initially (Red),
then pass when client.py is implemented (Green).
"""

import pytest
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock


class TestGoogleDocsClient:
    """Test GoogleDocsAPIClient class."""

    @pytest.fixture
    def credentials_path(self, fake_credentials_path):
        """Return path to test credentials."""
        return fake_credentials_path

    def test_google_docs_client_initialization(self, credentials_path):
        """Test GoogleDocsAPIClient can be initialized."""
        from agent.google_docs import GoogleDocsConfig, GoogleDocsAPIClient
        
        config = GoogleDocsConfig(credentials_path=credentials_path)
        client = GoogleDocsAPIClient(config)
        
        assert client.config == config
        assert client._service is None  # Not created until used

    def test_google_docs_client_has_config(self, credentials_path):
        """Test client stores config."""
        from agent.google_docs import GoogleDocsConfig, GoogleDocsAPIClient
        
        config = GoogleDocsConfig(credentials_path=credentials_path)
        client = GoogleDocsAPIClient(config)
        
        assert hasattr(client, 'config')
        assert client.config.credentials_path == credentials_path

    def test_google_docs_api_error_exists(self):
        """Test GoogleDocsAPIError exception exists."""
        from agent.google_docs import GoogleDocsAPIError
        
        error = GoogleDocsAPIError("Test error")
        assert str(error) == "Test error"

    def test_google_docs_api_error_with_status(self):
        """Test GoogleDocsAPIError can store status code."""
        from agent.google_docs import GoogleDocsAPIError
        
        error = GoogleDocsAPIError("API Error", status=404)
        assert error.status == 404


class TestGoogleDocsClientOperations:
    """Test document operations (NO delete - by design)."""

    @pytest.fixture
    def credentials_path(self, fake_credentials_path):
        """Return path to test credentials."""
        return fake_credentials_path

    @pytest.fixture
    def client(self, credentials_path):
        """Create client instance."""
        from agent.google_docs import GoogleDocsConfig, GoogleDocsAPIClient
        
        config = GoogleDocsConfig(credentials_path=credentials_path)
        return GoogleDocsAPIClient(config)

    def test_client_has_create_document_method(self, client):
        """Test client has create_document method."""
        assert hasattr(client, 'create_document')
        assert callable(client.create_document)

    def test_client_has_get_document_method(self, client):
        """Test client has get_document method."""
        assert hasattr(client, 'get_document')
        assert callable(client.get_document)

    def test_client_has_append_content_method(self, client):
        """Test client has append_content method."""
        assert hasattr(client, 'append_content')
        assert callable(client.append_content)

    def test_client_has_list_documents_method(self, client):
        """Test client has list_documents method."""
        assert hasattr(client, 'list_documents')
        assert callable(client.list_documents)

    def test_client_does_not_have_delete_method(self, client):
        """Test client does NOT have delete method (by design)."""
        assert not hasattr(client, 'delete_document')


class TestGoogleDocsClientAsync:
    """Test async operations."""

    @pytest.fixture
    def credentials_path(self, fake_credentials_path):
        """Return path to test credentials."""
        return fake_credentials_path

    @pytest.mark.asyncio
    async def test_client_can_build_service(self, credentials_path):
        """Test client can build Google Docs service."""
        from agent.google_docs import GoogleDocsConfig, GoogleDocsAPIClient
        import agent.google_docs.client as client_module
        
        config = GoogleDocsConfig(credentials_path=credentials_path)
        client = GoogleDocsAPIClient(config)
        
        mock_service = MagicMock()
        with patch.object(
            client_module.service_account.Credentials,
            "from_service_account_file",
            return_value=MagicMock(),
        ), patch.object(
            client_module.discovery,
            "build",
            return_value=mock_service,
        ) as mock_build:
            service = await client._get_service()

        assert service is mock_service
        mock_build.assert_called_once()
        assert mock_build.call_args.kwargs.get("num_retries") == 3

    @pytest.mark.asyncio
    async def test_create_document_returns_doc_id(self, credentials_path):
        """Test create_document method exists and returns dict."""
        from agent.google_docs import GoogleDocsConfig, GoogleDocsAPIClient
        
        config = GoogleDocsConfig(credentials_path=credentials_path)
        client = GoogleDocsAPIClient(config)
        
        # Test that create_document method exists and is callable
        assert hasattr(client, 'create_document')
        assert callable(client.create_document)

    @pytest.mark.asyncio
    async def test_append_content_to_document(self, credentials_path):
        """Test append_content adds text to document."""
        from agent.google_docs import GoogleDocsConfig, GoogleDocsAPIClient
        
        config = GoogleDocsConfig(credentials_path=credentials_path)
        client = GoogleDocsAPIClient(config)
        
        with patch.object(client, '_get_service') as mock_get_service:
            mock_service = MagicMock()
            # Mock the documents().batchUpdate response
            mock_service.documents.return_value.batchUpdate.return_value.execute.return_value = {
                'replies': [{'insertText': {'endIndex': 100}}]
            }
            mock_get_service.return_value = mock_service
            
            result = await client.append_content(
                document_id="test-doc-123",
                text="Additional content"
            )
            
            assert result is not None
            # Verify batchUpdate was called
            mock_service.documents.return_value.batchUpdate.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_document_returns_content(self, credentials_path):
        """Test get_document returns document content."""
        from agent.google_docs import GoogleDocsConfig, GoogleDocsAPIClient
        
        config = GoogleDocsConfig(credentials_path=credentials_path)
        client = GoogleDocsAPIClient(config)
        
        with patch.object(client, '_get_service') as mock_get_service:
            mock_service = MagicMock()
            mock_service.documents.return_value.get.return_value.execute.return_value = {
                'documentId': 'test-doc-123',
                'title': 'Test Doc',
                'body': {'content': []}
            }
            mock_get_service.return_value = mock_service
            
            result = await client.get_document(document_id="test-doc-123")
            
            assert result['documentId'] == 'test-doc-123'


class TestGoogleDocsServiceAccount:
    """Test service account authentication."""

    @pytest.fixture
    def credentials_path(self, fake_credentials_path):
        """Return path to test credentials."""
        return fake_credentials_path

    @pytest.mark.asyncio
    async def test_service_uses_credentials(self, credentials_path):
        """Test that service uses credentials from config."""
        from agent.google_docs import GoogleDocsConfig, GoogleDocsAPIClient
        
        config = GoogleDocsConfig(credentials_path=credentials_path)
        client = GoogleDocsAPIClient(config)
        
        # Verify credentials path is set
        assert str(credentials_path) in str(client.config.credentials_path)
