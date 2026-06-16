from integrations.base import Integration
from integrations.swiggy_client import SwiggyClient, SwiggyError
from integrations.swiggy_tools import SWIGGY_TOOLS
from utils.logger import get_logger

log = get_logger(__name__)


class SwiggyIntegration(Integration):
    name = "swiggy"

    def __init__(self, client: SwiggyClient) -> None:
        self._swiggy = client
        self._pending_order: dict | None = None
        self._pending_order_type: str | None = None  # "food" or "grocery"

    def is_available(self) -> bool:
        return bool(self._swiggy)

    @classmethod
    def get_tools(cls) -> list[dict]:
        return SWIGGY_TOOLS

    def get_pending_order(self) -> dict | None:
        return self._pending_order

    def dispatch(self, tool_name: str, args: dict) -> dict:
        try:
            # --- Shared ---
            if tool_name == "swiggy_get_addresses":
                addresses = self._swiggy.get_addresses()
                return {"addresses": addresses}

            # --- Food ---
            elif tool_name == "swiggy_search_food":
                restaurants = self._swiggy.search_restaurants(args["address_id"], args["query"])
                return {"restaurants": restaurants}

            elif tool_name == "swiggy_get_menu":
                menu = self._swiggy.get_menu(args["restaurant_id"])
                return {"menu": menu}

            elif tool_name == "swiggy_update_food_cart":
                result = self._swiggy.update_food_cart(args["restaurant_id"], args["items"])
                return {"success": True, "cart": result}

            elif tool_name == "swiggy_get_food_cart":
                cart = self._swiggy.get_food_cart()
                return {"cart": cart}

            elif tool_name == "swiggy_place_food_order":
                cart = self._swiggy.get_food_cart()
                self._pending_order = cart
                self._pending_order_type = "food"
                return {
                    "confirmation_required": True,
                    "order_summary": cart,
                    "payment_method": "Cash on Delivery",
                    "message": "Order summary ready. Awaiting user confirmation via button.",
                }

            elif tool_name == "swiggy_confirm_food_order":
                if not self._pending_order:
                    return {"error": "No pending food order to confirm."}
                result = self._swiggy.place_food_order()
                self._pending_order = None
                self._pending_order_type = None
                return {"success": True, "order": result}

            elif tool_name == "swiggy_track_food_order":
                status = self._swiggy.track_food_order(args["order_id"])
                return {"tracking": status}

            # --- Grocery ---
            elif tool_name == "swiggy_search_grocery":
                products = self._swiggy.search_products(args["address_id"], args["query"])
                return {"products": products}

            elif tool_name == "swiggy_update_grocery_cart":
                result = self._swiggy.update_grocery_cart(args["items"])
                return {"success": True, "cart": result}

            elif tool_name == "swiggy_get_grocery_cart":
                cart = self._swiggy.get_grocery_cart()
                return {"cart": cart}

            elif tool_name == "swiggy_place_grocery_order":
                cart = self._swiggy.get_grocery_cart()
                self._pending_order = cart
                self._pending_order_type = "grocery"
                return {
                    "confirmation_required": True,
                    "order_summary": cart,
                    "payment_method": "Cash on Delivery",
                    "message": "Order summary ready. Awaiting user confirmation via button.",
                }

            elif tool_name == "swiggy_confirm_grocery_order":
                if not self._pending_order:
                    return {"error": "No pending grocery order to confirm."}
                result = self._swiggy.checkout_grocery()
                self._pending_order = None
                self._pending_order_type = None
                return {"success": True, "order": result}

            # --- Dineout ---
            elif tool_name == "swiggy_search_dineout":
                restaurants = self._swiggy.search_dineout(args["query"], args["latitude"], args["longitude"])
                return {"restaurants": restaurants}

            elif tool_name == "swiggy_get_dineout_slots":
                slots = self._swiggy.get_slots(
                    args["restaurant_id"], args["date"], args["latitude"], args["longitude"]
                )
                return {"slots": slots}

            elif tool_name == "swiggy_book_table":
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

            elif tool_name == "swiggy_get_booking_status":
                status = self._swiggy.get_booking_status(args["order_id"])
                return {"booking": status}

            else:
                return {"error": f"Unknown Swiggy tool: {tool_name}"}

        except SwiggyError as e:
            log.error("swiggy_integration: api error", tool=tool_name, error=str(e))
            return {"error": str(e)}
        except Exception as e:
            log.error("swiggy_integration: dispatch error", tool=tool_name, error=str(e))
            return {"error": str(e)}
