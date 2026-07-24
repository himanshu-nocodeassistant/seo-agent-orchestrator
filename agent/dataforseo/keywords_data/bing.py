from agent.dataforseo.client import DataForSEOClient


class BingKeywords(DataForSEOClient):

    # ── Standard Queue methods (preferred — ~3x cheaper) ──────────────

    def search_volume(self, tasks: list[dict], **poll_kwargs) -> list[dict]:
        """
        Standard Queue end-to-end for Bing search volume data.
        ~3x cheaper than search_volume_live. Average turnaround ~5 minutes.

        Each task dict may contain:
            keywords              (list[str], required)  max 1000, 100 chars each
            location_code         (int)    e.g. 2840
            language_code         (str)    "en", "fr", or "de"
            device                (str)    "all", "mobile", "desktop", "tablet"
            sort_by               (str)    "relevance", "search_volume", "cpc", "competition"
            search_partners       (bool)   default False
            date_from / date_to   (str)    "YYYY-MM-DD"
            tag                   (str)

        Additional kwargs: poll_interval (float), max_wait (float)
        """
        return self._task_post_and_poll(
            "keywords_data/bing/search_volume/task_post",
            "keywords_data/bing/search_volume/task_get",
            tasks,
            **poll_kwargs,
        )

    def keywords_for_site(self, tasks: list[dict], **poll_kwargs) -> list[dict]:
        """
        Standard Queue end-to-end for Bing keywords-for-site data.

        Each task dict may contain:
            target                (str, required)  domain or URL
            location_code         (int)
            language_code         (str)
            keywords_negative     (list[str])  max 200
            device                (str)
            sort_by               (str)
            search_partners       (bool)
            date_from / date_to   (str)
            tag                   (str)

        Additional kwargs: poll_interval (float), max_wait (float)
        """
        return self._task_post_and_poll(
            "keywords_data/bing/keywords_for_site/task_post",
            "keywords_data/bing/keywords_for_site/task_get",
            tasks,
            **poll_kwargs,
        )

    def keywords_for_keywords(self, tasks: list[dict], **poll_kwargs) -> list[dict]:
        """
        Standard Queue end-to-end for Bing keywords-for-keywords data.

        Each task dict may contain:
            keywords              (list[str], required)  up to 200 seeds, 100 chars each
            location_code         (int)
            language_code         (str)
            keywords_negative     (list[str])  max 200
            device                (str)
            sort_by               (str)
            search_partners       (bool)
            date_from / date_to   (str)
            tag                   (str)

        Additional kwargs: poll_interval (float), max_wait (float)
        """
        return self._task_post_and_poll(
            "keywords_data/bing/keywords_for_keywords/task_post",
            "keywords_data/bing/keywords_for_keywords/task_get",
            tasks,
            **poll_kwargs,
        )

    def keyword_performance(self, tasks: list[dict], **poll_kwargs) -> list[dict]:
        """
        Standard Queue end-to-end for Bing keyword performance data.

        Each task dict may contain:
            keywords              (list[str], required)  max 1000
            location_code         (int)
            language_code         (str)
            device                (str)
            match                 (str)    "aggregate", "broad", "phrase", "exact"
            tag                   (str)

        Additional kwargs: poll_interval (float), max_wait (float)
        """
        return self._task_post_and_poll(
            "keywords_data/bing/keyword_performance/task_post",
            "keywords_data/bing/keyword_performance/task_get",
            tasks,
            **poll_kwargs,
        )

    # ── Live methods (instant but expensive — use only when needed) ───

    def search_volume_live(self, tasks: list[dict]) -> list[dict]:
        """
        POST /keywords_data/bing/search_volume/live

        Instant results. Prefer search_volume() for cost savings.

        Each task dict may contain:
            keywords              (list[str], required)
            location_code         (int)    e.g. 2840 for United States
            language_code         (str)    "en", "fr", or "de"
            device                (str)    "all" (default), "mobile", "desktop", "tablet"
            sort_by               (str)    "relevance" (default), "search_volume", "cpc", "competition"
            search_partners       (bool)   include Bing/Yahoo/AOL partners, default False
            date_from             (str)    "YYYY-MM-DD", min 24 months back
            date_to               (str)    "YYYY-MM-DD", max one month from today
            tag                   (str)    user-defined identifier, max 255 chars

        Returns list of dicts with:
            keyword, location_code, language_code, device, search_partners,
            search_volume, cpc, competition, monthly_searches
        """
        data = self._post("keywords_data/bing/search_volume/live", tasks)
        return self._extract_results(data)

    def keywords_for_site_live(self, tasks: list[dict]) -> list[dict]:
        """
        POST /keywords_data/bing/keywords_for_site/live

        Instant results. Prefer keywords_for_site() for cost savings.

        Each task dict may contain:
            target                (str, required)  domain or URL
            location_code         (int)
            language_code         (str)    "en", "fr", or "de"
            keywords_negative     (list[str])  terms to exclude, max 200
            device                (str)    "all" (default), "mobile", "desktop", "tablet"
            sort_by               (str)    "relevance" (default), "search_volume", "cpc", "competition"
            search_partners       (bool)   default False
            date_from             (str)    "YYYY-MM-DD"
            date_to               (str)    "YYYY-MM-DD"
            tag                   (str)

        Returns list of keyword result dicts (same shape as search_volume_live).
        """
        data = self._post("keywords_data/bing/keywords_for_site/live", tasks)
        return self._extract_results(data)

    def keywords_for_keywords_live(self, tasks: list[dict]) -> list[dict]:
        """
        POST /keywords_data/bing/keywords_for_keywords/live

        Instant results. Prefer keywords_for_keywords() for cost savings.

        Each task dict may contain:
            keywords              (list[str], required)  up to 200 seeds, 100 chars each
            location_code         (int)
            language_code         (str)    "en", "fr", or "de"
            keywords_negative     (list[str])  terms to exclude, max 200
            device                (str)    "all" (default), "mobile", "desktop", "tablet"
            sort_by               (str)    "relevance" (default), "search_volume", "cpc", "competition"
            search_partners       (bool)   default False
            date_from             (str)    "YYYY-MM-DD"
            date_to               (str)    "YYYY-MM-DD"
            tag                   (str)

        Returns list of keyword idea dicts (same shape as search_volume_live).
        """
        data = self._post("keywords_data/bing/keywords_for_keywords/live", tasks)
        return self._extract_results(data)

    def keyword_performance_live(self, tasks: list[dict]) -> list[dict]:
        """
        POST /keywords_data/bing/keyword_performance/live

        Instant results. Prefer keyword_performance() for cost savings.

        Each task dict may contain:
            keywords              (list[str], required)
            location_code         (int)
            language_code         (str)
            device                (str)    "all" (default), "desktop", "mobile", "tablet"
            match                 (str)    "aggregate" (default), "broad", "phrase", "exact"
            tag                   (str)

        Each result dict contains:
            keyword, location_code, language_code, year, month,
            keyword_kpi: {
                desktop: [{ad_position, clicks, impressions, average_cpc, ctr, total_cost, average_bid}],
                mobile:  [...],
                tablet:  [...],
            }
        """
        data = self._post("keywords_data/bing/keyword_performance/live", tasks)
        return self._extract_results(data)

    @staticmethod
    def _extract_results(data: dict) -> list[dict]:
        tasks = data.get("tasks", [])
        if not tasks:
            return []
        return tasks[0].get("result") or []
