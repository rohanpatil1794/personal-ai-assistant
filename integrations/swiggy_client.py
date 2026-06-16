"""
Swiggy REST API client (Food, Instamart, Dineout).
All methods are synchronous to match ha_client.py patterns.
Requires an OAuth 2.1 access token obtained out-of-band.
"""
import httpx
from utils.logger import get_logger

log = get_logger(__name__)

BASE_URL = "https://api.swiggy.com"


class SwiggyError(Exception):
    pass


class SwiggyClient:
    def __init__(self, access_token: str) -> None:
        self._headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

    def _get(self, path: str, params: dict | None = None) -> dict | list:
        try:
            resp = httpx.get(f"{BASE_URL}{path}", headers=self._headers, params=params, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise SwiggyError("Swiggy session expired. Please reconnect.") from e
            raise SwiggyError(f"Swiggy GET {path} failed ({e.response.status_code}): {e.response.text}") from e
        except Exception as e:
            raise SwiggyError(f"Swiggy GET {path} error: {e}") from e

    def _post(self, path: str, payload: dict) -> dict:
        try:
            resp = httpx.post(f"{BASE_URL}{path}", headers=self._headers, json=payload, timeout=15)
            resp.raise_for_status()
            return resp.json() if resp.content else {}
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise SwiggyError("Swiggy session expired. Please reconnect.") from e
            raise SwiggyError(f"Swiggy POST {path} failed ({e.response.status_code}): {e.response.text}") from e
        except Exception as e:
            raise SwiggyError(f"Swiggy POST {path} error: {e}") from e

    # --- Address management ---

    def get_addresses(self) -> list[dict]:
        log.info("swiggy: get_addresses")
        data = self._get("/mcp/addresses")
        return data if isinstance(data, list) else data.get("addresses", [])

    def create_address(self, details: dict) -> dict:
        log.info("swiggy: create_address")
        return self._post("/mcp/addresses", details)

    # --- Food delivery ---

    def search_restaurants(self, address_id: str, query: str) -> list[dict]:
        log.info("swiggy: search_restaurants", query=query)
        data = self._get("/mcp/food/restaurants/search", params={"addressId": address_id, "query": query})
        return data if isinstance(data, list) else data.get("restaurants", [])

    def get_menu(self, restaurant_id: str) -> dict:
        log.info("swiggy: get_menu", restaurant_id=restaurant_id)
        return self._get(f"/mcp/food/restaurants/{restaurant_id}/menu")

    def update_food_cart(self, restaurant_id: str, items: list[dict]) -> dict:
        log.info("swiggy: update_food_cart", restaurant_id=restaurant_id, item_count=len(items))
        return self._post("/mcp/food/cart", {"restaurantId": restaurant_id, "items": items})

    def get_food_cart(self) -> dict:
        log.info("swiggy: get_food_cart")
        return self._get("/mcp/food/cart")

    def fetch_coupons(self) -> list[dict]:
        log.info("swiggy: fetch_coupons")
        data = self._get("/mcp/food/coupons")
        return data if isinstance(data, list) else data.get("coupons", [])

    def apply_coupon(self, coupon_code: str, address_id: str) -> dict:
        log.info("swiggy: apply_coupon", code=coupon_code)
        return self._post("/mcp/food/cart/coupon", {"couponCode": coupon_code, "addressId": address_id})

    def place_food_order(self) -> dict:
        log.info("swiggy: place_food_order")
        return self._post("/mcp/food/orders", {"paymentMethod": "COD"})

    def track_food_order(self, order_id: str) -> dict:
        log.info("swiggy: track_food_order", order_id=order_id)
        return self._get(f"/mcp/food/orders/{order_id}/track")

    def get_food_orders(self) -> list[dict]:
        data = self._get("/mcp/food/orders")
        return data if isinstance(data, list) else data.get("orders", [])

    # --- Grocery (Instamart) ---

    def search_products(self, address_id: str, query: str) -> list[dict]:
        log.info("swiggy: search_products", query=query)
        data = self._get("/mcp/instamart/products/search", params={"addressId": address_id, "query": query})
        return data if isinstance(data, list) else data.get("products", [])

    def get_go_to_items(self, address_id: str) -> list[dict]:
        log.info("swiggy: get_go_to_items")
        data = self._get("/mcp/instamart/go-to-items", params={"addressId": address_id})
        return data if isinstance(data, list) else data.get("items", [])

    def update_grocery_cart(self, items: list[dict]) -> dict:
        log.info("swiggy: update_grocery_cart", item_count=len(items))
        return self._post("/mcp/instamart/cart", {"items": items})

    def get_grocery_cart(self) -> dict:
        log.info("swiggy: get_grocery_cart")
        return self._get("/mcp/instamart/cart")

    def clear_grocery_cart(self) -> dict:
        log.info("swiggy: clear_grocery_cart")
        return self._post("/mcp/instamart/cart/clear", {})

    def checkout_grocery(self) -> dict:
        log.info("swiggy: checkout_grocery")
        return self._post("/mcp/instamart/orders", {"paymentMethod": "COD"})

    def track_grocery_order(self, order_id: str) -> dict:
        log.info("swiggy: track_grocery_order", order_id=order_id)
        return self._get(f"/mcp/instamart/orders/{order_id}/track")

    # --- Dineout ---

    def search_dineout(self, query: str, lat: float, lng: float) -> list[dict]:
        log.info("swiggy: search_dineout", query=query)
        data = self._get("/mcp/dineout/restaurants/search", params={"query": query, "latitude": lat, "longitude": lng})
        return data if isinstance(data, list) else data.get("restaurants", [])

    def get_dineout_details(self, restaurant_id: str, lat: float, lng: float) -> dict:
        log.info("swiggy: get_dineout_details", restaurant_id=restaurant_id)
        return self._get(f"/mcp/dineout/restaurants/{restaurant_id}", params={"latitude": lat, "longitude": lng})

    def get_slots(self, restaurant_id: str, date: str, lat: float, lng: float) -> dict:
        log.info("swiggy: get_slots", restaurant_id=restaurant_id, date=date)
        return self._get(
            f"/mcp/dineout/restaurants/{restaurant_id}/slots",
            params={"date": date, "latitude": lat, "longitude": lng},
        )

    def book_table(
        self,
        restaurant_id: str,
        slot_id: str,
        item_id: str,
        reservation_time: str,
        guest_count: int,
        lat: float,
        lng: float,
    ) -> dict:
        log.info("swiggy: book_table", restaurant_id=restaurant_id, time=reservation_time, guests=guest_count)
        return self._post("/mcp/dineout/bookings", {
            "restaurantId": restaurant_id,
            "slotId": slot_id,
            "itemId": item_id,
            "reservationTime": reservation_time,
            "guestCount": guest_count,
            "latitude": lat,
            "longitude": lng,
        })

    def get_booking_status(self, order_id: str) -> dict:
        log.info("swiggy: get_booking_status", order_id=order_id)
        return self._get(f"/mcp/dineout/bookings/{order_id}")
