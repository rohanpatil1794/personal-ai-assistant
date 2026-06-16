from groq import Groq

from config.settings import get_settings
from utils.logger import get_logger

log = get_logger(__name__)


class LLMClient:
    """
    Wraps the Groq client. Holds conversation history and system prompt
    because Groq uses stateless chat completions (no server-side session).
    Tools are injected at construction time via the IntegrationRegistry.
    """

    def __init__(self, api_key: str, tools: list[dict] | None = None) -> None:
        self._client = Groq(api_key=api_key)
        self._model = get_settings().GROQ_MODEL
        self._tools = tools or []
        self._system_prompt: str = ""
        self._history: list[dict] = []
        log.info("llm: client initialised", model=self._model, tools=len(self._tools))

    def start_chat(self, system_prompt: str) -> "LLMClient":
        """Set system prompt and reset history. Returns self for chaining."""
        self._system_prompt = system_prompt
        self._history = []
        return self

    def send_message(self, user_text: str) -> object:
        """Append user message and get a completion from Groq."""
        self._history.append({"role": "user", "content": user_text})
        messages = [{"role": "system", "content": self._system_prompt}] + self._history

        response = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            tools=self._tools,
            tool_choice="auto",
            max_tokens=1024,
        )
        self._history.append(response.choices[0].message)
        return response

    def send_tool_result(self, tool_call_id: str, name: str, result: str) -> object:
        """Append a tool result and get the next completion."""
        import json
        self._history.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": name,
            "content": result,
        })
        messages = [{"role": "system", "content": self._system_prompt}] + self._history
        response = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            tools=self._tools,
            tool_choice="auto",
            max_tokens=512,
        )
        self._history.append(response.choices[0].message)
        return response
