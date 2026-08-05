from agent.dataforseo.client import DataForSEOClient


class GoogleTrends(DataForSEOClient):

    def explore(self, tasks: list[dict], **poll_kwargs) -> list[dict]:
        """
        Standard Queue end-to-end for Google Trends data.
        ~3x cheaper than explore_live. Average turnaround ~5 minutes.

        Each task dict may contain:
            keywords        (list[str], required)  max 5, 2-100 chars each
            location_code   (int)    e.g. 2840; omit for global
            language_code   (str)    e.g. "en"
            type            (str)    "web", "news", "youtube", "images", "froogle"
            category_code   (int)    0 = all (default)
            date_from / date_to  (str)  "YYYY-MM-DD"
            time_range      (str)    preset range (ignored if date_from/date_to set)
            item_types      (list[str])  default ["google_trends_graph"]
            tag             (str)

        Additional kwargs: poll_interval (float), max_wait (float)
        """
        return self._task_post_and_poll(
            "keywords_data/google_trends/explore/task_post",
            "keywords_data/google_trends/explore/task_get",
            tasks,
            **poll_kwargs,
        )

    def explore_live(self, tasks: list[dict]) -> list[dict]:
        """
        POST /keywords_data/google_trends/explore/live

        Instant results. Prefer explore() for cost savings.
        Rate limit: 250 live requests per minute.

        Each task dict may contain:
            keywords        (list[str], required)  max 5 keywords, 2-100 chars each.
                            Commas are stripped. For topics_list or queries_list
                            item types, specify only 1 keyword.
            location_code   (int)    e.g. 2840 for United States; omit for global
            language_code   (str)    e.g. "en" (default)
            type            (str)    "web" (default), "news", "youtube", "images", "froogle"
            category_code   (int)    category to filter by; 0 = all (default)
            date_from       (str)    "YYYY-MM-DD"; min "2004-01-01" for web
            date_to         (str)    "YYYY-MM-DD"; default today
            time_range      (str)    preset range (ignored if date_from/date_to set):
                                     "past_hour", "past_4_hours", "past_day",
                                     "past_7_days", "past_30_days", "past_90_days",
                                     "past_12_months", "past_5_years",
                                     "2004_present" (web only), "2008_present"
            item_types      (list[str])  which result types to include; default ["google_trends_graph"]
                                     options: "google_trends_graph", "google_trends_map",
                                              "google_trends_topics_list",
                                              "google_trends_queries_list"
            tag             (str)    user-defined identifier, max 255 chars

        Each result dict contains:
            keywords, location_code, language_code, check_url, datetime,
            items_count, items — where each item is one of:

            google_trends_graph:
                data: [{date_from, date_to, timestamp, missing_data, values}]
                      values are relative popularity 0-100 (100 = peak)
                averages: [avg popularity per keyword over the full range]

            google_trends_map:
                data: [{geo_id, geo_name, values, max_value_index}]
                      values are relative popularity 0-100 per location

            google_trends_topics_list:
                data.top:    [{topic_id, topic_title, topic_type, value}]  0-100
                data.rising: [{topic_id, topic_title, topic_type, value}]  % increase

            google_trends_queries_list:
                data.top:    [{query, value}]  0-100
                data.rising: [{query, value}]  % increase
        """
        data = self._post("keywords_data/google_trends/explore/live", tasks)
        return self._extract_results(data)

    @staticmethod
    def _extract_results(data: dict) -> list[dict]:
        tasks = data.get("tasks", [])
        if not tasks:
            return []
        return tasks[0].get("result") or []
