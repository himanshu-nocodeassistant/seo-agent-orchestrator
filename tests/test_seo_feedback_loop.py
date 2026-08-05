"""
Tests for SEO feedback loop: change logging, parsing, persistence, and rendering.

Red/green TDD — tests written before implementation.
Run: python -m pytest tests/test_seo_feedback_loop.py -v
"""

import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers: import targets (will fail until implemented)
# ---------------------------------------------------------------------------

def _import_targets():
    """Import the functions under test from main. Deferred so tests can be
    collected even before implementation exists."""
    from agent.api.main import (
        _parse_change_log_block,
        _build_change_id,
        _atomic_json_write,
        _load_seo_changes,
        _load_seo_learnings,
        _write_change_log_entry,
        _render_changes_markdown,
        _render_learnings_markdown,
        _refresh_markdown_views,
        CMS_CHANGE_FIELD_MAP,
        VALID_REVIEW_STATUSES,
        SEO_CHANGES_PATH,
        SEO_LEARNINGS_PATH,
    )
    return {
        "_parse_change_log_block": _parse_change_log_block,
        "_build_change_id": _build_change_id,
        "_atomic_json_write": _atomic_json_write,
        "_load_seo_changes": _load_seo_changes,
        "_load_seo_learnings": _load_seo_learnings,
        "_write_change_log_entry": _write_change_log_entry,
        "_render_changes_markdown": _render_changes_markdown,
        "_render_learnings_markdown": _render_learnings_markdown,
        "_refresh_markdown_views": _refresh_markdown_views,
        "CMS_CHANGE_FIELD_MAP": CMS_CHANGE_FIELD_MAP,
        "VALID_REVIEW_STATUSES": VALID_REVIEW_STATUSES,
        "SEO_CHANGES_PATH": SEO_CHANGES_PATH,
        "SEO_LEARNINGS_PATH": SEO_LEARNINGS_PATH,
    }


# ---------------------------------------------------------------------------
# _parse_change_log_block
# ---------------------------------------------------------------------------

class TestParseChangeLogBlock:
    """Tests for _parse_change_log_block(agent_output: str) -> dict"""

    def _fn(self):
        return _import_targets()["_parse_change_log_block"]

    def test_ok_parses_valid_block(self):
        fn = self._fn()
        output = """Some agent output here.

<!-- CHANGE_LOG
{
  "url": "https://nocodeassistant.agency/weweb-agency",
  "field": "title tag",
  "before": "WeWeb Agency | NCA",
  "after": "WeWeb Development Agency | NCA",
  "webflow_item_id": "abc123",
  "webflow_status": "published"
}
-->"""
        result = fn(output)
        assert result["extraction_status"] == "ok"
        assert result["failure_reason"] is None
        assert result["url"] == "https://nocodeassistant.agency/weweb-agency"
        assert result["field"] == "title tag"
        assert result["before"] == "WeWeb Agency | NCA"
        assert result["after"] == "WeWeb Development Agency | NCA"
        assert result["webflow_item_id"] == "abc123"

    def test_missing_block_returns_failure(self):
        fn = self._fn()
        output = "Agent output with no CHANGE_LOG block at all."
        result = fn(output)
        assert result["extraction_status"] == "failed"
        assert result["failure_reason"] == "missing_block"
        assert result["url"] is None
        assert result["after"] is None

    def test_invalid_json_returns_failure(self):
        fn = self._fn()
        output = """Done.
<!-- CHANGE_LOG
{ this is not valid json %%%
-->"""
        result = fn(output)
        assert result["extraction_status"] == "failed"
        assert result["failure_reason"] == "invalid_json"

    def test_missing_required_fields_returns_failure(self):
        fn = self._fn()
        # url, field, and after are all null — no usable data
        output = """Done.
<!-- CHANGE_LOG
{
  "url": null,
  "field": null,
  "before": null,
  "after": null,
  "webflow_item_id": null,
  "webflow_status": "manual-only"
}
-->"""
        result = fn(output)
        assert result["extraction_status"] == "failed"
        assert result["failure_reason"] == "missing_required_fields"

    def test_never_raises_on_garbage_input(self):
        fn = self._fn()
        # Should never raise, always return a dict
        result = fn("")
        assert isinstance(result, dict)
        assert result["extraction_status"] == "failed"

        result2 = fn("<!-- CHANGE_LOG\n-->")
        assert isinstance(result2, dict)
        assert result2["extraction_status"] == "failed"

    def test_partial_fields_still_ok_if_after_present(self):
        fn = self._fn()
        # url and field present, before is null — still valid (blog_write has null before)
        output = """Done.
<!-- CHANGE_LOG
{
  "url": "https://nocodeassistant.agency/blog/new-post",
  "field": "content",
  "before": null,
  "after": "How to Build Internal Tools No-Code | NCA",
  "webflow_item_id": "xyz",
  "webflow_status": "published"
}
-->"""
        result = fn(output)
        assert result["extraction_status"] == "ok"
        assert result["before"] is None
        assert result["after"] == "How to Build Internal Tools No-Code | NCA"


# ---------------------------------------------------------------------------
# _build_change_id
# ---------------------------------------------------------------------------

class TestBuildChangeId:
    """Tests for _build_change_id(task_id, execution_type, url) -> str"""

    def _fn(self):
        return _import_targets()["_build_change_id"]

    def test_produces_deterministic_id(self):
        fn = self._fn()
        id1 = fn(42, "rewrite_title", "https://nocodeassistant.agency/weweb-agency")
        id2 = fn(42, "rewrite_title", "https://nocodeassistant.agency/weweb-agency")
        assert id1 == id2

    def test_includes_task_id_and_type(self):
        fn = self._fn()
        result = fn(42, "rewrite_title", "https://nocodeassistant.agency/weweb-agency")
        assert result.startswith("42-rewrite_title-")

    def test_null_url_uses_unknown_slug(self):
        fn = self._fn()
        result = fn(7, "blog_write", None)
        assert result == "7-blog_write-unknown"

    def test_url_slug_is_normalized(self):
        fn = self._fn()
        result = fn(1, "rewrite_h1", "https://nocodeassistant.agency/bubble-agency")
        assert "bubble-agency" in result
        # No uppercase, no special chars other than hyphens
        slug_part = result.split("rewrite_h1-")[1]
        assert slug_part == slug_part.lower()

    def test_slug_truncated_to_40_chars(self):
        fn = self._fn()
        long_url = "https://nocodeassistant.agency/" + "a" * 100
        result = fn(1, "rewrite_title", long_url)
        slug_part = result.split("rewrite_title-")[1]
        assert len(slug_part) <= 40


# ---------------------------------------------------------------------------
# _atomic_json_write
# ---------------------------------------------------------------------------

class TestAtomicJsonWrite:
    """Tests for _atomic_json_write(path: Path, data: dict) -> None"""

    def _fn(self):
        return _import_targets()["_atomic_json_write"]

    def test_writes_valid_json(self, tmp_path):
        fn = self._fn()
        target = tmp_path / "test.json"
        data = {"version": 1, "entries": [{"id": "abc"}]}
        fn(target, data)
        assert target.exists()
        loaded = json.loads(target.read_text())
        assert loaded == data

    def test_no_tmp_file_left_after_write(self, tmp_path):
        fn = self._fn()
        target = tmp_path / "test.json"
        fn(target, {"version": 1})
        tmp_file = target.with_suffix(".tmp")
        assert not tmp_file.exists()

    def test_creates_parent_dirs_if_needed(self, tmp_path):
        fn = self._fn()
        target = tmp_path / "subdir" / "nested.json"
        # Should not raise even if parent doesn't exist
        fn(target, {"version": 1})
        assert target.exists()


# ---------------------------------------------------------------------------
# _load_seo_changes / _load_seo_learnings
# ---------------------------------------------------------------------------

class TestLoadFunctions:
    """Tests for _load_seo_changes() and _load_seo_learnings()"""

    def test_load_changes_returns_empty_structure_if_missing(self, tmp_path, monkeypatch):
        from agent.api import main as main_module
        monkeypatch.setattr(main_module, "SEO_CHANGES_PATH", tmp_path / "nonexistent.json")
        fn = _import_targets()["_load_seo_changes"]
        result = fn()
        assert result == {"version": 1, "entries": []}

    def test_load_learnings_returns_empty_structure_if_missing(self, tmp_path, monkeypatch):
        from agent.api import main as main_module
        monkeypatch.setattr(main_module, "SEO_LEARNINGS_PATH", tmp_path / "nonexistent.json")
        fn = _import_targets()["_load_seo_learnings"]
        result = fn()
        assert result == {"version": 1, "learnings": {}}

    def test_load_changes_reads_existing_file(self, tmp_path, monkeypatch):
        from agent.api import main as main_module
        path = tmp_path / "seo-changes.json"
        data = {"version": 1, "entries": [{"id": "1-rewrite_title-test"}]}
        path.write_text(json.dumps(data))
        monkeypatch.setattr(main_module, "SEO_CHANGES_PATH", path)
        fn = _import_targets()["_load_seo_changes"]
        result = fn()
        assert result["entries"][0]["id"] == "1-rewrite_title-test"


# ---------------------------------------------------------------------------
# _write_change_log_entry
# ---------------------------------------------------------------------------

class TestWriteChangeLogEntry:
    """Tests for _write_change_log_entry(task, agent_output, user_comments)"""

    def _make_task(self, task_id=42, title="Rewrite /weweb-agency title",
                   execution_type="rewrite_title"):
        task = MagicMock()
        task.id = task_id
        task.title = title
        task.execution_type = execution_type
        return task

    def _make_comment(self, author="user", body="keep it concise"):
        c = MagicMock()
        c.author = author
        c.body = body
        return c

    def _valid_output(self):
        return """Done.
<!-- CHANGE_LOG
{
  "url": "https://nocodeassistant.agency/weweb-agency",
  "field": "title tag",
  "before": "WeWeb Agency | NCA",
  "after": "WeWeb Dev Agency | NCA",
  "webflow_item_id": "abc",
  "webflow_status": "published"
}
-->"""

    def test_creates_new_entry_for_cms_type(self, tmp_path, monkeypatch):
        from agent.api import main as main_module
        monkeypatch.setattr(main_module, "SEO_CHANGES_PATH", tmp_path / "seo-changes.json")
        monkeypatch.setattr(main_module, "SEO_CHANGES_MD_PATH", tmp_path / "log.md")
        monkeypatch.setattr(main_module, "SEO_LEARNINGS_PATH", tmp_path / "seo-learnings.json")
        monkeypatch.setattr(main_module, "SEO_LEARNINGS_MD_PATH", tmp_path / "learnings.md")

        fn = _import_targets()["_write_change_log_entry"]
        task = self._make_task()
        fn(task, self._valid_output(), [self._make_comment()])

        data = json.loads((tmp_path / "seo-changes.json").read_text())
        assert len(data["entries"]) == 1
        entry = data["entries"][0]
        assert entry["task_id"] == 42
        assert entry["extraction_status"] == "ok"
        assert entry["failure_reason"] is None
        assert entry["status"] == "pending-review"
        assert entry["change_type"] == "title tag"
        assert entry["url"] == "https://nocodeassistant.agency/weweb-agency"
        assert entry["before"] == "WeWeb Agency | NCA"
        assert entry["after"] == "WeWeb Dev Agency | NCA"
        assert len(entry["user_notes"]) == 1
        assert entry["user_notes"][0]["body"] == "keep it concise"

    def test_upsert_increments_attempts(self, tmp_path, monkeypatch):
        from agent.api import main as main_module
        monkeypatch.setattr(main_module, "SEO_CHANGES_PATH", tmp_path / "seo-changes.json")
        monkeypatch.setattr(main_module, "SEO_CHANGES_MD_PATH", tmp_path / "log.md")
        monkeypatch.setattr(main_module, "SEO_LEARNINGS_PATH", tmp_path / "seo-learnings.json")
        monkeypatch.setattr(main_module, "SEO_LEARNINGS_MD_PATH", tmp_path / "learnings.md")

        fn = _import_targets()["_write_change_log_entry"]
        task = self._make_task()

        fn(task, self._valid_output(), [])
        fn(task, self._valid_output(), [])  # second run = upsert

        data = json.loads((tmp_path / "seo-changes.json").read_text())
        assert len(data["entries"]) == 1  # not duplicated
        assert data["entries"][0]["attempts"] == 2

    def test_upsert_preserves_reviewed_status(self, tmp_path, monkeypatch):
        from agent.api import main as main_module
        path = tmp_path / "seo-changes.json"
        existing_id = "42-rewrite_title-nocodeassistant-agency-weweb-agency"
        existing_data = {
            "version": 1,
            "entries": [{
                "id": existing_id,
                "task_id": 42,
                "status": "reviewed-positive",
                "attempts": 1,
                "review_notes": "Ranking improved",
                "reviewed_at": "2026-04-01T10:00:00Z",
                "learning_ids": ["buyer-intent"],
                "logged_at": "2026-03-19T21:00:00Z",
            }]
        }
        path.write_text(json.dumps(existing_data))
        monkeypatch.setattr(main_module, "SEO_CHANGES_PATH", path)
        monkeypatch.setattr(main_module, "SEO_CHANGES_MD_PATH", tmp_path / "log.md")
        monkeypatch.setattr(main_module, "SEO_LEARNINGS_PATH", tmp_path / "seo-learnings.json")
        monkeypatch.setattr(main_module, "SEO_LEARNINGS_MD_PATH", tmp_path / "learnings.md")

        fn = _import_targets()["_write_change_log_entry"]
        task = self._make_task()
        fn(task, self._valid_output(), [])

        data = json.loads(path.read_text())
        entry = data["entries"][0]
        assert entry["status"] == "reviewed-positive"  # preserved
        assert entry["review_notes"] == "Ranking improved"  # preserved
        assert entry["attempts"] == 2

    def test_non_cms_type_is_noop(self, tmp_path, monkeypatch):
        from agent.api import main as main_module
        changes_path = tmp_path / "seo-changes.json"
        monkeypatch.setattr(main_module, "SEO_CHANGES_PATH", changes_path)

        fn = _import_targets()["_write_change_log_entry"]
        task = self._make_task(execution_type="research")  # not in CMS_CHANGE_FIELD_MAP
        fn(task, "Some research output.", [])

        assert not changes_path.exists()  # file never created

    def test_failed_extraction_still_writes_entry(self, tmp_path, monkeypatch):
        from agent.api import main as main_module
        monkeypatch.setattr(main_module, "SEO_CHANGES_PATH", tmp_path / "seo-changes.json")
        monkeypatch.setattr(main_module, "SEO_CHANGES_MD_PATH", tmp_path / "log.md")
        monkeypatch.setattr(main_module, "SEO_LEARNINGS_PATH", tmp_path / "seo-learnings.json")
        monkeypatch.setattr(main_module, "SEO_LEARNINGS_MD_PATH", tmp_path / "learnings.md")

        fn = _import_targets()["_write_change_log_entry"]
        task = self._make_task()
        fn(task, "Agent output with no CHANGE_LOG block.", [])

        data = json.loads((tmp_path / "seo-changes.json").read_text())
        assert len(data["entries"]) == 1
        entry = data["entries"][0]
        assert entry["extraction_status"] == "failed"
        assert entry["failure_reason"] == "missing_block"
        assert entry["url"] is None
        assert entry["after"] is None

    def test_only_user_comments_stored(self, tmp_path, monkeypatch):
        from agent.api import main as main_module
        monkeypatch.setattr(main_module, "SEO_CHANGES_PATH", tmp_path / "seo-changes.json")
        monkeypatch.setattr(main_module, "SEO_CHANGES_MD_PATH", tmp_path / "log.md")
        monkeypatch.setattr(main_module, "SEO_LEARNINGS_PATH", tmp_path / "seo-learnings.json")
        monkeypatch.setattr(main_module, "SEO_LEARNINGS_MD_PATH", tmp_path / "learnings.md")

        fn = _import_targets()["_write_change_log_entry"]
        task = self._make_task()
        comments = [
            self._make_comment(author="user", body="keep concise"),
            self._make_comment(author="agent", body="✅ Task completed"),
        ]
        fn(task, self._valid_output(), comments)

        data = json.loads((tmp_path / "seo-changes.json").read_text())
        notes = data["entries"][0]["user_notes"]
        assert len(notes) == 1  # only user comment
        assert notes[0]["author"] == "user"


# ---------------------------------------------------------------------------
# _render_changes_markdown / _render_learnings_markdown
# ---------------------------------------------------------------------------

class TestRenderMarkdown:
    """Tests for _render_changes_markdown and _render_learnings_markdown"""

    def test_render_changes_includes_key_fields(self):
        fn = _import_targets()["_render_changes_markdown"]
        entries = [{
            "id": "42-rewrite_title-weweb-agency",
            "task_id": 42,
            "task_title": "Rewrite /weweb-agency title",
            "execution_type": "rewrite_title",
            "change_type": "title tag",
            "url": "https://nocodeassistant.agency/weweb-agency",
            "before": "WeWeb Agency | NCA",
            "after": "WeWeb Dev Agency | NCA",
            "extraction_status": "ok",
            "failure_reason": None,
            "status": "pending-review",
            "logged_at": "2026-03-19T21:30:00Z",
            "attempts": 1,
            "review_notes": None,
            "reviewed_at": None,
            "learning_ids": [],
            "is_backfilled": False,
            "user_notes": [],
            "webflow_item_id": "abc",
        }]
        md = fn(entries)
        assert "weweb-agency" in md
        assert "title tag" in md
        assert "pending-review" in md
        assert "WeWeb Dev Agency | NCA" in md

    def test_render_learnings_includes_principle(self):
        fn = _import_targets()["_render_learnings_markdown"]
        learnings = {
            "buyer-intent-qualifier-in-title": {
                "id": "buyer-intent-qualifier-in-title",
                "discovered": "2026-03-19",
                "evidence": "Task 42 — /weweb-agency moved #11→#7",
                "principle": "Adding deliverable qualifier improves service page rankings",
                "applicable_when": "Competitive service page",
                "not_applicable_when": "Branded queries",
                "confidence": "medium",
                "hit_count": 1,
                "source_entry_ids": ["42-rewrite_title-weweb-agency"],
                "updated_at": "2026-03-19T21:30:00Z",
            }
        }
        md = fn(learnings)
        assert "buyer-intent-qualifier-in-title" in md
        assert "Adding deliverable qualifier" in md
        assert "medium" in md

    def test_render_changes_empty_list_returns_string(self):
        fn = _import_targets()["_render_changes_markdown"]
        md = fn([])
        assert isinstance(md, str)

    def test_render_learnings_empty_dict_returns_string(self):
        fn = _import_targets()["_render_learnings_markdown"]
        md = fn({})
        assert isinstance(md, str)


# ---------------------------------------------------------------------------
# execute_task integration: CMS types log, non-CMS types don't
# ---------------------------------------------------------------------------

class TestExecuteTaskLogging:
    """Integration tests for execute_task endpoint — verifies change logging behaviour."""

    VALID_AGENT_OUTPUT = """Task complete. Final title: WeWeb Dev Agency | NCA

<!-- CHANGE_LOG
{
  "url": "https://nocodeassistant.agency/weweb-agency",
  "field": "title tag",
  "before": "WeWeb Agency | NCA",
  "after": "WeWeb Dev Agency | NCA",
  "webflow_item_id": "abc123",
  "webflow_status": "published"
}
-->"""

    def test_cms_task_creates_change_log_entry(self, client, tmp_path, monkeypatch):
        from agent.api import main as main_module
        monkeypatch.setattr(main_module, "SEO_CHANGES_PATH", tmp_path / "seo-changes.json")
        monkeypatch.setattr(main_module, "SEO_CHANGES_MD_PATH", tmp_path / "log.md")
        monkeypatch.setattr(main_module, "SEO_LEARNINGS_PATH", tmp_path / "seo-learnings.json")
        monkeypatch.setattr(main_module, "SEO_LEARNINGS_MD_PATH", tmp_path / "learnings.md")

        # Create task
        resp = client.post("/tasks", json={
            "title": "Rewrite /weweb-agency title",
            "execution_type": "rewrite_title",
        })
        assert resp.status_code == 200
        task_id = resp.json()["id"]

        # Mock agent to return valid structured output
        with patch.object(main_module, "_run_agent_prompt",
                          new=AsyncMock(return_value=self.VALID_AGENT_OUTPUT)):
            exec_resp = client.post(f"/tasks/{task_id}/execute")
            assert exec_resp.status_code == 200

        # Verify JSON log created
        assert (tmp_path / "seo-changes.json").exists()
        data = json.loads((tmp_path / "seo-changes.json").read_text())
        assert len(data["entries"]) == 1
        assert data["entries"][0]["extraction_status"] == "ok"
        assert data["entries"][0]["task_id"] == task_id

    def test_non_cms_task_does_not_create_log(self, client, tmp_path, monkeypatch):
        from agent.api import main as main_module
        changes_path = tmp_path / "seo-changes.json"
        monkeypatch.setattr(main_module, "SEO_CHANGES_PATH", changes_path)

        resp = client.post("/tasks", json={
            "title": "Research internal tools keywords",
            "execution_type": "research",
        })
        task_id = resp.json()["id"]

        with patch.object(main_module, "_run_agent_prompt",
                          new=AsyncMock(return_value="Research complete.")):
            client.post(f"/tasks/{task_id}/execute")

        assert not changes_path.exists()

    def test_failed_extraction_logs_with_failure_reason(self, client, tmp_path, monkeypatch):
        from agent.api import main as main_module
        monkeypatch.setattr(main_module, "SEO_CHANGES_PATH", tmp_path / "seo-changes.json")
        monkeypatch.setattr(main_module, "SEO_CHANGES_MD_PATH", tmp_path / "log.md")
        monkeypatch.setattr(main_module, "SEO_LEARNINGS_PATH", tmp_path / "seo-learnings.json")
        monkeypatch.setattr(main_module, "SEO_LEARNINGS_MD_PATH", tmp_path / "learnings.md")

        resp = client.post("/tasks", json={
            "title": "Rewrite /bubble-agency title",
            "execution_type": "rewrite_title",
        })
        task_id = resp.json()["id"]

        # Agent output with no CHANGE_LOG block
        with patch.object(main_module, "_run_agent_prompt",
                          new=AsyncMock(return_value="Done. New title: Bubble Agency | NCA")):
            exec_resp = client.post(f"/tasks/{task_id}/execute")
            assert exec_resp.status_code == 200

        data = json.loads((tmp_path / "seo-changes.json").read_text())
        assert len(data["entries"]) == 1
        entry = data["entries"][0]
        assert entry["extraction_status"] == "failed"
        assert entry["failure_reason"] == "missing_block"
        # Validators are authoritative: rewrite_title requires a CHANGE_LOG
        # block, so the run is blocked while the failed extraction is logged.
        task_resp = client.get(f"/tasks/{task_id}")
        assert task_resp.json()["status"] == "blocked"
        run = client.get(f"/runs/{exec_resp.json()['run_id']}")
        assert run.json()["validator_status"] == "failed"


# ---------------------------------------------------------------------------
# CMS_CHANGE_FIELD_MAP and VALID_REVIEW_STATUSES constants
# ---------------------------------------------------------------------------

class TestConstants:
    def test_cms_change_field_map_covers_webflow_dependent_types(self):
        targets = _import_targets()
        cms_map = targets["CMS_CHANGE_FIELD_MAP"]
        from agent.api.main import WEBFLOW_DEPENDENT_TYPES
        # Every webflow-dependent type should be in the CMS map
        for t in WEBFLOW_DEPENDENT_TYPES:
            assert t in cms_map, f"{t} missing from CMS_CHANGE_FIELD_MAP"

    def test_valid_review_statuses_contains_all_outcomes(self):
        statuses = _import_targets()["VALID_REVIEW_STATUSES"]
        assert "pending-review" in statuses
        assert "reviewed-positive" in statuses
        assert "reviewed-negative" in statuses
        assert "reviewed-neutral" in statuses
        assert "reviewed-inconclusive" in statuses
