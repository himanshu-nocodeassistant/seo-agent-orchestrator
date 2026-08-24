import json
import os
import random
import sys
import threading
import time
from datetime import datetime, timezone
from uuid import uuid4
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
MAX_RETRY_DELAY = 30.0
MAX_POLL_SECONDS = 30 * 60
DEFAULT_CONNECT_TIMEOUT = 10.0
DEFAULT_READ_TIMEOUT = 60.0


def _jittered_backoff(attempt: int) -> float:
    """Full-jitter exponential backoff, capped at 30s."""
    cap = min(RETRY_BACKOFF_BASE * (2 ** attempt), 30.0)
    return random.uniform(0, cap)


class _TokenBucket:
    """Thread-safe token bucket used to rate-limit DataForSEO task creation."""

    def __init__(self, rate_per_minute: float):
        self.capacity = max(1.0, float(rate_per_minute))
        self.tokens = self.capacity
        self.rate = self.capacity / 60.0
        self.updated_at = time.monotonic()
        self._lock = threading.Lock()

    def consume(self, tokens: float = 1.0) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                self.tokens = min(
                    self.capacity,
                    self.tokens + (now - self.updated_at) * self.rate,
                )
                self.updated_at = now
                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return
                wait = (tokens - self.tokens) / self.rate if self.rate > 0 else 60.0
            time.sleep(min(wait, 1.0))


_TASK_BUCKET = None


def _get_task_bucket() -> _TokenBucket:
    """Shared token bucket across all client instances (per-process)."""
    global _TASK_BUCKET
    if _TASK_BUCKET is None:
        rate = float(os.environ.get("DATAFORSEO_TASKS_PER_MINUTE", "100"))
        _TASK_BUCKET = _TokenBucket(rate)
    return _TASK_BUCKET


class DataForSEOError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(f"DataForSEO error {status_code}: {message}")


class TaskNotReadyError(DataForSEOError):
    """Raised when a task_get is called but results aren't ready yet."""
    pass


class DataForSEORecoveryError(DataForSEOError):
    """A submitted task needs recovery from its preserved manifest."""

    def __init__(self, task_ids: list[str], manifest_path: str | None, message: str):
        self.task_ids = list(task_ids)
        self.manifest_path = manifest_path
        super().__init__(0, message)


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
        self._last_manifest_path: str | None = None

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
        kwargs.setdefault("timeout", self._request_timeout())
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

                retry_after = response.headers.get("Retry-After")
                if retry_after and attempt < MAX_RETRIES - 1:
                    try:
                        delay = min(max(float(retry_after), 0.0), MAX_RETRY_DELAY)
                    except (ValueError, TypeError):
                        delay = _jittered_backoff(attempt)
                    time.sleep(delay)
                    continue

            if attempt < MAX_RETRIES - 1:
                time.sleep(_jittered_backoff(attempt))

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

        Payloads are chunked into batches of at most
        ``DATAFORSEO_MAX_TASKS_PER_REQUEST`` (default 100 — DataForSEO's
        per-request cap) and every task consumes a token from the shared
        per-process rate limiter (``DATAFORSEO_TASKS_PER_MINUTE``, default
        100). One manifest covering all chunks is written at the end.
        """
        if not payload:
            return []
        batch_size = max(
            1, int(os.environ.get("DATAFORSEO_MAX_TASKS_PER_REQUEST", "100"))
        )
        task_ids = []
        request_payloads = []
        manifest_path = None
        for start in range(0, len(payload), batch_size):
            chunk = payload[start:start + batch_size]
            _get_task_bucket().consume(len(chunk))
            data = self._post(endpoint, chunk)
            for task, req in zip(data.get("tasks", []), chunk):
                task_status = task.get("status_code")
                if task_status == TASK_CREATED_STATUS:
                    task_ids.append(task["id"])
                    request_payloads.append(req)
                else:
                    if task_ids:
                        manifest_path = self._write_manifest(
                            endpoint,
                            request_payloads,
                            task_ids,
                            manifest_path=manifest_path,
                        )
                        self._last_manifest_path = manifest_path
                    raise DataForSEOError(
                        task_status,
                        task.get("status_message", "Task creation failed"),
                    )
            manifest_path = self._write_manifest(
                endpoint,
                request_payloads,
                task_ids,
                manifest_path=manifest_path,
            )
            self._last_manifest_path = manifest_path
        self._last_manifest_path = manifest_path
        return task_ids

    @staticmethod
    def _write_manifest(
        endpoint: str,
        payload: list,
        task_ids: list[str],
        manifest_path: str | None = None,
    ) -> str:
        """Persist {task_id: request_task} to logs/task_manifests/ so a crash
        during polling can resume from disk instead of losing the IDs."""
        os.makedirs(MANIFEST_DIR, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
        safe_endpoint = endpoint.strip("/").replace("/", "_")
        manifest_path = manifest_path or os.path.join(
            MANIFEST_DIR,
            f"{timestamp}_{uuid4().hex[:12]}_{safe_endpoint}.json",
        )
        manifest = {
            "endpoint": endpoint,
            "created_at": timestamp,
            "tasks": [
                {"task_id": task_id, "request": req}
                for task_id, req in zip(task_ids, payload)
            ],
        }
        tmp_path = manifest_path + ".tmp"
        with open(tmp_path, "w") as f:
            json.dump(manifest, f, indent=2)
        os.replace(tmp_path, manifest_path)
        return manifest_path

    @staticmethod
    def _request_timeout() -> tuple[float, float]:
        def read_timeout(name: str, default: float) -> float:
            try:
                return max(float(os.environ.get(name, default)), 0.1)
            except (TypeError, ValueError):
                return default

        return (
            read_timeout("DATAFORSEO_CONNECT_TIMEOUT_SECONDS", DEFAULT_CONNECT_TIMEOUT),
            read_timeout("DATAFORSEO_READ_TIMEOUT_SECONDS", DEFAULT_READ_TIMEOUT),
        )

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
        manifest_path = getattr(self, "_last_manifest_path", None)

        all_results = []
        skipped = []
        pending = list(task_ids)
        # Global deadline across all tasks: one round polls every still-pending
        # task, so a batch of N tasks takes O(max_wait) worst case instead of
        # O(N × max_wait).
        effective_max_wait = min(max_wait, MAX_POLL_SECONDS)
        deadline = time.monotonic() + effective_max_wait
        while pending:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                skipped.extend(pending)
                break
            time.sleep(min(poll_interval, remaining))
            still_pending = []
            for task_id in pending:
                try:
                    data = self._task_get(get_endpoint, task_id)
                    tasks = data.get("tasks", [])
                    if tasks:
                        result = tasks[0].get("result") or []
                        all_results.extend(result)
                        # Remove earlier not-ready snapshots for this keyword/location;
                        # they have no value once the final result is on disk.
                        purge_stale_poll_logs(tasks[0])
                except TaskNotReadyError:
                    still_pending.append(task_id)
            pending = still_pending

        if skipped:
            print(
                f"Warning: {len(skipped)} task(s) not ready after {effective_max_wait}s, "
                f"recoverable from manifest {manifest_path}: {skipped}"
            )
            raise DataForSEORecoveryError(
                skipped,
                manifest_path,
                f"Polling stopped after {effective_max_wait}s; recover task IDs "
                f"from {manifest_path or 'the DataForSEO manifest'}.",
            )

        return all_results

    @staticmethod
    def _check_status(data: dict):
        status = data.get("status_code")
        if status not in (TASK_READY_STATUS, TASK_CREATED_STATUS):
            raise DataForSEOError(status, data.get("status_message", "Unknown error"))
