"""Tests for comment-driven autopilot execution."""

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from agent.api.main import (
    CommentActionModel,
    build_comment_revision_prompt,
    get_db_session,
    is_agent_trigger_comment,
    _autopilot_interval_seconds,
)


class TestCommentAutopilotHelpers:
    def test_trigger_detection_requires_user_and_prefix(self):
        assert is_agent_trigger_comment("user", "@agent please revise") is True
        assert is_agent_trigger_comment("user", " @agent revise") is True
        assert is_agent_trigger_comment("agent", "@agent recurse") is False
        assert is_agent_trigger_comment("user", "please revise") is False

    def test_build_revision_prompt_includes_context_and_feedback(self):
        task = SimpleNamespace(
            title="Rewrite title",
            description="Update title with SMB keyword",
            execution_type="rewrite_title",
            notes="Old draft",
        )

        prompt = build_comment_revision_prompt(task, "@agent include retention metric")

        assert "Rewrite title" in prompt
        assert "Old draft" in prompt
        assert "include retention metric" in prompt
        assert "@agent include retention metric" not in prompt


class TestCommentAutopilotAPI:
    def _agent_patches(self, result=None, error=None):
        config_patch = patch(
            "agent.config.AgentConfig.from_env",
            return_value=SimpleNamespace(cwd="", setting_sources=[], system_prompt=""),
        )
        if error is not None:
            run_patch = patch("agent.seo_agent.SEOAgent.create_and_run", new=AsyncMock(side_effect=error))
        else:
            run_patch = patch("agent.seo_agent.SEOAgent.create_and_run", new=AsyncMock(return_value=result))
        return config_patch, run_patch

    def test_process_one_ignores_non_trigger_comments(self, client):
        task = client.post("/tasks", json={"title": "Task A", "status": "completed"}).json()
        client.post(f"/tasks/{task['id']}/comments", json={"author": "user", "body": "please revise"})

        response = client.post("/automation/comments/process-one")
        assert response.status_code == 200
        assert response.json()["processed"] is False

    def test_process_one_executes_trigger_and_replies(self, client):
        task = client.post(
            "/tasks",
            json={
                "title": "Blog draft",
                "description": "Write draft",
                "execution_type": "blog_write",
                "status": "completed",
            },
        ).json()
        comment = client.post(
            f"/tasks/{task['id']}/comments",
            json={"author": "user", "body": "@agent tighten intro and add CTA"},
        ).json()

        config_patch, run_patch = self._agent_patches(result="Revised draft with CTA")
        with config_patch, run_patch as run_mock:
            response = client.post("/automation/comments/process-one")

        payload = response.json()
        assert response.status_code == 200
        assert payload["processed"] is True
        assert payload["status"] == "succeeded"
        assert payload["comment_id"] == comment["id"]

        updated_task = client.get(f"/tasks/{task['id']}").json()
        assert updated_task["status"] == "completed"
        assert "Revised draft with CTA" in updated_task["notes"]

        comments = client.get(f"/tasks/{task['id']}/comments").json()
        assert any("Started revision" in c["body"] for c in comments)
        assert any("Revision completed" in c["body"] for c in comments)

        prompt = run_mock.call_args.args[0]
        assert "tighten intro and add CTA" in prompt

    def test_process_one_handles_retry_and_exhaustion(self, client):
        task = client.post(
            "/tasks",
            json={"title": "Retry task", "execution_type": "research", "status": "completed"},
        ).json()
        comment = client.post(
            f"/tasks/{task['id']}/comments",
            json={"author": "user", "body": "@agent fix this"},
        ).json()

        config_patch, run_patch = self._agent_patches(error=RuntimeError("boom"))
        with config_patch, run_patch:
            first = client.post("/automation/comments/process-one").json()
            second = client.post("/automation/comments/process-one").json()

        assert first["processed"] is True
        assert first["status"] == "failed"
        assert first["attempts"] == 1

        assert second["processed"] is True
        assert second["status"] == "retry_exhausted"
        assert second["attempts"] == 2

        third = client.post("/automation/comments/process-one").json()
        assert third["processed"] is False

        db = get_db_session()
        try:
            action = db.query(CommentActionModel).filter(CommentActionModel.comment_id == comment["id"]).first()
            assert action is not None
            assert action.status == "retry_exhausted"
            assert action.attempts == 2
        finally:
            db.close()

    def test_throughput_processes_one_comment_per_cycle(self, client):
        t1 = client.post("/tasks", json={"title": "Task 1", "execution_type": "research"}).json()
        t2 = client.post("/tasks", json={"title": "Task 2", "execution_type": "research"}).json()

        c1 = client.post(
            f"/tasks/{t1['id']}/comments",
            json={"author": "user", "body": "@agent revise first"},
        ).json()
        c2 = client.post(
            f"/tasks/{t2['id']}/comments",
            json={"author": "user", "body": "@agent revise second"},
        ).json()

        config_patch = patch(
            "agent.config.AgentConfig.from_env",
            return_value=SimpleNamespace(cwd="", setting_sources=[], system_prompt=""),
        )
        run_patch = patch(
            "agent.seo_agent.SEOAgent.create_and_run",
            new=AsyncMock(side_effect=["Result 1", "Result 2"]),
        )

        with config_patch, run_patch:
            first = client.post("/automation/comments/process-one").json()
            second = client.post("/automation/comments/process-one").json()

        assert first["processed"] is True
        assert first["comment_id"] == c1["id"]
        assert second["processed"] is True
        assert second["comment_id"] == c2["id"]


class TestAutopilotIntervalDefault:
    def test_default_interval_is_five_minutes(self, monkeypatch):
        monkeypatch.delenv("COMMENT_AUTOPILOT_INTERVAL_SECONDS", raising=False)
        assert _autopilot_interval_seconds() == 300


class TestStaleCommentSkip:
    def _agent_patches(self, result="done"):
        config_patch = patch(
            "agent.config.AgentConfig.from_env",
            return_value=SimpleNamespace(cwd="", setting_sources=[], system_prompt=""),
        )
        run_patch = patch("agent.seo_agent.SEOAgent.create_and_run", new=AsyncMock(return_value=result))
        return config_patch, run_patch

    def test_autopilot_skips_comment_if_task_executed_after_comment(self, client):
        """If the task was executed AFTER the comment was posted, autopilot should skip it."""
        task = client.post(
            "/tasks",
            json={"title": "Already done", "execution_type": "research"},
        ).json()

        # Post the @agent comment
        client.post(
            f"/tasks/{task['id']}/comments",
            json={"author": "user", "body": "@agent redo this"},
        )

        # Now execute the task manually (simulates user clicking Execute after commenting)
        config_patch, run_patch = self._agent_patches()
        with config_patch, run_patch:
            client.post(f"/tasks/{task['id']}/execute")

        # Autopilot should NOT re-execute — task.updated_at is now after comment.created_at
        response = client.post("/automation/comments/process-one")
        assert response.status_code == 200
        assert response.json()["processed"] is False

    def test_autopilot_processes_comment_if_no_execution_after(self, client):
        """If no execution happened after the comment, autopilot should process it."""
        task = client.post(
            "/tasks",
            json={"title": "Needs revision", "execution_type": "research", "status": "completed"},
        ).json()

        client.post(
            f"/tasks/{task['id']}/comments",
            json={"author": "user", "body": "@agent add more detail"},
        )

        config_patch, run_patch = self._agent_patches(result="Revised output")
        with config_patch, run_patch:
            response = client.post("/automation/comments/process-one")

        assert response.json()["processed"] is True
