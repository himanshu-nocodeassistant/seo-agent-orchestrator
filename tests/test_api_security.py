"""Tests for API security hardening: CORS, optional token auth, rate limits,
and the fixed SEO audit endpoint."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


def _create_executable_task(client):
    resp = client.post(
        "/tasks",
        json={"title": "Security test task", "execution_type": "manual"},
    )
    return resp.json()["id"]


class TestCORS:
    def test_allows_configured_localhost_origin(self, client):
        resp = client.get(
            "/health", headers={"Origin": "http://localhost:8000"}
        )
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:8000"

    def test_rejects_unknown_origin(self, client):
        resp = client.get(
            "/health", headers={"Origin": "https://evil.example.com"}
        )
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") is None


class TestOptionalTokenAuth:
    def test_token_gate_blocks_requests_without_header(self, client, monkeypatch):
        monkeypatch.setenv("API_TOKEN", "secret-token")
        resp = client.get("/tasks")
        assert resp.status_code == 401

    def test_token_gate_accepts_valid_header(self, client, monkeypatch):
        monkeypatch.setenv("API_TOKEN", "secret-token")
        resp = client.get("/tasks", headers={"Authorization": "Bearer secret-token"})
        assert resp.status_code == 200

    def test_no_token_configured_means_open(self, client, monkeypatch):
        monkeypatch.delenv("API_TOKEN", raising=False)
        resp = client.get("/tasks")
        assert resp.status_code == 200


class TestRateLimit:
    def test_execute_endpoint_rate_limited(self, client, monkeypatch):
        monkeypatch.setenv("API_RATE_LIMIT_EXECUTE", "3/minute")
        task_id = _create_executable_task(client)
        statuses = []
        for _ in range(4):
            resp = client.post(f"/tasks/{task_id}/execute")
            statuses.append(resp.status_code)
        assert statuses[:3] == [200, 200, 200]
        assert statuses[3] == 429


class TestSeoAuditEndpoint:
    def test_audit_runs_through_profile_pipeline(self, client):
        with patch(
            "agent.api.helpers._run_agent_prompt",
            new=AsyncMock(
                return_value=SimpleNamespace(
                    result_text=(
                        "Audit found 3 critical keyword issues. "
                        "Source: https://example.com/audit"
                    ),
                    session_id=None,
                )
            ),
        ):
            resp = client.post(
                "/runs/audit-test-1/seo-audit", json={"days": 28}
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_id"]

        task = client.get(f"/tasks/{data['task_id']}").json()
        assert task["status"] == "completed"
        assert task["execution_type"] == "seo_audit"

        run = client.get(f"/runs/{data['run_id']}").json()
        assert run["validator_status"] == "passed"

    def test_audit_prompt_has_no_bash_instructions(self, client):
        captured = {}

        async def _fake_run(prompt, config, prompt_context):
            captured["prompt"] = prompt
            return SimpleNamespace(
                result_text="Audit complete. Top keyword: no-code. Source: https://example.com/audit",
                session_id=None,
            )

        with patch("agent.api.helpers._run_agent_prompt", new=_fake_run):
            resp = client.post(
                "/runs/audit-test-2/seo-audit", json={"days": 28}
            )
        assert resp.status_code == 200
        prompt = captured["prompt"]
        assert "Bash tool" not in prompt
        assert "curl" not in prompt
        assert "localhost:8000" not in prompt
