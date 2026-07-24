from agent.dataforseo.client import DataForSEOClient


class ChatGPTResponses(DataForSEOClient):

    def models(self) -> list[dict]:
        """
        GET /ai_optimization/chat_gpt/llm_responses/models

        Lists ChatGPT model names available for llm_responses calls, and
        whether each supports web search and task_post (queued) mode.

        Result dict contains:
            model_name, web_search_supported, task_post_supported
        """
        data = self._get("ai_optimization/chat_gpt/llm_responses/models")
        return self._extract_results(data)

    def live(self, tasks: list[dict]) -> list[dict]:
        """
        POST /ai_optimization/chat_gpt/llm_responses/live

        Sends a prompt to ChatGPT and returns the model's response
        synchronously, optionally with web search grounding.

        Each task dict may contain:
            user_prompt                  (str, required)
            model_name                    (str)   e.g. "o4-mini", default set by DataForSEO
            system_message                (str)
            message_chain                 (list[dict])  prior turns: [{role: "user"|"ai", message: str}]
            max_output_tokens             (int)
            temperature                   (float)  0-2
            top_p                         (float)  0-1
            web_search                    (bool)   default False
            web_search_country_iso_code    (str)   e.g. "FR", requires web_search=True
            tag                           (str)

        Each result dict contains:
            model_name, input_tokens, output_tokens, web_search, money_spent,
            datetime, items [{type, sections: [{type, text, annotations}]}]
        """
        data = self._post("ai_optimization/chat_gpt/llm_responses/live", tasks)
        return self._extract_results(data)

    def task_post(self, tasks: list[dict]) -> list[dict]:
        """
        POST /ai_optimization/chat_gpt/llm_responses/task_post

        Queues a ChatGPT prompt for asynchronous processing. Takes the
        same task dict fields as live(). Poll tasks_ready() then fetch
        with task_get(task_id).

        Result dict is null; the task id is on the task envelope, not
        the result — inspect the raw task via self._post return value
        if you need it, or use tasks_ready() to discover completed ids.
        """
        data = self._post("ai_optimization/chat_gpt/llm_responses/task_post", tasks)
        return self._extract_results(data)

    def tasks_ready(self) -> list[dict]:
        """
        GET /ai_optimization/chat_gpt/llm_responses/tasks_ready

        Lists queued llm_responses tasks that have finished processing
        and are ready to fetch with task_get().

        Result dict contains:
            id, se, function, date_posted, tag, endpoint
        """
        data = self._get("ai_optimization/chat_gpt/llm_responses/tasks_ready")
        return self._extract_results(data)

    def task_get(self, task_id: str) -> list[dict]:
        """
        GET /ai_optimization/chat_gpt/llm_responses/task_get/{id}

        Fetches the result of a previously queued task_post() task.

        Each result dict contains:
            model_name, input_tokens, output_tokens, web_search, money_spent,
            datetime, items [{type, sections: [{type, text, annotations}]}]
        """
        data = self._get(f"ai_optimization/chat_gpt/llm_responses/task_get/{task_id}")
        return self._extract_results(data)

    @staticmethod
    def _extract_results(data: dict) -> list[dict]:
        tasks = data.get("tasks", [])
        if not tasks:
            return []
        return tasks[0].get("result") or []
