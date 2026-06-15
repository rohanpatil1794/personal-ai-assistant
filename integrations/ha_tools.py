"""
Tool declarations for Home Assistant control.
Uses OpenAI-compatible JSON schema format (works with Groq).
"""

HA_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_ha_entities",
            "description": "List Home Assistant entities. Use this to find entity IDs before controlling devices.",
            "parameters": {
                "type": "object",
                "properties": {
                    "domain": {
                        "type": "string",
                        "description": (
                            "HA domain to filter by, e.g. 'light', 'switch', 'scene', "
                            "'media_player', 'climate'. Omit to list all entities."
                        ),
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "control_ha_entity",
            "description": "Turn on, turn off, or toggle a Home Assistant entity.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_id": {
                        "type": "string",
                        "description": "Full HA entity_id, e.g. 'light.living_room'.",
                    },
                    "action": {
                        "type": "string",
                        "enum": ["turn_on", "turn_off", "toggle"],
                        "description": "Action to perform.",
                    },
                    "brightness_pct": {
                        "type": "integer",
                        "description": "Brightness percentage 0–100 (lights only, optional).",
                    },
                    "color_name": {
                        "type": "string",
                        "description": "Color name like 'warm white', 'blue' (lights only, optional).",
                    },
                },
                "required": ["entity_id", "action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "activate_ha_scene",
            "description": "Activate a Home Assistant scene by its entity_id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "scene_entity_id": {
                        "type": "string",
                        "description": "Scene entity_id, e.g. 'scene.movie_night'.",
                    }
                },
                "required": ["scene_entity_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "call_ha_service",
            "description": "Call any Home Assistant service directly (escape hatch for advanced commands).",
            "parameters": {
                "type": "object",
                "properties": {
                    "domain": {"type": "string", "description": "HA domain, e.g. 'light'."},
                    "service": {"type": "string", "description": "Service name, e.g. 'turn_on'."},
                    "service_data": {
                        "type": "object",
                        "description": "Arbitrary service data payload.",
                    },
                },
                "required": ["domain", "service"],
            },
        },
    },
]
