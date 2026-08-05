from agent.dataforseo.client import DataForSEOClient


class AIKeywordData(DataForSEOClient):

    def locations_and_languages(self) -> list[dict]:
        """
        GET /ai_optimization/ai_keyword_data/locations_and_languages

        Lists locations supported by AI keyword search volume, each
        with its available languages.

        Result dict contains:
            location_code, location_name,
            available_languages [{language_name, language_code}]
        """
        data = self._get("ai_optimization/ai_keyword_data/locations_and_languages")
        return self._extract_results(data)

    def keywords_search_volume_live(self, tasks: list[dict]) -> list[dict]:
        """
        POST /ai_optimization/ai_keyword_data/keywords_search_volume/live

        Returns estimated monthly search volume for keywords as asked
        of AI assistants/chatbots (distinct from traditional Google Ads
        search volume), with 12 months of history.

        Each task dict may contain:
            keywords                (list[str], required)
            location_name / location_code
            language_name / language_code
            tag                     (str)

        Each result dict contains:
            location_code, language_code, items_count,
            items [{keyword, ai_search_volume,
                     ai_monthly_searches: [{year, month, ai_search_volume}]}]
        """
        data = self._post("ai_optimization/ai_keyword_data/keywords_search_volume/live", tasks)
        return self._extract_results(data)

    @staticmethod
    def _extract_results(data: dict) -> list[dict]:
        tasks = data.get("tasks", [])
        if not tasks:
            return []
        return tasks[0].get("result") or []
