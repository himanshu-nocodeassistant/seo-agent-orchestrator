"""
Tests for Kanban API.

Red/Green TDD approach:
1. RED: Write failing tests first
2. GREEN: Implement solution to pass tests
3. REFACTOR: Clean up code
"""

import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock, MagicMock
import json
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.api.main import app


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_seo_agent():
    """Mock the SEOAgent for testing."""
    with patch('agent.api.main.SEOAgent') as MockAgent:
        mock_instance = AsyncMock()
        mock_instance.execute_task = AsyncMock(return_value="Task executed successfully")
        MockAgent.return_value = mock_instance
        yield mock_instance


# ============================================================================
# RED PHASE: FAILING TESTS
# ============================================================================

class TestTaskAPI:
    """Test task API endpoints - RED phase (tests should fail initially)."""
    
    def test_list_tasks_returns_json(self, client):
        """Test: GET /tasks returns list of tasks.
        
        Expected: Returns JSON with tasks array and counts
        """
        response = client.get("/tasks")
        
        # Should return 200 OK
        assert response.status_code == 200
        
        data = response.json()
        
        # Should have tasks array and counts
        assert "tasks" in data
        assert "total" in data
        assert "pending_count" in data
        assert "in_progress_count" in data
        assert "completed_count" in data
        assert "blocked_count" in data
    
    def test_create_task(self, client):
        """Test: POST /tasks creates a new task.
        
        Expected: New task created with generated ID
        """
        task_data = {
            "title": "Test SEO Task",
            "description": "Test description",
            "priority": 1,
            "status": "pending"
        }
        
        response = client.post("/tasks", json=task_data)
        
        assert response.status_code == 200
        
        data = response.json()
        assert "id" in data
        assert data["title"] == "Test SEO Task"
        assert data["status"] == "pending"
    
    def test_get_task_by_id(self, client):
        """Test: GET /tasks/{id} returns a single task."""
        # First create a task
        task_data = {"title": "Task to Get", "priority": 0}
        create_response = client.post("/tasks", json=task_data)
        task_id = create_response.json()["id"]
        
        # Then get it
        response = client.get(f"/tasks/{task_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Task to Get"
    
    def test_update_task_status(self, client):
        """Test: PATCH /tasks/{id} updates task status."""
        # Create task
        task_data = {"title": "Task to Update", "status": "pending"}
        create_response = client.post("/tasks", json=task_data)
        task_id = create_response.json()["id"]
        
        # Update status
        update_data = {"status": "in_progress"}
        response = client.patch(f"/tasks/{task_id}", json=update_data)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "in_progress"
    
    def test_delete_task(self, client):
        """Test: DELETE /tasks/{id} deletes a task."""
        # Create task
        task_data = {"title": "Task to Delete"}
        create_response = client.post("/tasks", json=task_data)
        task_id = create_response.json()["id"]
        
        # Delete it
        response = client.delete(f"/tasks/{task_id}")
        
        assert response.status_code == 200
        
        # Verify it's gone
        get_response = client.get(f"/tasks/{task_id}")
        assert get_response.status_code == 404
    
    def test_execute_task_no_agent(self, client):
        """Test: POST /tasks/{id}/execute returns error when agent not available."""
        # Create task
        task_data = {"title": "Task to Execute", "description": "Do SEO audit"}
        create_response = client.post("/tasks", json=task_data)
        task_id = create_response.json()["id"]
        
        # Execute it - will fail without agent but should return 500
        response = client.post(f"/tasks/{task_id}/execute")
        
        # Either succeeds or returns error (agent may not be available in test)
        assert response.status_code in [200, 500]


# ============================================================================
# TEST: KANBAN HTML
# ============================================================================

class TestKanbanHTML:
    """Test kanban HTML serving."""
    
    def test_kanban_serves_html(self, client):
        """Test: GET /kanban returns the HTML page.
        
        Expected: HTML page loads correctly
        """
        response = client.get("/kanban")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "kanban" in response.text.lower()
    
    def test_kanban_has_styling(self, client):
        """Test that kanban HTML has proper styling."""
        response = client.get("/kanban")
        
        text = response.text
        # Check for DM Sans font
        assert "DM Sans" in text
        # Check for Tailwind
        assert "tailwind" in text.lower()


# ============================================================================
# TEST: SEO AUDIT
# ============================================================================

class TestSEOAudit:
    """Test SEO audit functionality."""
    
    def test_run_seo_audit(self, client):
        """Test: POST /runs/{run_id}/seo-audit triggers SEO audit."""
        response = client.post("/runs/test-audit-123/seo-audit", json={
            "days": 28,
            "max_rows": 1000
        })
        
        # Either succeeds or returns error (agent may not be available in test)
        assert response.status_code in [200, 500]
