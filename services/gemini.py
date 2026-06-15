from google import genai
from google.genai import types

from integrations.ha_tools import HA_TOOLS
from utils.exceptions import GeminiError
from utils.logger import get_logger

log = get_logger(__name__)

MODEL_NAME = "gemini-1.5-flash"


class GeminiClient:
    def __init__(self, api_key: str) -> None:
        self._client = genai.Client(api_key=api_key)
        self._config = types.GenerateContentConfig(
            tools=HA_TOOLS,
        )
        log.info("gemini: client initialised", model=MODEL_NAME)

    def start_chat(self, system_prompt: str) -> genai.chats.Chat:
        """Start a new Chat session with a system instruction."""
        config = types.GenerateContentConfig(
            tools=HA_TOOLS,
            system_instruction=system_prompt,
        )
        return self._client.chats.create(model=MODEL_NAME, config=config)
