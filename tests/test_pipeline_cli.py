"""
Tests for scripts/pipelines/_cli.py — the shared harness every DataForSEO
pipeline script (scripts/pipelines/<name>.py) delegates to.

Uses a small fake DataForSEOClient subclass covering every parameter shape
the harness must dispatch (no args, tasks list, tasks + poll kwargs,
task_id) rather than any real agent.dataforseo class, so these tests don't
depend on — or need updating alongside — the actual API surface.
All HTTP is mocked; no real network calls, no real billing.
"""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import agent.dataforseo.logger as logger_module
from agent.dataforseo.client import DataForSEOClient
from scripts.pipelines._cli import run_pipeline, _public_methods, _method_params


class _FakeClient(DataForSEOClient):
    """Exercises every method shape run_pipeline must handle."""

    def no_args_method(self) -> list[dict]:
        """Free lookup, no arguments."""
        data = self._get("fake/no_args")
        return self._extract(data)

    def tasks_method(self, tasks: list[dict]) -> list[dict]:
        """Takes a list of task dicts."""
        data = self._post("fake/tasks", tasks)
        return self._extract(data)

    def tasks_with_poll_method(self, tasks: list[dict], **poll_kwargs) -> list[dict]:
        """Takes tasks plus optional poll_interval/max_wait."""
        data = self._post("fake/tasks_poll", tasks)
        return self._extract(data)

    def task_id_method(self, task_id: str) -> dict:
        """Takes a single task_id string."""
        data = self._get(f"fake/task/{task_id}")
        results = self._extract(data)
        return results[0] if results else {}

    @staticmethod
    def _extract(data: dict) -> list[dict]:
        tasks = data.get("tasks", [])
        if not tasks:
            return []
        return tasks[0].get("result") or []


@pytest.fixture(autouse=True)
def isolated_logs_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(logger_module, "LOGS_DIR", tmp_path)


@pytest.fixture(autouse=True)
def dataforseo_creds(monkeypatch):
    monkeypatch.setenv("DATAFORSEO_LOGIN", "test@example.com")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "test-password")


def _fake_response(cost=0.0, result_items=None):
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status.return_value = None
    resp.json.return_value = {
        "status_code": 20000,
        "status_message": "Ok.",
        "cost": cost,
        "tasks": [{"status_code": 20000, "result": result_items or []}],
    }
    return resp


def _run(argv, monkeypatch):
    monkeypatch.setattr(sys, "argv", argv)
    run_pipeline(_FakeClient, "fake-pipeline")


class TestIntrospection:
    def test_public_methods_excludes_underscore_and_static_helpers(self):
        methods = _public_methods(_FakeClient)
        assert set(methods) == {
            "no_args_method", "tasks_method", "tasks_with_poll_method", "task_id_method",
        }

    def test_method_params_detects_tasks(self):
        params, has_var_kw = _method_params(_FakeClient.tasks_method)
        assert params == ["tasks"]
        assert has_var_kw is False

    def test_method_params_detects_tasks_with_var_kw(self):
        params, has_var_kw = _method_params(_FakeClient.tasks_with_poll_method)
        assert "tasks" in params
        assert has_var_kw is True

    def test_method_params_detects_task_id(self):
        params, has_var_kw = _method_params(_FakeClient.task_id_method)
        assert params == ["task_id"]
        assert has_var_kw is False

    def test_method_params_no_args(self):
        params, has_var_kw = _method_params(_FakeClient.no_args_method)
        assert params == []
        assert has_var_kw is False


class TestRunPipelineDispatch:
    def test_no_args_method_runs_without_task_flags(self, monkeypatch, tmp_path, capsys):
        out = tmp_path / "out.json"
        with patch("requests.Session.request", return_value=_fake_response(cost=0.0)):
            _run(["fake.py", "no_args_method", "--output", str(out)], monkeypatch)
        assert json.loads(out.read_text()) == []
        captured = capsys.readouterr()
        assert "DataForSEO API cost this run: $0.0000" in captured.out

    def test_tasks_method_accepts_inline_task(self, monkeypatch, tmp_path, capsys):
        out = tmp_path / "out.json"
        with patch("requests.Session.request", return_value=_fake_response(cost=0.05, result_items=[{"keyword": "x"}])):
            _run(
                ["fake.py", "tasks_method", "--task", '{"keyword": "x"}', "--output", str(out)],
                monkeypatch,
            )
        assert json.loads(out.read_text()) == [{"keyword": "x"}]
        captured = capsys.readouterr()
        assert "Wrote 1 result(s)" in captured.out
        assert "$0.0500" in captured.out

    def test_tasks_method_accepts_tasks_file(self, monkeypatch, tmp_path, capsys):
        tasks_file = tmp_path / "tasks.json"
        tasks_file.write_text(json.dumps([{"keyword": "a"}, {"keyword": "b"}]))
        out = tmp_path / "out.json"
        with patch("requests.Session.request", return_value=_fake_response(cost=0.1, result_items=[{"k": 1}, {"k": 2}])):
            _run(
                ["fake.py", "tasks_method", "--tasks-file", str(tasks_file), "--output", str(out)],
                monkeypatch,
            )
        assert len(json.loads(out.read_text())) == 2

    def test_task_and_tasks_file_are_mutually_exclusive(self, monkeypatch, tmp_path):
        out = tmp_path / "out.json"
        with pytest.raises(SystemExit):
            _run(
                ["fake.py", "tasks_method", "--task", "{}", "--tasks-file", "x.json", "--output", str(out)],
                monkeypatch,
            )

    def test_tasks_method_requires_task_or_tasks_file(self, monkeypatch, tmp_path):
        out = tmp_path / "out.json"
        with pytest.raises(SystemExit):
            _run(["fake.py", "tasks_method", "--output", str(out)], monkeypatch)

    def test_task_id_method_dispatches_with_task_id(self, monkeypatch, tmp_path, capsys):
        out = tmp_path / "out.json"
        with patch("requests.Session.request", return_value=_fake_response(cost=0.0, result_items=[{"status": "ready"}])):
            _run(
                ["fake.py", "task_id_method", "--task-id", "abc123", "--output", str(out)],
                monkeypatch,
            )
        assert json.loads(out.read_text()) == {"status": "ready"}

    def test_poll_kwargs_are_optional_and_passed_through_when_given(self, monkeypatch, tmp_path):
        out = tmp_path / "out.json"
        captured_kwargs = {}
        original = _FakeClient.tasks_with_poll_method

        def spy(self, tasks, **poll_kwargs):
            captured_kwargs.update(poll_kwargs)
            return original(self, tasks, **poll_kwargs)

        with patch.object(_FakeClient, "tasks_with_poll_method", spy):
            with patch("requests.Session.request", return_value=_fake_response(cost=0.0)):
                _run(
                    [
                        "fake.py", "tasks_with_poll_method", "--task", "{}",
                        "--poll-interval", "5", "--max-wait", "60", "--output", str(out),
                    ],
                    monkeypatch,
                )
        assert captured_kwargs == {"poll_interval": 5.0, "max_wait": 60.0}

    def test_default_output_path_uses_pipeline_and_method_name(self, monkeypatch, tmp_path):
        import scripts.pipelines._cli as cli_module
        monkeypatch.setattr(cli_module, "COMPILED_DIR", tmp_path)
        with patch("requests.Session.request", return_value=_fake_response(cost=0.0)):
            _run(["fake.py", "no_args_method"], monkeypatch)
        from datetime import date
        expected = tmp_path / f"fake-pipeline-no-args-method-{date.today()}.json"
        assert expected.exists()

    def test_token_summary_printed_when_result_has_token_fields(self, monkeypatch, tmp_path, capsys):
        out = tmp_path / "out.json"
        with patch(
            "requests.Session.request",
            return_value=_fake_response(
                cost=0.02,
                result_items=[{"input_tokens": 100, "output_tokens": 200, "money_spent": 0.02}],
            ),
        ):
            _run(["fake.py", "tasks_method", "--task", "{}", "--output", str(out)], monkeypatch)
        captured = capsys.readouterr()
        assert "LLM token usage: 100 input / 200 output tokens, $0.0200 money_spent" in captured.out

    def test_token_summary_absent_when_no_token_fields(self, monkeypatch, tmp_path, capsys):
        out = tmp_path / "out.json"
        with patch("requests.Session.request", return_value=_fake_response(cost=0.02, result_items=[{"keyword": "x"}])):
            _run(["fake.py", "tasks_method", "--task", "{}", "--output", str(out)], monkeypatch)
        captured = capsys.readouterr()
        assert "LLM token usage" not in captured.out
