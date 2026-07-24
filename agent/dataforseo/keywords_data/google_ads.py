from agent.dataforseo.client import DataForSEOClient


class GoogleAdsKeywords(DataForSEOClient):

    # ── Standard Queue methods (preferred — ~3x cheaper) ──────────────

    def search_volume(self, tasks: list[dict], **poll_kwargs) -> list[dict]:
        """
        Standard Queue end-to-end for search volume data.
        ~3x cheaper than search_volume_live. Average turnaround ~5 minutes.

        Each task dict may contain:
            keywords                (list[str], required)  max 1000
            location_code           (int)    e.g. 2840
            language_code           (str)    e.g. "en"
            search_partners         (bool)   default False
            include_adult_keywords  (bool)   default False
            sort_by                 (str)    "relevance", "search_volume", etc.
            date_from / date_to     (str)    "YYYY-MM-DD"
            tag                     (str)

        Additional kwargs: poll_interval (float), max_wait (float)
        """
        return self._task_post_and_poll(
            "keywords_data/google_ads/search_volume/task_post",
            "keywords_data/google_ads/search_volume/task_get",
            tasks,
            **poll_kwargs,
        )

    def keywords_for_site(self, tasks: list[dict], **poll_kwargs) -> list[dict]:
        """
        Standard Queue end-to-end for keywords-for-site data.

        Each task dict may contain:
            target                  (str, required)  domain or URL
            target_type             (str)  "page" (default) or "site"
            location_code           (int)
            language_code           (str)
            search_partners         (bool)
            include_adult_keywords  (bool)
            sort_by                 (str)
            date_from / date_to     (str)
            tag                     (str)

        Additional kwargs: poll_interval (float), max_wait (float)
        """
        return self._task_post_and_poll(
            "keywords_data/google_ads/keywords_for_site/task_post",
            "keywords_data/google_ads/keywords_for_site/task_get",
            tasks,
            **poll_kwargs,
        )

    def keywords_for_keywords(self, tasks: list[dict], **poll_kwargs) -> list[dict]:
        """
        Standard Queue end-to-end for keywords-for-keywords data.

        Each task dict may contain:
            keywords                (list[str], required)  max 20 seeds
            location_code           (int)
            language_code           (str)
            search_partners         (bool)
            include_adult_keywords  (bool)
            sort_by                 (str)
            date_from / date_to     (str)
            tag                     (str)

        Additional kwargs: poll_interval (float), max_wait (float)
        """
        return self._task_post_and_poll(
            "keywords_data/google_ads/keywords_for_keywords/task_post",
            "keywords_data/google_ads/keywords_for_keywords/task_get",
            tasks,
            **poll_kwargs,
        )

    def ad_traffic_by_keywords(self, tasks: list[dict], **poll_kwargs) -> list[dict]:
        """
        Standard Queue end-to-end for ad traffic forecasts.

        Each task dict may contain:
            keywords        (list[str], required)  max 1000
            bid             (int, required)        max CPC bid in USD
            match           (str, required)        "exact", "broad", or "phrase"
            location_code   (int)
            language_code   (str)
            date_from / date_to  (str)
            date_interval   (str)  "next_week", "next_month", "next_quarter"
            sort_by         (str)
            tag             (str)

        Additional kwargs: poll_interval (float), max_wait (float)
        """
        return self._task_post_and_poll(
            "keywords_data/google_ads/ad_traffic_by_keywords/task_post",
            "keywords_data/google_ads/ad_traffic_by_keywords/task_get",
            tasks,
            **poll_kwargs,
        )

    # ── Live methods (instant but expensive — use only when needed) ───

    def search_volume_live(self, tasks: list[dict]) -> list[dict]:
        """
        POST /keywords_data/google_ads/search_volume/live

        Instant results. Prefer search_volume() for cost savings.

        Each task dict may contain:
            keywords                (list[str], required)
            location_code           (int)    e.g. 2840 for United States
            language_code           (str)    e.g. "en"
            search_partners         (bool)   include Google search partners, default False
            include_adult_keywords  (bool)   default False
            sort_by                 (str)    "relevance" (default), "search_volume",
                                             "competition_index", "low_top_of_page_bid",
                                             "high_top_of_page_bid"
            date_from               (str)    "YYYY-MM-DD", min 4 years back
            date_to                 (str)    "YYYY-MM-DD", max yesterday
            tag                     (str)    user-defined identifier, max 255 chars

        Each result dict contains:
            keyword, location_code, language_code, search_partners, spell,
            search_volume, competition ("LOW"/"MEDIUM"/"HIGH"), competition_index,
            cpc, low_top_of_page_bid, high_top_of_page_bid,
            monthly_searches [{year, month, search_volume}]
        """
        data = self._post("keywords_data/google_ads/search_volume/live", tasks)
        return self._extract_results(data)

    def keywords_for_site_live(self, tasks: list[dict]) -> list[dict]:
        """
        POST /keywords_data/google_ads/keywords_for_site/live

        Instant results. Prefer keywords_for_site() for cost savings.

        Each task dict may contain:
            target                  (str, required)  domain or URL
            target_type             (str)  "page" (default) or "site"
            location_code           (int)
            language_code           (str)
            search_partners         (bool)   default False
            include_adult_keywords  (bool)   default False
            sort_by                 (str)    "relevance" (default), "search_volume",
                                             "competition_index", "low_top_of_page_bid",
                                             "high_top_of_page_bid"
            date_from               (str)    "YYYY-MM-DD", min 4 years back
            date_to                 (str)    "YYYY-MM-DD", max yesterday
            tag                     (str)

        Each result dict contains:
            keyword, location_code, language_code, search_partners,
            search_volume, competition, competition_index, cpc,
            low_top_of_page_bid, high_top_of_page_bid,
            monthly_searches, keyword_annotations
        """
        data = self._post("keywords_data/google_ads/keywords_for_site/live", tasks)
        return self._extract_results(data)

    def keywords_for_keywords_live(self, tasks: list[dict]) -> list[dict]:
        """
        POST /keywords_data/google_ads/keywords_for_keywords/live

        Instant results. Prefer keywords_for_keywords() for cost savings.

        Each task dict may contain:
            keywords                (list[str], required)  max 20 seeds, 80 chars each
            location_code           (int)
            language_code           (str)
            search_partners         (bool)   default False
            include_adult_keywords  (bool)   default False
            sort_by                 (str)    "relevance" (default), "search_volume",
                                             "competition_index", "low_top_of_page_bid",
                                             "high_top_of_page_bid"
            date_from               (str)    "YYYY-MM-DD", min 4 years back
            date_to                 (str)    "YYYY-MM-DD", max yesterday
            tag                     (str)

        Returns same field shape as keywords_for_site_live.
        """
        data = self._post("keywords_data/google_ads/keywords_for_keywords/live", tasks)
        return self._extract_results(data)

    def ad_traffic_by_keywords_live(self, tasks: list[dict]) -> list[dict]:
        """
        POST /keywords_data/google_ads/ad_traffic_by_keywords/live

        Instant results. Prefer ad_traffic_by_keywords() for cost savings.

        Each task dict may contain:
            keywords        (list[str], required)  max 1000, 80 chars / 10 words each
            bid             (int, required)         max CPC bid in USD
            match           (str, required)         "exact", "broad", or "phrase"
            location_code   (int)
            language_code   (str)
            date_from       (str)    "YYYY-MM-DD", min tomorrow; required if date_to set
            date_to         (str)    "YYYY-MM-DD"; required if date_from set
            date_interval   (str)    "next_week", "next_month" (default), "next_quarter"
                                     (ignored when date_from/date_to are set)
            sort_by         (str)    "relevance" (default), "impressions", "ctr",
                                     "average_cpc", "cost", "clicks"
            tag             (str)

        Each result dict contains:
            keyword, location_code, language_code, bid, match, date_interval,
            clicks, average_cpc, cost
            (impressions and ctr are deprecated and always null)
        """
        data = self._post("keywords_data/google_ads/ad_traffic_by_keywords/live", tasks)
        return self._extract_results(data)

    @staticmethod
    def _extract_results(data: dict) -> list[dict]:
        tasks = data.get("tasks", [])
        if not tasks:
            return []
        return tasks[0].get("result") or []
