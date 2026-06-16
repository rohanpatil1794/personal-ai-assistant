"""
Manages the LLM conversation and the tool-call / tool-result exchange.
Uses the Groq SDK (OpenAI-compatible chat completions).
"""
import json

from integrations.ha_client import HAClient
from integrations.swiggy_client import SwiggyClient, SwiggyError
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
- For food/grocery orders, always call swiggy_get_addresses first, then ask the user which address to use before searching.
- Never place a food or grocery order without first calling swiggy_place_food_order or swiggy_place_grocery_order to show the user a summary. The UI will display a confirmation button — wait for that before confirming.
- For dine-out bookings, only book FREE reservations. Paid deals are not supported in v1.
- Payment for food and grocery orders is always Cash on Delivery (COD).
- Always confirm what you did in ONE short, friendly spoken sentence (no markdown).
- If you are unsure which entity or item the user means, ask for clarification.
- For general questions, answer conversationally.
- When the user says "__confirm_order__", call swiggy_confirm_food_order or swiggy_confirm_grocery_order based on the active pending order.
- When the user says "cancel the order", simply acknowledge cancellation — no tool call needed.
""".strip()


class ConversationManager:
    def __init__(self, llm: LLMClient, ha: HAClient, swiggy: SwiggyClient) -> None:
        self._llm = llm
        self._ha = ha
        self._swiggy = swiggy
        self._started = False
        self._pending_order: dict | None = None
        self._pending_order_type: str | None = None  # "food" or "grocery"

    def start(self) -> None:
        """Fetch HA entities and initialise the chat session."""
        try:
            entities = self._ha.get_states()
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
        """Returns the pending order summary if a confirmation is awaited."""
        return self._pending_order

    def send(self, user_text: str) -> str:
        """Send a user message, handle tool calls, and return the final reply."""
        if not self._started:
            raise LLMError("ConversationManager.start() has not been called.")

        # Handle cancel sentinel without involving the LLM tool loop
        if user_text.strip() == "cancel the order":
            self._pending_order = None
            self._pending_order_type = None

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
                    tool_result = self._dispatch_tool(tc.function.name, args)
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

    def _dispatch_tool(self, name: str, args: dict) -> dict:
        """Route a tool call to the appropriate client."""
        try:
            # --- Home Assistant ---
            if name == "get_ha_entities":
                domain = args.get("domain") or None
                entities = self._ha.get_states(domain=domain)
                return {"entities": entities}

            elif name == "control_ha_entity":
                entity_id = args["entity_id"]
                action = args["action"]
                kwargs = {}
                if "brightness_pct" in args:
                    kwargs["brightness_pct"] = args["brightness_pct"]
                if "color_name" in args:
                    kwargs["color_name"] = args["color_name"]
                if action == "turn_on":
                    self._ha.turn_on(entity_id, **kwargs)
                elif action == "turn_off":
                    self._ha.turn_off(entity_id)
                elif action == "toggle":
                    self._ha.toggle(entity_id)
                else:
                    return {"error": f"Unknown action: {action}"}
                return {"success": True, "entity_id": entity_id, "action": action}

            elif name == "activate_ha_scene":
                self._ha.activate_scene(args["scene_entity_id"])
                return {"success": True, "scene": args["scene_entity_id"]}

            elif name == "call_ha_service":
                result = self._ha.call_service(
                    args["domain"],
                    args["service"],
                    args.get("service_data", {}),
                )
                return {"success": True, "result": result}

            # --- Swiggy shared ---
            elif name == "swiggy_get_addresses":
                addresses = self._swiggy.get_addresses()
                return {"addresses": addresses}

            # --- Swiggy food ---
            elif name == "swiggy_search_food":
                restaurants = self._swiggy.search_restaurants(args["address_id"], args["query"])
                return {"restaurants": restaurants}

            elif name == "swiggy_get_menu":
                menu = self._swiggy.get_menu(args["restaurant_id"])
                return {"menu": menu}

            elif name == "swiggy_update_food_cart":
                result = self._swiggy.update_food_cart(args["restaurant_id"], args["items"])
                return {"success": True, "cart": result}

            elif name == "swiggy_get_food_cart":
                cart = self._swiggy.get_food_cart()
                return {"cart": cart}

            elif name == "swiggy_place_food_order":
                # Preview only — fetch current cart, store as pending, signal UI
                cart = self._swiggy.get_food_cart()
                self._pending_order = cart
                self._pending_order_type = "food"
                return {
                    "confirmation_required": True,
                    "order_summary": cart,
                    "payment_method": "Cash on Delivery",
                    "message": "Order summary ready. Awaiting user confirmation via button.",
                }

            elif name == "swiggy_confirm_food_order":
                if not self._pending_order:
                    return {"error": "No pending food order to confirm."}
                result = self._swiggy.place_food_order()
                self._pending_order = None
                self._pending_order_type = None
                return {"success": True, "order": result}

            elif name == "swiggy_track_food_order":
                status = self._swiggy.track_food_order(args["order_id"])
                return {"tracking": status}

            # --- Swiggy grocery ---
            elif name == "swiggy_search_grocery":
                products = self._swiggy.search_products(args["address_id"], args["query"])
                return {"products": products}

            elif name == "swiggy_update_grocery_cart":
                result = self._swiggy.update_grocery_cart(args["items"])
                return {"success": True, "cart": result}

            elif name == "swiggy_get_grocery_cart":
                cart = self._swiggy.get_grocery_cart()
                return {"cart": cart}

            elif name == "swiggy_place_grocery_order":
                cart = self._swiggy.get_grocery_cart()
                self._pending_order = cart
                self._pending_order_type = "grocery"
                return {
                    "confirmation_required": True,
                    "order_summary": cart,
                    "payment_method": "Cash on Delivery",
                    "message": "Order summary ready. Awaiting user confirmation via button.",
                }

            elif name == "swiggy_confirm_grocery_order":
                if not self._pending_order:
                    return {"error": "No pending grocery order to confirm."}
                result = self._swiggy.checkout_grocery()
                self._pending_order = None
                self._pending_order_type = None
                return {"success": True, "order": result}

            # --- Swiggy dineout ---
            elif name == "swiggy_search_dineout":
                restaurants = self._swiggy.search_dineout(args["query"], args["latitude"], args["longitude"])
                return {"restaurants": restaurants}

            elif name == "swiggy_get_dineout_slots":
                slots = self._swiggy.get_slots(
                    args["restaurant_id"], args["date"], args["latitude"], args["longitude"]
                )
                return {"slots": slots}

            elif name == "swiggy_book_table":
                result = self._swiggy.book_table(
                    args["restaurant_id"],
                    args["slot_id"],
                    args["item_id"],
                    args["reservation_time"],
                    args["guest_count"],
                    args["latitude"],
                    args["longitude"],
                )
                return {"success": True, "booking": result}

            elif name == "swiggy_get_booking_status":
                status = self._swiggy.get_booking_status(args["order_id"])
                return {"booking": status}

            else:
                return {"error": f"Unknown tool: {name}"}

        except SwiggyError as e:
            log.error("conversation: swiggy error", tool=name, error=str(e))
            return {"error": str(e)}
        except Exception as e:
            log.error("conversation: tool dispatch error", tool=name, error=str(e))
            return {"error": str(e)}
