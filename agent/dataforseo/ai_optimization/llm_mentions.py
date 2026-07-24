from agent.dataforseo.client import DataForSEOClient


class LLMMentions(DataForSEOClient):

    def locations_and_languages(self) -> list[dict]:
        """
        GET /ai_optimization/llm_mentions/locations_and_languages

        Lists locations supported by llm_mentions, each with its
        available languages.

        Result dict contains:
            location_code, location_name,
            available_languages [{language_name, language_code}]
        """
        data = self._get("ai_optimization/llm_mentions/locations_and_languages")
        return self._extract_results(data)

    def available_filters(self) -> list[dict]:
        """
        GET /ai_optimization/llm_mentions/available_filters

        Lists filterable fields and their types for the search() endpoint.

        Result dict contains:
            search: {platform, location_code, language_code, ai_search_volume, ...} (field: type map)
        """
        data = self._get("ai_optimization/llm_mentions/available_filters")
        return self._extract_results(data)

    def search_live(self, tasks: list[dict]) -> list[dict]:
        """
        POST /ai_optimization/llm_mentions/search/live

        Searches AI-generated answers (Google AI Overviews, ChatGPT,
        etc.) for mentions of a domain and/or keyword, returning the
        matching question/answer pairs with source citations.

        Each task dict may contain:
            target                  (list[dict], required)  e.g.
                                     [{"domain": "example.com", "search_filter": "include"|"exclude"},
                                      {"keyword": "bmw", "search_scope": ["answer","question"]}]
            platform                 (str)   e.g. "google", "chat_gpt"
            location_name / location_code
            language_name / language_code
            filters                  (list)
            order_by                 (list[str])
            limit                    (int)
            offset                   (int)
            search_after_token        (str)   pagination cursor from a previous response
            tag                      (str)

        Each result dict contains:
            total_count, current_offset, search_after_token, items_count,
            items [{platform, location_code, language_code, question, answer,
                     sources, search_results, ai_search_volume, ...}]
        """
        data = self._post("ai_optimization/llm_mentions/search/live", tasks)
        return self._extract_results(data)

    def aggregated_metrics_live(self, tasks: list[dict]) -> list[dict]:
        """
        POST /ai_optimization/llm_mentions/aggregated_metrics/live

        Returns aggregated mention/search-volume/impression metrics for
        a target, grouped by location, language, platform, and citing
        domain.

        Each task dict may contain:
            target                       (list[dict], required)  same shape as search_live()
            platform                      (str)
            location_name / location_code
            language_name / language_code
            initial_dataset_filters        (list)
            internal_list_limit            (int)   max items per group, default 10
            tag                           (str)

        Result dict contains:
            total: {location, language, platform, sources_domain, search_results_domain}
                   — each a list of {type: "group_element", key, mentions,
                                      ai_search_volume, impressions}
        """
        data = self._post("ai_optimization/llm_mentions/aggregated_metrics/live", tasks)
        return self._extract_results(data)

    def cross_aggregated_metrics_live(self, tasks: list[dict]) -> list[dict]:
        """
        POST /ai_optimization/llm_mentions/cross_aggregated_metrics/live

        Same aggregation as aggregated_metrics_live(), but across
        multiple named targets in a single call (e.g. compare several
        brand/competitor keywords side by side).

        Each task dict may contain:
            targets                       (list[dict], required)
                                           [{"aggregation_key": str, "target": [...]}]
            platform                       (str)
            location_name / location_code
            language_name / language_code
            initial_dataset_filters        (list)
            internal_list_limit            (int)
            tag                           (str)

        Result dict contains:
            total: {location, language, platform, sources_domain, search_results_domain}
                   — each a list of {type: "group_element", key, mentions,
                                      ai_search_volume, impressions}
        """
        data = self._post("ai_optimization/llm_mentions/cross_aggregated_metrics/live", tasks)
        return self._extract_results(data)

    def top_domains_live(self, tasks: list[dict]) -> list[dict]:
        """
        POST /ai_optimization/llm_mentions/top_domains/live

        Returns the domains most frequently cited as sources (or
        appearing in underlying search results) for a target's AI
        mentions, ranked by mentions/search volume/impressions.

        Each task dict may contain:
            target                       (list[dict], required)  same shape as search_live()
            platform                      (str)
            location_name / location_code
            language_name / language_code
            links_scope                   (str)   "sources" or "search_results"
            initial_dataset_filters        (list)
            items_list_limit               (int)   max domains returned
            internal_list_limit            (int)
            tag                           (str)

        Result dict contains:
            total: {location, language, platform, sources_domain, search_results_domain},
            items [{key (domain), mentions, ai_search_volume, impressions}]
        """
        data = self._post("ai_optimization/llm_mentions/top_domains/live", tasks)
        return self._extract_results(data)

    def top_pages_live(self, tasks: list[dict]) -> list[dict]:
        """
        POST /ai_optimization/llm_mentions/top_pages/live

        Returns the individual pages most frequently cited as sources
        (or appearing in underlying search results) for a target's AI
        mentions, ranked by mentions/search volume/impressions.

        Each task dict may contain:
            target                       (list[dict], required)  same shape as search_live()
            platform                      (str)
            location_name / location_code
            language_name / language_code
            links_scope                   (str)   "sources" or "search_results"
            initial_dataset_filters        (list)
            items_list_limit               (int)   max pages returned
            internal_list_limit            (int)
            tag                           (str)

        Result dict contains:
            total: {location, language, platform, sources_domain, search_results_domain},
            items [{key (page URL), mentions, ai_search_volume, impressions}]
        """
        data = self._post("ai_optimization/llm_mentions/top_pages/live", tasks)
        return self._extract_results(data)

    @staticmethod
    def _extract_results(data: dict) -> list[dict]:
        tasks = data.get("tasks", [])
        if not tasks:
            return []
        return tasks[0].get("result") or []
