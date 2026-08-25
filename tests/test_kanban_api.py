"""
Tests for Kanban API.

Red/Green TDD approach:
1. RED: Write failing tests first
2. GREEN: Implement solution to pass tests
3. REFACTOR: Clean up code
"""

import pytest
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock
import json
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))


# ============================================================================
# FIXTURES
# ============================================================================


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

    def test_list_tasks_sorted_by_recently_updated_first(self, client):
        """Test: GET /tasks returns tasks sorted by updated_at DESC."""
        older = client.post("/tasks", json={"title": "Older Task", "status": "pending"}).json()
        newer = client.post("/tasks", json={"title": "Newer Task", "status": "pending"}).json()

        # Touch the older task so it becomes most recently updated.
        client.patch(f"/tasks/{older['id']}", json={"status": "in_progress"})

        response = client.get("/tasks")
        assert response.status_code == 200
        tasks = response.json()["tasks"]

        older_index = next(i for i, t in enumerate(tasks) if t["id"] == older["id"])
        newer_index = next(i for i, t in enumerate(tasks) if t["id"] == newer["id"])
        assert older_index < newer_index
    
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
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, patch

        with patch(
            "agent.api.helpers._run_agent_prompt",
            new=AsyncMock(
                return_value=SimpleNamespace(
                    result_text=(
                        "Audit complete. Top keyword: no-code. "
                        "Source: https://example.com/audit"
                    ),
                    session_id=None,
                )
            ),
        ):
            response = client.post(
                "/runs/test-audit-123/seo-audit",
                json={"days": 28, "max_rows": 1000},
            )

        assert response.status_code == 200
        assert response.json()["task_id"]

        task = client.get(f"/tasks/{response.json()['task_id']}").json()
        assert task["status"] == "completed"
        assert task["execution_type"] == "seo_audit"


# ============================================================================
# TEST: TASK COMMENTS (RED PHASE - Failing Tests)
# ============================================================================

class TestTaskComments:
    """Test task comments functionality - RED phase (tests should fail)."""
    
    def test_execute_task_adds_started_comment(self, client):
        """Test: When task starts executing, a comment is added."""
        # Create task
        task_data = {"title": "Test SEO Task", "description": "Do research", "execution_type": "research"}
        create_response = client.post("/tasks", json=task_data)
        task_id = create_response.json()["id"]
        
        # Execute task (may succeed or fail, but should add comments)
        client.post(f"/tasks/{task_id}/execute")
        
        # Check that comments were added
        comments_response = client.get(f"/tasks/{task_id}/comments")
        comments = comments_response.json()
        
        # Should have at least one comment about task starting
        started_comments = [c for c in comments if "started" in c["body"].lower() or "executing" in c["body"].lower() or "🤖" in c["body"]]
        assert len(started_comments) > 0, f"Task should add a comment when starting. Got comments: {comments}"
    
    def test_execute_task_adds_completion_comment(self, client):
        """Test: When task completes, a completion comment is added."""
        # Create task
        task_data = {"title": "Test Task", "description": "Do something", "execution_type": "research"}
        create_response = client.post("/tasks", json=task_data)
        task_id = create_response.json()["id"]
        
        # Execute task
        client.post(f"/tasks/{task_id}/execute")
        
        # Check comments
        comments_response = client.get(f"/tasks/{task_id}/comments")
        comments = comments_response.json()
        
        # Check task status to determine what comment to expect
        task_response = client.get(f"/tasks/{task_id}")
        task = task_response.json()
        
        if task["status"] == "completed":
            # Should have completion comment
            completion_comments = [c for c in comments if "completed" in c["body"].lower() or "done" in c["body"].lower() or "✅" in c["body"]]
            assert len(completion_comments) > 0, f"Task should add a completion comment. Got comments: {comments}"
        elif task["status"] == "blocked":
            # Should have failure comment
            error_comments = [c for c in comments if "failed" in c["body"].lower() or "error" in c["body"].lower() or "❌" in c["body"]]
            assert len(error_comments) > 0, f"Failed task should add an error comment. Got comments: {comments}"
        else:
            # Any status is fine as long as we have agent comments
            assert len(comments) > 0, f"Task should add some comment. Got comments: {comments}"
    
    def test_execute_task_adds_failure_comment(self, client):
        """Test: When task fails, an error comment is added."""
        # Use a valid task type. The unavailable agent path should fail safely.
        task_data = {"title": "Failing Task", "description": "Will fail", "execution_type": "research"}
        create_response = client.post("/tasks", json=task_data)
        task_id = create_response.json()["id"]
        
        # Execute - should fail
        client.post(f"/tasks/{task_id}/execute")
        
        # Get comments
        comments_response = client.get(f"/tasks/{task_id}/comments")
        comments = comments_response.json()
        
        # Check task status
        task_response = client.get(f"/tasks/{task_id}")
        task = task_response.json()
        
        # Should have error comment
        error_comments = [c for c in comments if "error" in c["body"].lower() or "failed" in c["body"].lower() or "❌" in c["body"]]
        assert len(error_comments) > 0, f"Failed task should add an error comment. Status: {task['status']}, Comments: {comments}"
    
    def test_comment_count_increments_on_execute(self, client):
        """Test: comment_count increases when agent adds comments."""
        # Create task
        task_data = {"title": "Test Task", "description": "Do work", "execution_type": "research"}
        create_response = client.post("/tasks", json=task_data)
        task_id = create_response.json()["id"]
        initial_count = create_response.json()["comment_count"]
        
        # Execute task
        client.post(f"/tasks/{task_id}/execute")
        
        # Check comment count increased
        task_response = client.get(f"/tasks/{task_id}")
        updated_count = task_response.json()["comment_count"]
        
        assert updated_count > initial_count, f"Comment count should increase after execution. Initial: {initial_count}, Updated: {updated_count}"
    
    def test_get_comments_returns_agent_comments(self, client):
        """Test: GET /tasks/{id}/comments returns agent-authored comments."""
        # Create and execute a task
        task_data = {"title": "Agent Test", "description": "Test", "execution_type": "research"}
        create_response = client.post("/tasks", json=task_data)
        task_id = create_response.json()["id"]
        
        client.post(f"/tasks/{task_id}/execute")
        
        # Get comments
        response = client.get(f"/tasks/{task_id}/comments")
        comments = response.json()
        
        # Should have comments from agent (author="agent")
        agent_comments = [c for c in comments if c.get("author") == "agent"]
        assert len(agent_comments) > 0, f"Should have agent-authored comments. Got: {comments}"
    
    def test_multiple_comments_added_on_execution(self, client):
        """Test: Multiple comments are added during task execution (started + completed/failed)."""
        task_data = {"title": "Multi Comment Test", "description": "Test", "execution_type": "research"}
        create_response = client.post("/tasks", json=task_data)
        task_id = create_response.json()["id"]
        
        # Execute task
        client.post(f"/tasks/{task_id}/execute")
        
        # Get comments
        response = client.get(f"/tasks/{task_id}/comments")
        comments = response.json()
        
        # Should have at least 2 comments: started + completed/failed
        assert len(comments) >= 2, f"Should have at least 2 comments. Got: {len(comments)}"
    
    def test_comment_body_contains_task_info(self, client):
        """Test: Comments contain relevant task information."""
        task_data = {"title": "Test Task Title", "description": "Test description", "execution_type": "research"}
        create_response = client.post("/tasks", json=task_data)
        task_id = create_response.json()["id"]
        
        client.post(f"/tasks/{task_id}/execute")
        
        # Get comments
        response = client.get(f"/tasks/{task_id}/comments")
        comments = response.json()
        
        # Check that comments contain expected content
        combined_body = " ".join([c["body"] for c in comments])
        
        # Should contain emoji indicators
        assert "🤖" in combined_body or "❌" in combined_body, f"Should have agent indicator. Got: {combined_body}"
    
    def test_comment_has_valid_timestamp(self, client):
        """Test: Comments have valid created_at timestamps."""
        task_data = {"title": "Timestamp Test", "description": "Test", "execution_type": "research"}
        create_response = client.post("/tasks", json=task_data)
        task_id = create_response.json()["id"]
        
        client.post(f"/tasks/{task_id}/execute")
        
        # Get comments
        response = client.get(f"/tasks/{task_id}/comments")
        comments = response.json()
        
        # Each comment should have a valid ISO timestamp
        for comment in comments:
            assert "created_at" in comment, "Comment should have created_at"
            assert comment["created_at"], "created_at should not be empty"
            # Check it's ISO format (contains T and : for time)
            assert "T" in comment["created_at"], f"Invalid timestamp format: {comment['created_at']}"
    
    def test_comment_count_matches_actual_comments(self, client):
        """Test: task.comment_count matches the number of actual comments."""
        task_data = {"title": "Count Test", "description": "Test", "execution_type": "research"}
        create_response = client.post("/tasks", json=task_data)
        task_id = create_response.json()["id"]
        
        # Execute task
        client.post(f"/tasks/{task_id}/execute")
        
        # Get comments count from task
        task_response = client.get(f"/tasks/{task_id}")
        task = task_response.json()
        
        # Get actual comments
        comments_response = client.get(f"/tasks/{task_id}/comments")
        comments = comments_response.json()
        
        assert task["comment_count"] == len(comments), f"comment_count ({task['comment_count']}) should match actual comments ({len(comments)})"
    
    def test_failure_comment_contains_error_info(self, client):
        """Test: Failed task comments contain error information."""
        # Use a valid task type. The unavailable agent path should fail safely.
        task_data = {"title": "Error Test", "description": "Test", "execution_type": "research"}
        create_response = client.post("/tasks", json=task_data)
        task_id = create_response.json()["id"]
        
        client.post(f"/tasks/{task_id}/execute")
        
        # Get comments
        response = client.get(f"/tasks/{task_id}/comments")
        comments = response.json()
        
        # Should have error/failed comment
        error_comments = [c for c in comments if "error" in c["body"].lower() or "failed" in c["body"].lower()]
        assert len(error_comments) > 0, f"Should have error comment. Got: {comments}"


# ============================================================================
# TEST: COMMENT HELPER FUNCTIONS (Unit Tests)
# ============================================================================

class TestCommentHelperFunctions:
    """Test comment helper functions directly."""
    
    def test_add_task_comment_creates_comment(self, client):
        """Test: add_task_comment helper creates a comment."""
        from agent.api.main import add_task_comment, get_db_session
        
        # Create a task first
        task_data = {"title": "Helper Test", "description": "Test"}
        create_response = client.post("/tasks", json=task_data)
        task_id = create_response.json()["id"]
        
        # Use the helper function
        db = get_db_session()
        comment = add_task_comment(db, task_id, "Test comment body", "user")
        db.close()
        
        # Verify comment was created
        assert comment is not None
        assert comment.body == "Test comment body"
        assert comment.author == "user"
        assert comment.task_id == task_id
    
    def test_add_task_started_comment_format(self, client):
        """Test: add_task_started_comment creates properly formatted comment."""
        from agent.api.main import add_task_started_comment, get_db_session
        
        task_data = {"title": "Format Test", "description": "Test"}
        create_response = client.post("/tasks", json=task_data)
        task_id = create_response.json()["id"]
        
        db = get_db_session()
        comment = add_task_started_comment(db, task_id, "Test Title")
        db.close()
        
        assert comment is not None
        assert "🤖" in comment.body
        assert "started" in comment.body.lower()
        assert comment.author == "agent"
    
    def test_add_task_completed_comment_format(self, client):
        """Test: add_task_completed_comment creates properly formatted comment."""
        from agent.api.main import add_task_completed_comment, get_db_session
        
        task_data = {"title": "Complete Test", "description": "Test"}
        create_response = client.post("/tasks", json=task_data)
        task_id = create_response.json()["id"]
        
        db = get_db_session()
        comment = add_task_completed_comment(db, task_id, "Task result summary")
        db.close()
        
        assert comment is not None
        assert "✅" in comment.body
        assert "completed" in comment.body.lower()
        assert "Task result summary" in comment.body
        assert comment.author == "agent"
    
    def test_add_task_failed_comment_format(self, client):
        """Test: add_task_failed_comment creates properly formatted comment."""
        from agent.api.main import add_task_failed_comment, get_db_session
        
        task_data = {"title": "Fail Test", "description": "Test"}
        create_response = client.post("/tasks", json=task_data)
        task_id = create_response.json()["id"]
        
        db = get_db_session()
        comment = add_task_failed_comment(db, task_id, "Something went wrong")
        db.close()
        
        assert comment is not None
        assert "❌" in comment.body
        assert "failed" in comment.body.lower()
        assert "Something went wrong" in comment.body
        assert comment.author == "agent"
    
    def test_add_google_doc_comment_format(self, client):
        """Test: add_google_doc_comment creates properly formatted comment."""
        from agent.api.main import add_google_doc_comment, get_db_session
        
        task_data = {"title": "Doc Test", "description": "Test"}
        create_response = client.post("/tasks", json=task_data)
        task_id = create_response.json()["id"]
        
        db = get_db_session()
        comment = add_google_doc_comment(db, task_id, "https://docs.google.com/doc123")
        db.close()
        
        assert comment is not None
        assert "📄" in comment.body
        assert "Google Doc" in comment.body
        assert "https://docs.google.com/doc123" in comment.body
        assert comment.author == "agent"
    
    def test_add_subtasks_created_comment_format(self, client):
        """Test: add_subtasks_created_comment creates properly formatted comment."""
        from agent.api.main import add_subtasks_created_comment, get_db_session
        
        task_data = {"title": "Subtask Test", "description": "Test"}
        create_response = client.post("/tasks", json=task_data)
        task_id = create_response.json()["id"]
        
        db = get_db_session()
        comment = add_subtasks_created_comment(db, task_id, 5)
        db.close()
        
        assert comment is not None
        assert "📋" in comment.body
        assert "5" in comment.body
        assert "subtask" in comment.body.lower()
        assert comment.author == "agent"
    
    def test_comment_increments_task_comment_count(self, client):
        """Test: Adding a comment increments the task's comment_count."""
        from agent.api.main import add_task_comment, get_db_session
        
        task_data = {"title": "Increment Test", "description": "Test"}
        create_response = client.post("/tasks", json=task_data)
        task_id = create_response.json()["id"]
        
        # Get initial count
        task_response = client.get(f"/tasks/{task_id}")
        initial_count = task_response.json()["comment_count"]
        
        # Add comment
        db = get_db_session()
        add_task_comment(db, task_id, "Test", "user")
        db.close()
        
        # Verify count incremented
        task_response = client.get(f"/tasks/{task_id}")
        new_count = task_response.json()["comment_count"]
        
        assert new_count == initial_count + 1
