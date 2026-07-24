from agent.dataforseo.client import DataForSEOClient


class PerplexityResponses(DataForSEOClient):

    def models(self) -> list[dict]:
        """
        GET /ai_optimization/perplexity/llm_responses/models

        Lists Perplexity model names available for llm_responses calls,
        and whether each supports web search and task_post (queued) mode.

        Result dict contains:
            model_name, web_search_supported, task_post_supported
        """
        data = self._get("ai_optimization/perplexity/llm_responses/models")
        return self._extract_results(data)

    def live(self, tasks: list[dict]) -> list[dict]:
        """
        POST /ai_optimization/perplexity/llm_responses/live

        Sends a prompt to Perplexity and returns the model's response
        synchronously. Perplexity does not support task_post — this is
        the only way to call it.

        Each task dict may contain:
            user_prompt                  (str, required)
            model_name                    (str)   e.g. "sonar", default set by DataForSEO
            system_message                (str)
            message_chain                 (list[dict])  prior turns: [{role: "user"|"ai", message: str}]
            max_output_tokens             (int)
            temperature                   (float)
            top_p                         (float)  0-1
            web_search_country_iso_code    (str)   e.g. "FR"
            tag                           (str)

        Each result dict contains:
            model_name, input_tokens, output_tokens, web_search, money_spent,
            datetime, items [{type, sections: [{type, text, annotations}]}]
        """
        data = self._post("ai_optimization/perplexity/llm_responses/live", tasks)
        return self._extract_results(data)

    @staticmethod
    def _extract_results(data: dict) -> list[dict]:
        tasks = data.get("tasks", [])
        if not tasks:
            return []
        return tasks[0].get("result") or []
