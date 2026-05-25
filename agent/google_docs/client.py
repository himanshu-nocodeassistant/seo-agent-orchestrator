"""
Google Docs API Client for the SEO Agent.

This module provides the GoogleDocsAPIClient class that wraps
the Google Docs API for document operations.
"""

import logging
from typing import Any, Optional

from google.oauth2 import service_account
from googleapiclient import discovery

from .config import GoogleDocsConfig

logger = logging.getLogger(__name__)


class GoogleDocsAPIError(Exception):
    """Exception raised for Google Docs API errors."""

    def __init__(self, message: str, status: int = 0, response: Optional[dict] = None):
        super().__init__(message)
        self.status = status
        self.response = response


class GoogleDocsAPIClient:
    """
    Async client for Google Docs API.

    Provides methods for document operations:
    - create_document: Create a new document
    - get_document: Get document by ID
    - append_content: Add text to existing document
    - list_documents: List user's documents: No delete method
    
    NOTE - documents cannot be deleted by design.
    """

    def __init__(self, config: GoogleDocsConfig):
        """Initialize the Google Docs API client."""
        self.config = config
        self._service: Optional[Any] = None

    async def _get_service(self) -> Any:
        """
        Get or build the Google Docs service.
        
        Returns:
            Google Docs service instance
        """
        if self._service is None:
            # Validate credentials file exists before attempting to load
            self.config.validate()
            # Load credentials from service account JSON file
            credentials = service_account.Credentials.from_service_account_file(
                str(self.config.credentials_path),
                scopes=['https://www.googleapis.com/auth/documents']
            )
            
            # Build the service
            self._service = discovery.build(
                'docs',
                'v1',
                credentials=credentials,
                cache_discovery=False
            )
        
        return self._service

    async def close(self):
        """Close the client and cleanup resources."""
        # Google API client doesn't require explicit cleanup
        self._service = None

    # -------------------------------------------------------------------------
    # Document Operations (NO DELETE - by design)
    # -------------------------------------------------------------------------

    async def create_document(
        self,
        title: str,
        content: str = ""
    ) -> dict[str, Any]:
        """
        Create a new Google Doc.

        Args:
            title: Document title
            content: Initial content (optional)

        Returns:
            Dict with documentId and title
        """
        service = await self._get_service()
        
        try:
            # Create empty document
            document = service.documents().create(
                body={'title': title}
            ).execute()
            
            document_id = document.get('documentId')
            
            # If initial content provided, add it
            if content and document_id:
                await self.append_content(document_id, content)
                # Fetch the updated document
                document = await self.get_document(document_id)
            
            return document
            
        except Exception as e:
            logger.error(f"Failed to create document: {e}")
            raise GoogleDocsAPIError(f"Failed to create document: {e}")

    async def get_document(self, document_id: str) -> dict[str, Any]:
        """
        Get a document by ID.

        Args:
            document_id: The document's unique identifier

        Returns:
            Document data as dict
        """
        service = await self._get_service()
        
        try:
            document = service.documents().get(
                documentId=document_id
            ).execute()
            
            return document
            
        except Exception as e:
            logger.error(f"Failed to get document: {e}")
            raise GoogleDocsAPIError(f"Failed to get document: {e}")

    async def append_content(
        self,
        document_id: str,
        text: str
    ) -> dict[str, Any]:
        """
        Append text to a document.

        Args:
            document_id: The document's unique identifier
            text: Text to append

        Returns:
            Batch update response
        """
        service = await self._get_service()
        
        try:
            # First, get the document to find the end index
            document = await self.get_document(document_id)
            
            # Find the end of the document body
            end_index = 1
            if document.get('body', {}).get('content'):
                last_element = document['body']['content'][-1]
                if 'paragraph' in last_element:
                    end_index = last_element.get('endIndex', 1)
                elif 'table' in last_element:
                    # If there's a table, get its end index
                    end_index = last_element.get('endIndex', 1)
            
            # Append the text using batchUpdate
            requests = [
                {
                    'insertText': {
                        'location': {
                            'index': end_index - 1
                        },
                        'text': text
                    }
                }
            ]
            
            result = service.documents().batchUpdate(
                documentId=document_id,
                body={'requests': requests}
            ).execute()
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to append content: {e}")
            raise GoogleDocsAPIError(f"Failed to append content: {e}")

    async def list_documents(
        self,
        page_size: int = 10
    ) -> dict[str, Any]:
        """
        List the user's Google Docs.

        Note: This uses the Drive API to list documents since
        Google Docs API doesn't have a direct list method.

        Args:
            page_size: Number of documents to return

        Returns:
            Dict with documents array
        """
        # Note: For full implementation, would need Drive API
        # This is a placeholder that returns empty results
        # In production, you would add Drive API scope and use files().list()
        return {'documents': []}

    async def update_title(
        self,
        document_id: str,
        title: str
    ) -> dict[str, Any]:
        """
        Update document title.

        Args:
            document_id: The document's unique identifier
            title: New title

        Returns:
            Updated document
        """
        service = await self._get_service()
        
        try:
            requests = [
                {
                    'updateDocumentTitle': {
                        'title': title
                    }
                }
            ]
            
            result = service.documents().batchUpdate(
                documentId=document_id,
                body={'requests': requests}
            ).execute()
            
            return await self.get_document(document_id)
            
        except Exception as e:
            logger.error(f"Failed to update title: {e}")
            raise GoogleDocsAPIError(f"Failed to update title: {e}")
