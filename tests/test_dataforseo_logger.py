import json

import pytest

from agent.dataforseo import logger


@pytest.fixture(autouse=True)
def isolated_logs_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(logger, "LOGS_DIR", tmp_path)
    return tmp_path


def _task(keyword, location_code, tag, task_id="task-id", status_code=20100):
    return {
        "id": task_id,
        "status_code": status_code,
        "data": {
            "keyword": keyword,
            "location_code": location_code,
            "tag": tag,
        },
    }


def test_single_task_post_is_grouped_by_tag_keyword_location(isolated_logs_dir):
    result = {"tasks": [_task("weweb agency", 2840, "tier1_service_weweb")]}

    written = logger.log_result("serp/google/organic/task_post", [], result)

    assert len(written) == 1
    path = written[0]
    assert path.parent == isolated_logs_dir / "tier1-service-weweb" / "weweb-agency" / "2840"
    assert path.name.endswith("_task_post.json")


def test_batched_task_post_splits_into_one_file_per_task(isolated_logs_dir):
    result = {
        "tasks": [
            _task("weweb agency", 2840, "tier1_service_weweb", task_id="a"),
            _task("weweb agency", 2826, "tier1_service_weweb", task_id="b"),
            _task("bubble agency", 2840, "tier1_service_bubble", task_id="c"),
        ]
    }

    written = logger.log_result("serp/google/organic/task_post", [], result)

    assert len(written) == 3
    relative = {str(p.relative_to(isolated_logs_dir)) for p in written}
    assert any(r.startswith("tier1-service-weweb/weweb-agency/2840/") for r in relative)
    assert any(r.startswith("tier1-service-weweb/weweb-agency/2826/") for r in relative)
    assert any(r.startswith("tier1-service-bubble/bubble-agency/2840/") for r in relative)

    # Each file only contains its own task's data, not the other two.
    for path in written:
        entry = json.loads(path.read_text())
        assert "tasks" not in entry
        assert entry["data"]["keyword"] in {"weweb agency", "bubble agency"}


def test_task_get_uses_task_get_suffix_not_task_id(isolated_logs_dir):
    result = {"tasks": [_task("hire bubble developer", 2840, "tier1_service_bubble", task_id="07011546-xyz")]}

    written = logger.log_result(
        "serp/google/organic/task_get/advanced/07011546-xyz", [], result
    )

    assert len(written) == 1
    assert written[0].name.endswith("_task_get.json")
    assert "07011546-xyz" not in written[0].name


def test_non_serp_call_without_tag_falls_back_to_legacy_layout(isolated_logs_dir):
    result = {"tasks": [{"id": "abc", "data": {}, "result": [{"foo": "bar"}]}]}

    written = logger.log_result(
        "ai_optimization/ai_keyword_data/locations_and_languages", [], result
    )

    assert len(written) == 1
    path = written[0]
    assert path.parent.parent == isolated_logs_dir / "ai_optimization" / "ai_keyword_data" / "locations_and_languages"
    entry = json.loads(path.read_text())
    assert entry["endpoint"] == "ai_optimization/ai_keyword_data/locations_and_languages"


def test_empty_tasks_list_falls_back_to_legacy_layout(isolated_logs_dir):
    result = {"tasks": []}

    written = logger.log_result("serp/google/organic/task_post", [{"keyword": "weweb agency"}], result)

    assert len(written) == 1
    entry = json.loads(written[0].read_text())
    assert entry["endpoint"] == "serp/google/organic/task_post"


def test_llm_mentions_target_list_payload_does_not_crash(isolated_logs_dir):
    """llm_mentions payloads carry `target: [{"keyword"|"domain": ...}]`
    rather than a scalar `keyword`. The logger must extract a string slug
    from inside the list, not pass the list to _slugify (which crashed)."""
    payload = [
        {
            "target": [{"keyword": "no-code agency", "search_scope": ["answer"]}],
            "location_name": "United States",
        }
    ]
    result = {"tasks": [{"id": "abc", "data": {}, "result": [{"items": []}]}]}

    written = logger.log_result(
        "ai_optimization/llm_mentions/search/live", payload, result
    )

    assert len(written) == 1
    assert "no-code-agency" in written[0].name


def test_extract_keyword_reads_keyword_from_target_list():
    payload = [{"target": [{"domain": "nocodeassistant.agency"}, {"keyword": "bubble agency"}]}]
    assert logger._extract_keyword(payload) == "bubble agency"


def test_extract_keyword_falls_back_to_domain_in_target_list():
    payload = [{"target": [{"domain": "nocodeassistant.agency"}]}]
    assert logger._extract_keyword(payload) == "nocodeassistant.agency"


def test_slugify_coerces_non_string_without_crashing():
    # Defense in depth: a logging helper must never raise and discard a
    # paid API response, whatever odd value reaches it.
    assert logger._slugify(["not", "a", "string"]) != ""
