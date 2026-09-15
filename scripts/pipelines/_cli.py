"""
Shared CLI harness for DataForSEO pipeline scripts.

Each pipeline script (scripts/pipelines/<name>.py) maps 1:1 to one
agent.dataforseo class. Rather than hand-writing near-identical argparse
wiring 14 times, every script just calls run_pipeline(SomeClient, "name"):
this harness introspects the class's public methods and exposes each as a
subcommand, taking a JSON task (inline or from a file) and writing the
result to dataforseo/compiled/.

Cost accounting: every call goes through DataForSEOClient._post/_get,
which accumulates the real `cost` field from each response onto
client.total_cost (see agent/dataforseo/client.py). This harness prints
that total after every run — never a hardcoded per-endpoint estimate.
For ai_optimization/llm_responses/* methods specifically, results also
carry input_tokens/output_tokens/money_spent per item (real LLM token
usage, distinct from the DataForSEO API's own call cost); those are
summed and printed too when present.
"""
import argparse
import inspect
import json
from datetime import date
from pathlib import Path

from agent.dataforseo.client import DataForSEORecoveryError

# Fields DataForSEO's llm_responses/* endpoints (ChatGPT/Claude/Gemini/
# Perplexity) attach to each result item. Absent on every other endpoint.
TOKEN_FIELDS = ("input_tokens", "output_tokens", "money_spent")

COMPILED_DIR = Path(__file__).resolve().parent.parent.parent / "dataforseo" / "compiled"


def _public_methods(client_cls: type) -> dict:
    """Every non-underscore method defined on the class (task/GET wrappers).
    DataForSEOClient's own helpers are all underscore-prefixed, so the base
    class contributes nothing here — only the subclass's real API methods."""
    return {
        name: member
        for name, member in inspect.getmembers(client_cls, predicate=inspect.isfunction)
        if not name.startswith("_")
    }


def _method_params(func) -> tuple[list[str], bool]:
    sig = inspect.signature(func)
    params = [name for name in sig.parameters if name != "self"]
    has_var_kw = any(
        p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
    )
    return params, has_var_kw


def _add_subcommand(subparsers, name: str, func) -> None:
    params, has_var_kw = _method_params(func)
    doc = (func.__doc__ or "").strip()
    help_text = doc.splitlines()[0].strip() if doc else name
    sub = subparsers.add_parser(name, help=help_text, description=doc or None)

    if "tasks" in params:
        group = sub.add_mutually_exclusive_group(required=True)
        group.add_argument(
            "--tasks-file",
            help="JSON file containing a list of task dicts (see the method's docstring for shape)",
        )
        group.add_argument(
            "--task",
            help="Single task as an inline JSON object string",
        )
    if "task_id" in params:
        sub.add_argument("--task-id", required=True, help="DataForSEO task ID")
    if has_var_kw:
        sub.add_argument(
            "--poll-interval", type=float, default=None,
            help="Seconds between polls (Standard Queue methods only; default set by the method)",
        )
        sub.add_argument(
            "--max-wait", type=float, default=None,
            help="Max seconds to wait for results (Standard Queue methods only; default set by the method)",
        )
    sub.add_argument(
        "--output", default=None,
        help="Output JSON path (default: dataforseo/compiled/<pipeline>-<method>-<date>.json)",
    )
    sub.set_defaults(_params=params, _has_var_kw=has_var_kw)


def _build_kwargs(args) -> dict:
    kwargs = {}
    if "tasks" in args._params:
        if args.tasks_file:
            tasks = json.loads(Path(args.tasks_file).read_text(encoding="utf-8"))
        else:
            tasks = [json.loads(args.task)]
        kwargs["tasks"] = tasks
    if "task_id" in args._params:
        kwargs["task_id"] = args.task_id
    if args._has_var_kw:
        if args.poll_interval is not None:
            kwargs["poll_interval"] = args.poll_interval
        if args.max_wait is not None:
            kwargs["max_wait"] = args.max_wait
    return kwargs


def _print_cost_summary(client, result) -> None:
    print(f"DataForSEO API cost this run: ${client.total_cost:.4f}")

    items = result if isinstance(result, list) else [result]
    totals = {field: 0 for field in TOKEN_FIELDS}
    found_tokens = False
    for item in items:
        if not isinstance(item, dict):
            continue
        for field in TOKEN_FIELDS:
            if field in item and item[field] is not None:
                found_tokens = True
                totals[field] += item[field]

    if found_tokens:
        print(
            f"LLM token usage: {totals['input_tokens']} input / "
            f"{totals['output_tokens']} output tokens, "
            f"${totals['money_spent']:.4f} money_spent"
        )


def run_pipeline(client_cls: type, pipeline_name: str) -> None:
    """Entry point every scripts/pipelines/<name>.py script calls.

    Args:
        client_cls: A DataForSEOClient subclass, e.g. GoogleOrganicSERP.
        pipeline_name: Short slug used in default output filenames, e.g. "serp-google-organic".
    """
    methods = _public_methods(client_cls)
    parser = argparse.ArgumentParser(
        prog=f"{pipeline_name}.py",
        description=(client_cls.__doc__ or client_cls.__name__).strip(),
    )
    subparsers = parser.add_subparsers(dest="method", required=True)
    for name, func in sorted(methods.items()):
        _add_subcommand(subparsers, name, func)
    args = parser.parse_args()

    kwargs = _build_kwargs(args)

    client = client_cls()
    method = getattr(client, args.method)
    recovery = None
    try:
        result = method(**kwargs)
    except DataForSEORecoveryError as exc:
        recovery = exc
        result = exc.results
        print(
            f"Recovery required: {len(exc.task_ids)} submitted task(s) remain "
            f"pending or uncertain. "
            f"Manifest: {exc.manifest_path or 'unavailable'}"
        )
        print(
            "Submitted task IDs: "
            + (", ".join(exc.task_ids) if exc.task_ids else "none")
        )
        print(f"Partial results: {len(exc.results)}")
        for error in exc.errors:
            print(
                f"Task {error.get('task_id', 'unknown')} failed: "
                f"{error.get('error', 'unknown error')}"
            )

    output_path = (
        Path(args.output) if args.output
        else COMPILED_DIR / f"{pipeline_name}-{args.method.replace('_', '-')}-{date.today()}.json"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    count = len(result) if isinstance(result, list) else 1
    print(f"Wrote {count} result(s) to {output_path}")
    _print_cost_summary(client, result)
    if recovery is not None:
        print("Partial results were written; recover the pending task IDs from the manifest.")
