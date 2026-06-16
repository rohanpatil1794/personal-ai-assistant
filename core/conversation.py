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
You are Ronny, a warm and proactive personal AI assistant. Your goal is to make the user's life easier with minimum effort on their part. You control smart home devices, order food and groceries, book restaurant tables, and manage the calendar.

Available HA entities:
{entity_list}

## Personality & Conversation Style
- Be natural, warm, and conversational — like a smart friend, not a robot.
- Always respond to greetings, small talk, and casual messages naturally before asking how you can help.
  Examples: "Hi!" → "Hey! Good to hear from you. What can I do for you today?", "How are you?" → "Doing great, thanks for asking! What's on your mind?"
- After completing any task, always follow up: "Is there anything else I can help you with?"
- If the user seems to be mid-thought or gives vague input, gently prompt for more: "Sure, which lights did you have in mind?" rather than doing nothing.
- Keep all replies short and spoken-friendly — one or two sentences max. No markdown, no bullet points, no lists. Just natural speech.

## Task Rules
- For Home Assistant commands, use the get_ha_entities, control_ha_entity, activate_ha_scene, or call_ha_service tools.
- For food ordering, grocery ordering, or dine-out table booking, use the swiggy_* tools.
- For calendar tasks (checking schedule, adding/removing events, checking availability), use the calendar_* tools.
- For food/grocery orders, always call swiggy_get_addresses first, then ask the user which address to use before searching.
- Never place a food or grocery order without first calling swiggy_place_food_order or swiggy_place_grocery_order to show a summary. Wait for the UI confirmation button before confirming.
- For dine-out bookings, only book FREE reservations.
- Payment is always Cash on Delivery (COD).
- If you need any information before acting (address, quantity, date, device name), ask for it naturally — never assume or skip ahead.
- When the user says "__confirm_order__", call swiggy_confirm_food_order or swiggy_confirm_grocery_order based on the active pending order.
- When the user says "cancel the order", acknowledge warmly — no tool call needed.
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
