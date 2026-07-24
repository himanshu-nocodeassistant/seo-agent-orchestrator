import json
import os
import sys
import time
from dotenv import load_dotenv
import requests

from agent.dataforseo.logger import log_result, purge_stale_poll_logs

load_dotenv()

BASE_URL = "https://api.dataforseo.com/v3"
MANIFEST_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "dataforseo", "manifests")

TASK_READY_STATUS = 20000
TASK_CREATED_STATUS = 20100
TASK_IN_QUEUE_STATUS = 40601
TASK_NOT_READY_STATUSES = (40601, 40602)

# HTTP statuses worth retrying rather than failing outright: rate limits
# (429) and transient server-side issues (502/503/504).
RETRYABLE_HTTP_STATUSES = (429, 502, 503, 504)
MAX_RETRIES = 5
RETRY_BACKOFF_BASE = 2.0


class DataForSEOError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(f"DataForSEO error {status_code}: {message}")


class TaskNotReadyError(DataForSEOError):
    """Raised when a task_get is called but results aren't ready yet."""
    pass


class DataForSEOClient:
    def __init__(self, login: str = None, password: str = None):
        self.login = login or os.environ["DATAFORSEO_LOGIN"]
        self.password = password or os.environ["DATAFORSEO_PASSWORD"]
        self.session = requests.Session()
        self.session.auth = (self.login, self.password)
        self.session.headers.update({"Content-Type": "application/json"})
        # Cumulative real spend for this client instance, read from each
        # response's own `cost` field (not an estimate). Per-instance, not
        # global, so concurrent pipelines don't cross-contaminate totals.
        self.total_cost: float = 0.0

    def _accumulate_cost(self, data: dict) -> None:
        cost = data.get("cost")
        if isinstance(cost, (int, float)):
            self.total_cost += cost

    def _request_with_retry(self, method: str, url: str, **kwargs) -> requests.Response:
        """Issue an HTTP request, retrying on rate limits, transient server
        errors, and dropped connections with exponential backoff.

        Anything else (auth errors, 4xx other than 429, etc.) raises immediately.
        """
        last_exc = None
        for attempt in range(MAX_RETRIES):
            try:
                response = self.session.request(method, url, **kwargs)
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                last_exc = e
            else:
                if response.status_code not in RETRYABLE_HTTP_STATUSES:
                    response.raise_for_status()
                    return response
                last_exc = requests.exceptions.HTTPError(
                    f"{response.status_code} {response.reason}", response=response
                )

            if attempt < MAX_RETRIES - 1:
                backoff = RETRY_BACKOFF_BASE * (2 ** attempt)
                time.sleep(backoff)

        raise last_exc

    def _post(self, endpoint: str, payload: list) -> dict:
        url = f"{BASE_URL}/{endpoint.lstrip('/')}"
        response = self._request_with_retry("POST", url, json=payload)
        data = response.json()
        # Accumulate before _check_status can raise — a rejected/errored
        # call can still report nonzero cost, and that spend is real
        # regardless of whether we go on to raise for it.
        self._accumulate_cost(data)
        self._check_status(data)
        self._safe_log(endpoint, payload, data)
        return data

    def _get(self, endpoint: str) -> dict:
        url = f"{BASE_URL}/{endpoint.lstrip('/')}"
        response = self._request_with_retry("GET", url)
        data = response.json()
        self._accumulate_cost(data)
        self._check_status(data)
        self._safe_log(endpoint, [], data)
        return data

    @staticmethod
    def _safe_log(endpoint: str, payload: list, data: dict) -> None:
        """Log a call's raw response without ever letting a logging error
        propagate. The API is already billed by the time we log, so a logging
        bug must never discard a paid response (see the llm_mentions
        target-list crash that lost a paid call)."""
        try:
            log_result(endpoint, payload, data)
        except Exception as exc:  # noqa: BLE001 — logging must not mask paid data
            print(f"WARNING: failed to log {endpoint} response: {exc}", file=sys.stderr)

    def _task_post(self, endpoint: str, payload: list) -> list[str]:
        """Submit tasks to the Standard Queue. Returns a list of task IDs.

        Writes a manifest file immediately after tasks are created, so that
        IDs survive a crash anywhere downstream (polling errors, process
        kill, etc.) without needing to re-submit and re-bill the tasks.
        """
        data = self._post(endpoint, payload)
        task_ids = []
        for task in data.get("tasks", []):
            task_status = task.get("status_code")
            if task_status == TASK_CREATED_STATUS:
                task_ids.append(task["id"])
            else:
                raise DataForSEOError(
                    task_status,
                    task.get("status_message", "Task creation failed"),
                )
        self._write_manifest(endpoint, payload, task_ids)
        return task_ids

    @staticmethod
    def _write_manifest(endpoint: str, payload: list, task_ids: list[str]) -> str:
        """Persist {task_id: request_task} to logs/task_manifests/ so a crash
        during polling can resume from disk instead of losing the IDs."""
        os.makedirs(MANIFEST_DIR, exist_ok=True)
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        safe_endpoint = endpoint.strip("/").replace("/", "_")
        manifest_path = os.path.join(MANIFEST_DIR, f"{timestamp}_{safe_endpoint}.json")
        manifest = {
            "endpoint": endpoint,
            "created_at": timestamp,
            "tasks": [
                {"task_id": task_id, "request": req}
                for task_id, req in zip(task_ids, payload)
            ],
        }
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)
        return manifest_path

    def _task_get(self, endpoint: str, task_id: str) -> dict:
        """Retrieve results for a single completed task."""
        data = self._get(f"{endpoint}/{task_id}")
        for task in data.get("tasks", []):
            task_status = task.get("status_code")
            if task_status in TASK_NOT_READY_STATUSES:
                raise TaskNotReadyError(task_status, "Task still in queue")
            if task_status != TASK_READY_STATUS:
                raise DataForSEOError(
                    task_status,
                    task.get("status_message", "Task retrieval failed"),
                )
        return data

    def _task_post_and_poll(
        self,
        post_endpoint: str,
        get_endpoint: str,
        payload: list,
        poll_interval: float = 10,
        max_wait: float = 300,
    ) -> list[dict]:
        """Submit tasks, poll until ready, return all results.

        Args:
            post_endpoint: e.g. "serp/google/organic/task_post"
            get_endpoint:  e.g. "serp/google/organic/task_get/advanced"
            payload:       list of task dicts
            poll_interval: seconds between polls (default 10)
            max_wait:      max seconds to wait before giving up (default 300)

        Returns:
            Combined list of result dicts from all tasks.

        A task that isn't ready by max_wait is skipped (not raised) so one
        straggler can't discard results already collected for the rest of
        the batch. Skipped task IDs are still in the manifest written by
        _task_post, so they can be recovered later without re-billing.
        """
        task_ids = self._task_post(post_endpoint, payload)

        all_results = []
        skipped = []
        for task_id in task_ids:
            elapsed = 0.0
            while elapsed < max_wait:
                time.sleep(poll_interval)
                elapsed += poll_interval
                try:
                    data = self._task_get(get_endpoint, task_id)
                    tasks = data.get("tasks", [])
                    if tasks:
                        result = tasks[0].get("result") or []
                        all_results.extend(result)
                        # Remove earlier not-ready snapshots for this keyword/location;
                        # they have no value once the final result is on disk.
                        purge_stale_poll_logs(tasks[0])
                    break
                except TaskNotReadyError:
                    continue
            else:
                skipped.append(task_id)

        if skipped:
            print(
                f"Warning: {len(skipped)} task(s) not ready after {max_wait}s, "
                f"skipped (recoverable from manifest, not re-billed): {skipped}"
            )

        return all_results

    @staticmethod
    def _check_status(data: dict):
        status = data.get("status_code")
        if status not in (TASK_READY_STATUS, TASK_CREATED_STATUS):
            raise DataForSEOError(status, data.get("status_message", "Unknown error"))
