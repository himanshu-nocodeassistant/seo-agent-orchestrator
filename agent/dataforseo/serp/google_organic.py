from agent.dataforseo.client import DataForSEOClient


class GoogleOrganicSERP(DataForSEOClient):

    def task_post(self, tasks: list[dict]) -> list[str]:
        """
        POST /serp/google/organic/task_post

        Submit SERP tasks to the Standard Queue ($0.0006/SERP).
        Returns a list of task IDs to retrieve later with task_get().

        Each task dict may contain:
            keyword                   (str, required)
            location_code             (int)   e.g. 2840 for United States
            language_code             (str)   e.g. "en"
            depth                     (int)   results to retrieve, default 10, max 200
            device                    (str)   "desktop" or "mobile"
            os                        (str)   "windows", "macos", "android", "ios"
            priority                  (int)   1 = normal (default), 2 = high
            postback_url              (str)   webhook URL for results
            pingback_url              (str)   webhook URL for task-ready notification
            tag                       (str)   user-defined identifier
        """
        return self._task_post("serp/google/organic/task_post", tasks)

    def task_get(self, task_id: str) -> dict:
        """
        GET /serp/google/organic/task_get/advanced/{task_id}

        Retrieve results for a completed Standard Queue task.
        Returns the first result dict with items (organic, featured_snippet,
        people_also_ask, knowledge_graph, etc.).

        Raises TaskNotReadyError if results are not yet available.
        """
        data = self._task_get("serp/google/organic/task_get/advanced", task_id)
        return self._extract_result(data)

    def search(self, tasks: list[dict], **poll_kwargs) -> list[dict]:
        """
        Standard Queue end-to-end: submit tasks, poll until ready, return results.
        ~3x cheaper than live_advanced ($0.0006 vs $0.002 per SERP).
        Average turnaround ~5 minutes.

        Accepts the same task dicts as task_post(). Additional kwargs:
            poll_interval  (float)  seconds between polls, default 10
            max_wait       (float)  max seconds to wait, default 300
        """
        return self._task_post_and_poll(
            "serp/google/organic/task_post",
            "serp/google/organic/task_get/advanced",
            tasks,
            **poll_kwargs,
        )

    def live_advanced(self, tasks: list[dict]) -> dict:
        """
        POST /serp/google/organic/live/advanced

        Single request, instant results. $0.002/SERP — prefer search() for cost savings.

        Each task dict may contain:
            keyword                   (str, required)
            location_code             (int)   e.g. 2840 for United States
            language_code             (str)   e.g. "en"
            depth                     (int)   results to retrieve, default 10, max 200
            device                    (str)   "desktop" or "mobile"
            os                        (str)   "windows", "macos", "android", "ios"
            people_also_ask_click_depth (int) expand PAA boxes, 1-4

        Returns the first result dict with items (organic, featured_snippet,
        people_also_ask, knowledge_graph, etc.).
        """
        data = self._post("serp/google/organic/live/advanced", tasks)
        return self._extract_result(data)

    @staticmethod
    def _extract_result(data: dict) -> dict:
        tasks = data.get("tasks", [])
        if not tasks:
            return {}
        result_list = tasks[0].get("result") or []
        if not result_list:
            return {}
        return result_list[0]
