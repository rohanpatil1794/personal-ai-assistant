"""
Tool declarations for Swiggy Food, Instamart, and Dineout.
Uses OpenAI-compatible JSON schema format (works with Groq).
"""

SWIGGY_TOOLS = [
    # --- Shared ---
    {
        "type": "function",
        "function": {
            "name": "swiggy_get_addresses",
            "description": (
                "Fetch the user's saved Swiggy delivery addresses. "
                "Always call this first before any food or grocery order. "
                "After getting the list, ask the user: 'Would you like to deliver to [address labels] or provide a new address?'"
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },

    # --- Food delivery ---
    {
        "type": "function",
        "function": {
            "name": "swiggy_search_food",
            "description": "Search for food delivery restaurants by cuisine or name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "address_id": {"type": "string", "description": "The address ID to deliver to."},
                    "query": {"type": "string", "description": "Restaurant name or cuisine type, e.g. 'biryani' or 'McDonald's'."},
                },
                "required": ["address_id", "query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "swiggy_get_menu",
            "description": "Get the full menu for a specific restaurant.",
            "parameters": {
                "type": "object",
                "properties": {
                    "restaurant_id": {"type": "string", "description": "Restaurant ID from swiggy_search_food results."},
                },
                "required": ["restaurant_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "swiggy_update_food_cart",
            "description": "Add or update items in the food delivery cart.",
            "parameters": {
                "type": "object",
                "properties": {
                    "restaurant_id": {"type": "string", "description": "Restaurant ID."},
                    "items": {
                        "type": "array",
                        "description": "List of items to add.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "itemId": {"type": "string"},
                                "quantity": {"type": "integer"},
                                "name": {"type": "string"},
                                "price": {"type": "number"},
                            },
                            "required": ["itemId", "quantity"],
                        },
                    },
                },
                "required": ["restaurant_id", "items"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "swiggy_get_food_cart",
            "description": "Get current food cart contents and total price.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "swiggy_place_food_order",
            "description": (
                "Show the user an order summary and request confirmation before placing the order. "
                "This does NOT place the order yet — it returns a preview that the user must confirm. "
                "Call swiggy_get_food_cart first to get the latest totals."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "swiggy_confirm_food_order",
            "description": (
                "Place the food order after the user has physically confirmed via the confirmation button. "
                "Only call this after the user explicitly confirms. Payment is Cash on Delivery."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "swiggy_track_food_order",
            "description": "Track the delivery status of a food order.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "Order ID from swiggy_confirm_food_order."},
                },
                "required": ["order_id"],
            },
        },
    },

    # --- Grocery (Instamart) ---
    {
        "type": "function",
        "function": {
            "name": "swiggy_search_grocery",
            "description": "Search for grocery or quick-commerce products on Swiggy Instamart.",
            "parameters": {
                "type": "object",
                "properties": {
                    "address_id": {"type": "string", "description": "Delivery address ID."},
                    "query": {"type": "string", "description": "Product name, e.g. 'milk', 'bread', 'eggs'."},
                },
                "required": ["address_id", "query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "swiggy_update_grocery_cart",
            "description": "Add or update items in the Instamart grocery cart.",
            "parameters": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "description": "List of grocery items to add.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "spinId": {"type": "string", "description": "Product variant ID from search results."},
                                "quantity": {"type": "integer"},
                                "name": {"type": "string"},
                                "price": {"type": "number"},
                            },
                            "required": ["spinId", "quantity"],
                        },
                    },
                },
                "required": ["items"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "swiggy_get_grocery_cart",
            "description": "Get current Instamart grocery cart contents and total.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "swiggy_place_grocery_order",
            "description": (
                "Show the user a grocery order summary and request confirmation. "
                "Does NOT place the order — returns a preview. "
                "Call swiggy_get_grocery_cart first."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "swiggy_confirm_grocery_order",
            "description": (
                "Place the grocery order after the user confirms via the confirmation button. "
                "Payment is Cash on Delivery. Cart cap is ₹1,000."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },

    # --- Dineout ---
    {
        "type": "function",
        "function": {
            "name": "swiggy_search_dineout",
            "description": "Search for restaurants available for table booking via Swiggy Dineout.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Cuisine or restaurant name, e.g. 'Italian', 'rooftop'."},
                    "latitude": {"type": "number", "description": "User's latitude. Get from saved address if available."},
                    "longitude": {"type": "number", "description": "User's longitude."},
                },
                "required": ["query", "latitude", "longitude"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "swiggy_get_dineout_slots",
            "description": "Get available table booking slots for a restaurant on a given date.",
            "parameters": {
                "type": "object",
                "properties": {
                    "restaurant_id": {"type": "string", "description": "Restaurant ID from swiggy_search_dineout."},
                    "date": {"type": "string", "description": "Date in YYYY-MM-DD format."},
                    "latitude": {"type": "number"},
                    "longitude": {"type": "number"},
                },
                "required": ["restaurant_id", "date", "latitude", "longitude"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "swiggy_book_table",
            "description": (
                "Book a table at a restaurant. Only FREE reservations are supported in v1 — "
                "do not attempt paid deals."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "restaurant_id": {"type": "string"},
                    "slot_id": {"type": "string", "description": "Slot ID from swiggy_get_dineout_slots."},
                    "item_id": {"type": "string", "description": "Item/deal ID from slot data."},
                    "reservation_time": {"type": "string", "description": "ISO datetime string for the reservation."},
                    "guest_count": {"type": "integer", "description": "Number of guests."},
                    "latitude": {"type": "number"},
                    "longitude": {"type": "number"},
                },
                "required": ["restaurant_id", "slot_id", "item_id", "reservation_time", "guest_count", "latitude", "longitude"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "swiggy_get_booking_status",
            "description": "Check the status of a dine-out table reservation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "Booking order ID from swiggy_book_table."},
                },
                "required": ["order_id"],
            },
        },
    },
]
