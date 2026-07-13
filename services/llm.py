"""
Multi-provider LLM client — supports Groq, Anthropic, and OpenAI.

Exposes an OpenAI-shaped response interface (response.choices[0].message.tool_calls /
.content) for all three providers so ConversationManager needs no changes.
"""
import json

import anthropic

from config.settings import get_settings
from utils.logger import get_logger

log = get_logger(__name__)

PROVIDERS = ("groq", "anthropic", "openai")


# ---------------------------------------------------------------------------
# Anthropic compatibility wrappers
# ---------------------------------------------------------------------------

class _ToolFunction:
    def __init__(self, name: str, arguments: str) -> None:
        self.name = name
        self.arguments = arguments


class _ToolCall:
    def __init__(self, id: str, name: str, input_dict: dict) -> None:
        self.id = id
        self.function = _ToolFunction(name, json.dumps(input_dict))


class _Message:
    def __init__(self, tool_calls: list | None, content: str) -> None:
        self.tool_calls = tool_calls
        self.content = content


class _Choice:
    def __init__(self, message: _Message) -> None:
        self.message = message


class _Response:
    def __init__(self, choices: list) -> None:
        self.choices = choices


# ---------------------------------------------------------------------------
# LLMClient
# ---------------------------------------------------------------------------

class LLMClient:
    """
    Unified client for Groq, Anthropic, and OpenAI.

    Args:
        provider: "groq" | "anthropic" | "openai"
        api_keys: {"groq": "...", "anthropic": "...", "openai": "..."}
        tools: list of tool dicts in OpenAI function-calling format
    """

    def __init__(self, provider: str, api_keys: dict, tools: list[dict] | None = None) -> None:
        if provider not in PROVIDERS:
            raise ValueError(f"Unknown provider '{provider}'. Choose from: {PROVIDERS}")

        self._provider = provider
        self._tools_raw = tools or []
        self._system_prompt: str = ""
        self._history: list = []

        settings = get_settings()

        if provider == "groq":
            from groq import Groq
            self._client = Groq(api_key=api_keys.get("groq", ""))
            self._model = settings.GROQ_MODEL

        elif provider == "anthropic":
            self._client = anthropic.Anthropic(api_key=api_keys.get("anthropic", ""))
            self._model = settings.ANTHROPIC_MODEL
            self._ant_tools = self._to_anthropic_tools(self._tools_raw)

        elif provider == "openai":
            import openai as _oai
            self._client = _oai.OpenAI(api_key=api_keys.get("openai", ""))
            self._model = settings.OPENAI_MODEL

        log.info("llm: client initialised", provider=provider, model=self._model, tools=len(self._tools_raw))

    # ------------------------------------------------------------------
    # Tool format conversion
    # ------------------------------------------------------------------

    def _to_anthropic_tools(self, tools: list[dict]) -> list[dict]:
        result = []
        for t in tools:
            if t.get("type") == "function":
                fn = t["function"]
                result.append({
                    "name": fn["name"],
                    "description": fn.get("description", ""),
                    "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
                })
        return result

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def start_chat(self, system_prompt: str) -> "LLMClient":
        """Set system prompt and reset history. Returns self for chaining."""
        self._system_prompt = system_prompt
        self._history = []
        return self

    def send_message(self, user_text: str):
        """Append user message and return a completion response."""
        if self._provider == "anthropic":
            self._history.append({"role": "user", "content": user_text})
            return self._ant_call()
        else:
            self._history.append({"role": "user", "content": user_text})
            return self._oai_call()

    def send_tool_result(self, tool_call_id: str, name: str, result: str):
        """Append a tool result and return the next completion."""
        if self._provider == "anthropic":
            self._history.append({
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": tool_call_id, "content": result}],
            })
            return self._ant_call(max_tokens=512)
        else:
            self._history.append({
                "role": "tool",
                "tool_call_id": tool_call_id,
                "name": name,
                "content": result,
            })
            return self._oai_call(max_tokens=512)

    # ------------------------------------------------------------------
    # Provider-specific internals
    # ------------------------------------------------------------------

    def _oai_call(self, max_tokens: int = 1024):
        """Shared implementation for Groq and OpenAI (both OpenAI-compatible)."""
        messages = [{"role": "system", "content": self._system_prompt}] + self._history
        kwargs: dict = dict(model=self._model, messages=messages, max_tokens=max_tokens)
        if self._tools_raw:
            kwargs["tools"] = self._tools_raw
            kwargs["tool_choice"] = "auto"
        response = self._client.chat.completions.create(**kwargs)

        # Serialize assistant message back into history as a plain dict so
        # both providers always have serializable history entries.
        msg = response.choices[0].message
        entry: dict = {"role": "assistant", "content": msg.content}
        if msg.tool_calls:
            entry["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in msg.tool_calls
            ]
        self._history.append(entry)
        return response

    def _ant_call(self, max_tokens: int = 1024) -> _Response:
        """Call Anthropic and return a compatibility-wrapped response."""
        kwargs: dict = dict(
            model=self._model,
            system=self._system_prompt,
            messages=self._history,
            max_tokens=max_tokens,
        )
        if self._ant_tools:
            kwargs["tools"] = self._ant_tools

        response = self._client.messages.create(**kwargs)

        assistant_content: list = []
        tool_calls: list[_ToolCall] = []
        text_content: str = ""

        for block in response.content:
            if block.type == "text":
                text_content = block.text
                assistant_content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                tool_calls.append(_ToolCall(block.id, block.name, block.input))
                assistant_content.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })

        self._history.append({"role": "assistant", "content": assistant_content})
        message = _Message(tool_calls=tool_calls if tool_calls else None, content=text_content)
        return _Response([_Choice(message)])
