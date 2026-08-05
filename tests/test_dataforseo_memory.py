"""Tests for the DataForSEO measurement memory layer and prompt injection.
Uses fake compiled rollups on disk — no network calls, no billing."""

import json
from types import SimpleNamespace

from agent.dataforseo.memory import load_measurement_snapshot


def _write_rollup(root, name, data):
    compiled = root / "dataforseo" / "compiled"
    compiled.mkdir(parents=True, exist_ok=True)
    path = compiled / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


class TestMeasurementSnapshot:
    def test_empty_when_no_compiled_dir(self, tmp_path):
        assert load_measurement_snapshot(str(tmp_path)) == ""

    def test_renders_newest_file_per_pipeline(self, tmp_path):
        _write_rollup(tmp_path, "serp-google-organic-search-2026-08-01.json",
                      [{"keyword": "old", "rank_absolute": 5}])
        newer = _write_rollup(tmp_path, "serp-google-organic-search-2026-08-05.json",
                              [{"keyword": "new", "rank_absolute": 3}])
        import os
        os.utime(newer)  # ensure newest by mtime too
        snapshot = load_measurement_snapshot(str(tmp_path))
        assert "new" in snapshot
        assert "old" not in snapshot

    def test_digests_tasks_result_shape(self, tmp_path):
        _write_rollup(
            tmp_path,
            "keywords-google-ads-search-volume-2026-08-05.json",
            {"tasks": [{"result": [{"keyword": "no-code", "search_volume": 1200}]}]},
        )
        snapshot = load_measurement_snapshot(str(tmp_path))
        assert "search_volume=1200" in snapshot

    def test_corrupt_file_skipped(self, tmp_path):
        compiled = tmp_path / "dataforseo" / "compiled"
        compiled.mkdir(parents=True)
        (compiled / "bad-2026-08-05.json").write_text("{not json", encoding="utf-8")
        _write_rollup(tmp_path, "serp-google-organic-search-2026-08-05.json",
                      [{"keyword": "good"}])
        snapshot = load_measurement_snapshot(str(tmp_path))
        assert "good" in snapshot

    def test_char_budget_truncates_sections(self, tmp_path):
        _write_rollup(tmp_path, "serp-google-organic-search-2026-08-05.json",
                      [{"keyword": "a" * 50}] * 10)
        _write_rollup(tmp_path, "backlinks-backlinks-live-2026-08-05.json",
                      [{"target": "example.com", "rank": 1}] * 10)
        snapshot = load_measurement_snapshot(str(tmp_path), char_limit=300)
        assert snapshot != ""
        # With a small budget, the first section is kept but the second isn't.
        assert ("serp-google-organic-search" in snapshot) != (
            "backlinks" in snapshot
        )


class TestPromptInjection:
    def test_measurements_only_for_tagged_profiles(self, tmp_path):
        _write_rollup(tmp_path, "serp-google-organic-search-2026-08-05.json",
                      [{"keyword": "no-code", "rank_absolute": 3}])

        from agent.memory_service import fetch_semantic_context
        from agent.runtime_profiles import PROFILE_REGISTRY

        task = SimpleNamespace(title="Research no-code", description="Find keywords")
        research_ctx = fetch_semantic_context(
            task, "research", str(tmp_path), 2000,
            profile=PROFILE_REGISTRY["research"],
        )
        assert "no-code" in research_ctx.measurements

        manual_ctx = fetch_semantic_context(
            task, "manual", str(tmp_path), 2000,
            profile=PROFILE_REGISTRY["manual"],
        )
        assert manual_ctx.measurements == ""

    def test_to_prompt_renders_measured_data_section(self, tmp_path):
        _write_rollup(tmp_path, "serp-google-organic-search-2026-08-05.json",
                      [{"keyword": "no-code", "rank_absolute": 3}])

        from agent.memory_service import (
            EpisodicContext,
            ProceduralContext,
            SemanticContext,
            ShortTermContext,
            compose_prompt_context,
        )

        ctx = compose_prompt_context(
            short_term=ShortTermContext(
                run_id="r", task_id=1, execution_type="research",
                trigger_source="test", session_id=None, validator_status=None,
                task_title="T", task_description=None,
            ),
            episodic=EpisodicContext(task_id=1, execution_type="research"),
            semantic=SemanticContext(
                project_overview="", strategy="", learnings="", context_view="",
                measurements=load_measurement_snapshot(str(tmp_path)),
            ),
            procedural=ProceduralContext(
                execution_type="research", profile_name="research",
                tool_policy=[], validator_name="x", max_turns=10,
                timeout_seconds=100, procedural_tags=[], workflow_prompt="",
            ),
        )
        prompt = ctx.to_prompt()
        assert "## Measured Data (DataForSEO)" in prompt
        assert "no-code" in prompt
