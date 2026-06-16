from groq import Groq

from integrations.ha_tools import HA_TOOLS
from integrations.swiggy_tools import SWIGGY_TOOLS
from utils.logger import get_logger

ALL_TOOLS = HA_TOOLS + SWIGGY_TOOLS

log = get_logger(__name__)

MODEL_NAME = "llama-3.1-8b-instant"


class LLMClient:
    """
    Wraps the Groq client. Holds conversation history and system prompt
    because Groq uses stateless chat completions (no server-side session).
    """

    def __init__(self, api_key: str) -> None:
        self._client = Groq(api_key=api_key)
        self._system_prompt: str = ""
        self._history: list[dict] = []
        log.info("llm: client initialised", model=MODEL_NAME)

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
            model=MODEL_NAME,
            messages=messages,
            tools=ALL_TOOLS,
            tool_choice="auto",
            max_tokens=1024,
        )
        # Append assistant message to history (may contain tool_calls)
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
            model=MODEL_NAME,
            messages=messages,
            tools=ALL_TOOLS,
            tool_choice="auto",
            max_tokens=512,
        )
        self._history.append(response.choices[0].message)
        return response
