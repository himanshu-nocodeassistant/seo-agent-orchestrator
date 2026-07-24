from agent.dataforseo.client import DataForSEOClient


class GeminiScraper(DataForSEOClient):

    def live_advanced(self, tasks: list[dict]) -> list[dict]:
        """
        POST /ai_optimization/gemini/llm_scraper/live/advanced

        Scrapes a live Gemini web response for a keyword and returns
        the parsed answer (markdown, sources, search results) alongside
        the raw items.

        Each task dict may contain:
            keyword                 (str, required)
            location_name / location_code
            language_name / language_code
            force_web_search          (bool)  default False
            device                    (str)   "desktop" (default) or "mobile"
            os                        (str)   e.g. "windows", "macos"
            tag                       (str)

        Each result dict contains:
            keyword, location_code, language_code, check_url, datetime,
            markdown, search_results, sources, se_results_count,
            item_types, items_count, items [{type, rank_group, rank_absolute, markdown, sources}]
        """
        data = self._post("ai_optimization/gemini/llm_scraper/live/advanced", tasks)
        return self._extract_results(data)

    def live_html(self, tasks: list[dict]) -> list[dict]:
        """
        POST /ai_optimization/gemini/llm_scraper/live/html

        Scrapes a live Gemini web response for a keyword and returns
        the raw rendered HTML instead of parsed content.

        Each task dict may contain:
            keyword                 (str, required)
            location_name / location_code
            language_name / language_code
            force_web_search          (bool)  default False
            device                    (str)   "desktop" (default) or "mobile"
            os                        (str)   e.g. "windows", "macos"
            tag                       (str)

        Each result dict contains:
            keyword, location_code, language_code, datetime, items_count,
            items [{page, date, html}]
        """
        data = self._post("ai_optimization/gemini/llm_scraper/live/html", tasks)
        return self._extract_results(data)

    def task_post(self, tasks: list[dict]) -> list[dict]:
        """
        POST /ai_optimization/gemini/llm_scraper/task_post

        Queues a Gemini scrape for asynchronous processing. Takes the
        same task dict fields as live_advanced()/live_html(). Poll
        tasks_ready() then fetch with task_get_advanced()/task_get_html().
        """
        data = self._post("ai_optimization/gemini/llm_scraper/task_post", tasks)
        return self._extract_results(data)

    def tasks_ready(self) -> list[dict]:
        """
        GET /ai_optimization/gemini/llm_scraper/tasks_ready

        Lists queued llm_scraper tasks that have finished processing
        and are ready to fetch.

        Result dict contains:
            id, se, function, date_posted, tag, endpoint_advanced, endpoint_html
        """
        data = self._get("ai_optimization/gemini/llm_scraper/tasks_ready")
        return self._extract_results(data)

    def task_get_advanced(self, task_id: str) -> list[dict]:
        """
        GET /ai_optimization/gemini/llm_scraper/task_get/advanced/{id}

        Fetches the parsed result of a previously queued task_post() task.

        Each result dict contains:
            keyword, location_code, language_code, check_url, datetime,
            markdown, search_results, sources, se_results_count,
            item_types, items_count, items [{type, rank_group, rank_absolute, markdown, sources}]
        """
        data = self._get(f"ai_optimization/gemini/llm_scraper/task_get/advanced/{task_id}")
        return self._extract_results(data)

    def task_get_html(self, task_id: str) -> list[dict]:
        """
        GET /ai_optimization/gemini/llm_scraper/task_get/html/{id}

        Fetches the raw HTML result of a previously queued task_post() task.

        Each result dict contains:
            keyword, location_code, language_code, datetime, items_count,
            items [{page, date, html}]
        """
        data = self._get(f"ai_optimization/gemini/llm_scraper/task_get/html/{task_id}")
        return self._extract_results(data)

    def locations(self) -> list[dict]:
        """
        GET /ai_optimization/gemini/llm_scraper/locations

        Lists locations supported by the Gemini scraper.

        Result dict contains:
            location_code, location_name, location_code_parent,
            country_iso_code, location_type
        """
        data = self._get("ai_optimization/gemini/llm_scraper/locations")
        return self._extract_results(data)

    def languages(self) -> list[dict]:
        """
        GET /ai_optimization/gemini/llm_scraper/languages

        Lists languages supported by the Gemini scraper.

        Result dict contains:
            language_name, language_code
        """
        data = self._get("ai_optimization/gemini/llm_scraper/languages")
        return self._extract_results(data)

    @staticmethod
    def _extract_results(data: dict) -> list[dict]:
        tasks = data.get("tasks", [])
        if not tasks:
            return []
        return tasks[0].get("result") or []
