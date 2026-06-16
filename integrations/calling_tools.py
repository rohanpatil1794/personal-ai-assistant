"""OpenAI-format tool schemas for the calling integration."""

CALLING_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "call_place",
            "description": (
                "Place an outgoing phone call to a contact or phone number. "
                "Deliver a spoken message on the user's behalf and extract the other party's response. "
                "Returns a call_id — use call_get_result later to retrieve what they said."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "contact_name": {
                        "type": "string",
                        "description": "Name of a saved contact (e.g. 'mom', 'dad'). Fuzzy matched.",
                    },
                    "phone_number": {
                        "type": "string",
                        "description": "Direct phone number in E.164 format (e.g. +919876543210). Used if contact_name is not found.",
                    },
                    "message": {
                        "type": "string",
                        "description": "The exact spoken message to deliver to the person on the call. Should be phrased naturally as speech.",
                    },
                    "extract_intent": {
                        "type": "string",
                        "description": "What information to listen for and extract from the other party's response (e.g. 'acknowledgment', 'yes or no', 'time they will arrive', 'any instructions').",
                    },
                },
                "required": ["message", "extract_intent"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "call_get_result",
            "description": (
                "Retrieve the result of a previously placed call. "
                "Returns status (dialing/connected/completed/failed/no-answer/voicemail) "
                "and the extracted response from the other party."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "call_id": {
                        "type": "string",
                        "description": "The call_id returned by call_place.",
                    },
                },
                "required": ["call_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "call_list_contacts",
            "description": "List all saved contacts (names and phone numbers).",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "call_add_contact",
            "description": "Save a new contact with a name and phone number.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Contact name (e.g. 'mom', 'doctor', 'Raj').",
                    },
                    "phone_number": {
                        "type": "string",
                        "description": "Phone number in E.164 format (e.g. +919876543210).",
                    },
                },
                "required": ["name", "phone_number"],
            },
        },
    },
]
