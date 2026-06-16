"""
Manages the LLM conversation and the tool-call / tool-result exchange.
Uses the Groq SDK (OpenAI-compatible chat completions).
"""
import json

from integrations.ha_integration import HAIntegration
from core.registry import IntegrationRegistry
from services.llm import LLMClient
from utils.exceptions import GeminiError as LLMError
from utils.logger import get_logger

log = get_logger(__name__)

SYSTEM_PROMPT_TEMPLATE = """
You are Ronny, a helpful personal AI assistant. You control smart home devices via Home Assistant and can order food/groceries or book restaurant tables via Swiggy. When asked your name or who you are, always say you are Ronny, a personal AI assistant.

Available HA entities:
{entity_list}

Rules:
- For Home Assistant commands, use the get_ha_entities, control_ha_entity, activate_ha_scene, or call_ha_service tools.
- For food ordering, grocery ordering, or dine-out table booking, use the swiggy_* tools.
- For calendar tasks (checking schedule, adding/removing events, checking availability), use the calendar_* tools.
- For food/grocery orders, always call swiggy_get_addresses first, then ask the user which address to use before searching.
- Never place a food or grocery order without first calling swiggy_place_food_order or swiggy_place_grocery_order to show the user a summary. The UI will display a confirmation button — wait for that before confirming.
- For dine-out bookings, only book FREE reservations. Paid deals are not supported in v1.
- Payment for food and grocery orders is always Cash on Delivery (COD).
- Always confirm what you did in ONE short, friendly spoken sentence (no markdown).
- If you need any information before executing a command (address, quantity, date, device name, etc.), always ask the user for it first — never assume.
- For general questions, answer conversationally.
- When the user says "__confirm_order__", call swiggy_confirm_food_order or swiggy_confirm_grocery_order based on the active pending order.
- When the user says "cancel the order", simply acknowledge cancellation — no tool call needed.
""".strip()


class ConversationManager:
    def __init__(self, llm: LLMClient, ha: HAIntegration, registry: IntegrationRegistry) -> None:
        self._llm = llm
        self._ha = ha          # HAIntegration kept for start() entity fetch
        self._registry = registry
        self._started = False

    def start(self) -> None:
        """Fetch HA entities and initialise the chat session."""
        try:
            entities = self._ha._ha.get_states()
            useful_domains = {"light", "switch", "climate", "scene", "media_player", "fan", "cover", "input_boolean"}
            filtered = [e for e in entities if e["entity_id"].split(".")[0] in useful_domains]
            entity_lines = "\n".join(
                f"- {e['entity_id']} ({e['name']}): {e['state']}"
                for e in filtered[:80]
            )
        except Exception as e:
            log.warning("conversation: could not fetch HA entities", error=str(e))
            entity_lines = "(Could not fetch entity list)"

        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(entity_list=entity_lines)
        self._llm.start_chat(system_prompt)
        self._started = True
        log.info("conversation: session started")

    def get_pending_order(self) -> dict | None:
        """Returns the pending Swiggy order summary if a confirmation is awaited."""
        swiggy = self._registry.get_integration("swiggy")
        if swiggy is None:
            return None
        return swiggy.get_pending_order()

    def send(self, user_text: str) -> str:
        """Send a user message, handle tool calls, and return the final reply."""
        if not self._started:
            raise LLMError("ConversationManager.start() has not been called.")

        # Handle cancel sentinel: clear pending order without involving LLM
        if user_text.strip() == "cancel the order":
            swiggy = self._registry.get_integration("swiggy")
            if swiggy:
                swiggy._pending_order = None
                swiggy._pending_order_type = None

        log.info("conversation: user input", text=user_text)
        try:
            response = self._llm.send_message(user_text)
        except Exception as e:
            raise LLMError(f"LLM send_message failed: {e}") from e

        # Tool-call loop
        while True:
            message = response.choices[0].message

            if message.tool_calls:
                for tc in message.tool_calls:
                    args = json.loads(tc.function.arguments)
                    tool_result = self._registry.dispatch(tc.function.name, args)
                    log.info("conversation: tool result", tool=tc.function.name, result=str(tool_result)[:200])

                    try:
                        response = self._llm.send_tool_result(
                            tool_call_id=tc.id,
                            name=tc.function.name,
                            result=json.dumps(tool_result),
                        )
                    except Exception as e:
                        raise LLMError(f"LLM tool response failed: {e}") from e
            else:
                reply = (message.content or "").strip()
                log.info("conversation: assistant reply", text=reply[:100])
                return reply
