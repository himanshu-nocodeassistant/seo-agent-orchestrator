from agent.dataforseo.client import DataForSEOClient


class GoogleLabs(DataForSEOClient):

    def related_keywords_live(self, tasks: list[dict]) -> list[dict]:
        """
        POST /dataforseo_labs/google/related_keywords/live

        Returns keywords related to a seed keyword, based on Google's
        "searches related to" suggestions, up to a search depth of 4
        (each depth level expands related keywords of related keywords).

        Each task dict may contain:
            keyword         (str, required)
            location_name    (str)   e.g. "United States"
            location_code    (int)   e.g. 2840
            language_name     (str)   e.g. "English"
            language_code     (str)   e.g. "en"
            depth             (int)   0-4, default 1
            include_seed_keyword (bool)  include data for the seed keyword itself
            include_serp_info    (bool)  include SERP data for each keyword
            ignore_synonyms      (bool)
            filters           (list)
            order_by          (list[str])
            limit             (int)   max 1000, default 100
            offset            (int)
            tag               (str)

        Each result dict contains:
            seed_keyword, seed_keyword_data, location_code, language_code,
            total_count, items_count,
            items [{keyword_data, depth, related_keywords}]
        """
        data = self._post("dataforseo_labs/google/related_keywords/live", tasks)
        return self._extract_results(data)

    def keyword_suggestions_live(self, tasks: list[dict]) -> list[dict]:
        """
        POST /dataforseo_labs/google/keyword_suggestions/live

        Returns keywords that contain the seed keyword as a substring
        (full-text search phrase match), along with search volume, CPC,
        competition, and SERP data.

        Each task dict may contain:
            keyword               (str, required)
            location_name / location_code
            language_name / language_code
            include_seed_keyword   (bool)
            include_serp_info      (bool)
            exact_match             (bool)  only keywords containing exact seed phrase
            filters                (list)
            order_by               (list[str])
            limit                  (int)   max 1000, default 100
            offset                 (int)
            tag                    (str)

        Each result dict contains:
            seed_keyword, seed_keyword_data, location_code, language_code,
            total_count, items_count, items [keyword_data...]
        """
        data = self._post("dataforseo_labs/google/keyword_suggestions/live", tasks)
        return self._extract_results(data)

    def keyword_ideas_live(self, tasks: list[dict]) -> list[dict]:
        """
        POST /dataforseo_labs/google/keyword_ideas/live

        Returns keyword ideas relevant to the product/service categories
        of up to 200 seed keywords (keywords that fall into the same
        categories as the seeds, not necessarily containing them).

        Each task dict may contain:
            keywords               (list[str], required)  max 200 seeds
            location_name / location_code
            language_name / language_code
            closely_variants        (bool)  narrower, more closely related ideas
            include_serp_info       (bool)
            ignore_synonyms         (bool)
            filters                 (list)
            order_by                (list[str])
            limit                   (int)   max 1000, default 100
            offset                  (int)
            tag                     (str)

        Each result dict contains:
            seed_keywords, location_code, language_code,
            total_count, items_count, items [keyword_data...]
        """
        data = self._post("dataforseo_labs/google/keyword_ideas/live", tasks)
        return self._extract_results(data)

    def ranked_keywords_live(self, tasks: list[dict]) -> list[dict]:
        """
        POST /dataforseo_labs/google/ranked_keywords/live

        Returns keywords that a given domain ranks for in Google's organic
        and/or paid search results, with rank position, search volume,
        traffic estimation, and SERP info.

        Each task dict may contain:
            target                  (str, required)  domain
            location_name / location_code
            language_name / language_code
            item_types               (list[str])  "organic", "paid"
            load_rank_absolute       (bool)  include absolute SERP rank
            include_serp_info        (bool)
            include_clickstream_data (bool)
            filters                  (list)
            order_by                 (list[str])
            limit                    (int)   max 1000, default 100
            offset                   (int)
            tag                      (str)

        Each result dict contains:
            target, location_code, language_code,
            total_count, items_count, items [{keyword_data, ranked_serp_element}]
        """
        data = self._post("dataforseo_labs/google/ranked_keywords/live", tasks)
        return self._extract_results(data)

    def competitors_domain_live(self, tasks: list[dict]) -> list[dict]:
        """
        POST /dataforseo_labs/google/competitors_domain/live

        Returns domains that compete with the target domain in organic
        search, ranked by number of shared keywords and estimated traffic.

        Each task dict may contain:
            target                    (str, required)  domain
            location_name / location_code
            language_name / language_code
            exclude_top_domains        (bool)
            ignore_synonyms             (bool)
            intersecting_domains        (list[str])  restrict comparison to these domains
            item_types                  (list[str])  "organic", "paid"
            max_rank_group               (int)
            filters                     (list)
            order_by                    (list[str])
            limit                       (int)   max 1000, default 100
            offset                      (int)
            tag                         (str)

        Each result dict contains:
            target, location_code, language_code,
            total_count, items_count,
            items [{domain, avg_position, sum_position, intersections, ...metrics}]
        """
        data = self._post("dataforseo_labs/google/competitors_domain/live", tasks)
        return self._extract_results(data)

    def domain_intersection_live(self, tasks: list[dict]) -> list[dict]:
        """
        POST /dataforseo_labs/google/domain_intersection/live

        Compares two domains and returns keywords both rank for in Google
        organic/paid search — useful for content gap / competitor overlap
        analysis.

        Each task dict may contain:
            target1                  (str, required)  domain
            target2                  (str, required)  domain
            location_name / location_code
            language_name / language_code
            item_types                (list[str])  "organic", "paid"
            include_serp_info         (bool)
            include_clickstream_data  (bool)
            intersections              (bool)  True = keywords both rank for (default),
                                                False = keywords only target1 ranks for
            filters                   (list)
            order_by                  (list[str])
            limit                     (int)   max 1000, default 100
            offset                    (int)
            tag                       (str)

        Each result dict contains:
            target1, target2, location_code, language_code,
            total_count, items_count,
            items [{keyword_data, first_domain_serp_element, second_domain_serp_element}]
        """
        data = self._post("dataforseo_labs/google/domain_intersection/live", tasks)
        return self._extract_results(data)

    def domain_rank_overview_live(self, tasks: list[dict]) -> list[dict]:
        """
        POST /dataforseo_labs/google/domain_rank_overview/live

        Returns an overview of a domain's organic and paid search
        performance in Google: total keyword count, estimated traffic,
        and traffic cost, broken down by position ranges.

        Each task dict may contain:
            target                (str, required)  domain
            location_name / location_code
            language_name / language_code
            ignore_synonyms         (bool)
            item_types              (list[str])  "organic", "paid"
            tag                     (str)

        Each result dict contains:
            target, location_code, language_code,
            total_count, items_count,
            items [{se_type, metrics: {organic, paid}}]
        """
        data = self._post("dataforseo_labs/google/domain_rank_overview/live", tasks)
        return self._extract_results(data)

    @staticmethod
    def _extract_results(data: dict) -> list[dict]:
        tasks = data.get("tasks", [])
        if not tasks:
            return []
        return tasks[0].get("result") or []
