from integrations.base import Integration
from integrations.swiggy_client import SwiggyClient, SwiggyError
from integrations.swiggy_tools import SWIGGY_TOOLS
from utils.logger import get_logger

log = get_logger(__name__)

# Hard ceiling on any single order, in rupees. Previously prose in the tool
# descriptions only, which the model was free to ignore.
CART_CAP_RUPEES = 1000

# Total is read from whichever of these the API actually returns. Narrow this
# to the real key once a live cart response has been captured.
_TOTAL_KEYS = ("total", "cartTotal", "grandTotal", "orderTotal", "finalTotal", "totalAmount")


def _cart_total(cart: dict) -> float | None:
    """
    Best-effort read of a cart's total. Returns None when the total cannot be
    determined, which callers must treat as 'unknown', never as zero.
    """
    if not isinstance(cart, dict):
        return None

    for scope in (cart, cart.get("data"), cart.get("cart")):
        if not isinstance(scope, dict):
            continue
        for key in _TOTAL_KEYS:
            value = scope.get(key)
            if isinstance(value, bool):
                continue
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str):
                cleaned = value.replace("₹", "").replace(",", "").strip()
                try:
                    return float(cleaned)
                except ValueError:
                    continue
    return None


class SwiggyIntegration(Integration):
    name = "swiggy"

    def __init__(self, client: SwiggyClient) -> None:
        self._swiggy = client
        self._pending_order: dict | None = None
        self._pending_order_type: str | None = None  # "food" or "grocery"

    def is_available(self) -> bool:
        return self._swiggy is not None and self._swiggy.available

    @classmethod
    def get_tools(cls) -> list[dict]:
        return SWIGGY_TOOLS

    def get_pending_order(self) -> dict | None:
        return self._pending_order

    def get_pending_order_type(self) -> str | None:
        """Either 'food', 'grocery', or None when nothing awaits confirmation."""
        return self._pending_order_type

    def clear_pending_order(self) -> None:
        self._pending_order = None
        self._pending_order_type = None

    def _stage_order(self, cart: dict, order_type: str) -> dict:
        """Cap-check a cart, then stage it for user confirmation."""
        total = _cart_total(cart)

        if total is not None and total > CART_CAP_RUPEES:
            self.clear_pending_order()
            log.warning("swiggy: cart over cap", type=order_type, total=total, cap=CART_CAP_RUPEES)
            return {
                "error": (
                    f"Cart total is ₹{total:.0f}, over the ₹{CART_CAP_RUPEES} limit. "
                    "Remove some items before ordering."
                )
            }

        self._pending_order = cart
        self._pending_order_type = order_type
        staged = {
            "confirmation_required": True,
            "order_summary": cart,
            "payment_method": "Cash on Delivery",
            "message": "Order summary ready. Awaiting user confirmation via button.",
        }
        if total is None:
            # Neither block nor silently allow — the confirmation UI puts a human
            # in front of the summary, so let it through but flag it.
            log.warning("swiggy: cart total unreadable, deferring to human confirmation", type=order_type)
            staged["cart_total_unknown"] = True
        return staged

    def _recheck_cap(self, order_type: str) -> dict | None:
        """Re-read the live cart just before checkout. Error dict if over cap, else None."""
        cart = self._swiggy.get_food_cart() if order_type == "food" else self._swiggy.get_grocery_cart()
        total = _cart_total(cart)
        if total is not None and total > CART_CAP_RUPEES:
            self.clear_pending_order()
            log.warning("swiggy: cart over cap at confirm", type=order_type, total=total)
            return {
                "error": (
                    f"Cart total is ₹{total:.0f}, over the ₹{CART_CAP_RUPEES} limit. "
                    "Order was not placed."
                )
            }
        return None

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
                return self._stage_order(self._swiggy.get_food_cart(), "food")

            elif tool_name == "swiggy_confirm_food_order":
                if not self._pending_order or self._pending_order_type != "food":
                    return {"error": "No pending food order to confirm."}
                over_cap = self._recheck_cap("food")
                if over_cap:
                    return over_cap
                result = self._swiggy.place_food_order()
                self.clear_pending_order()
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
                return self._stage_order(self._swiggy.get_grocery_cart(), "grocery")

            elif tool_name == "swiggy_confirm_grocery_order":
                if not self._pending_order or self._pending_order_type != "grocery":
                    return {"error": "No pending grocery order to confirm."}
                over_cap = self._recheck_cap("grocery")
                if over_cap:
                    return over_cap
                result = self._swiggy.checkout_grocery()
                self.clear_pending_order()
                return {"success": True, "order": result}

            elif tool_name == "swiggy_track_grocery_order":
                status = self._swiggy.track_grocery_order(args["order_id"])
                return {"tracking": status}

            elif tool_name == "swiggy_clear_grocery_cart":
                result = self._swiggy.clear_grocery_cart()
                if self._pending_order_type == "grocery":
                    self.clear_pending_order()
                return {"success": True, "cart": result}

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
