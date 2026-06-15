import google.generativeai as genai
from integrations.ha_tools import HA_TOOLS
from utils.exceptions import GeminiError
from utils.logger import get_logger

log = get_logger(__name__)

MODEL_NAME = "gemini-1.5-flash"


class GeminiClient:
    def __init__(self, api_key: str) -> None:
        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(
            model_name=MODEL_NAME,
            tools=HA_TOOLS,
        )
        log.info("gemini: model initialised", model=MODEL_NAME)

    def start_chat(self, system_prompt: str) -> genai.ChatSession:
        """Start a new ChatSession with a system instruction."""
        model = genai.GenerativeModel(
            model_name=MODEL_NAME,
            tools=HA_TOOLS,
            system_instruction=system_prompt,
        )
        return model.start_chat(enable_automatic_function_calling=False)
