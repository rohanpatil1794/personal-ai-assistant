"""
Gemini function declarations for Home Assistant control.
Uses the new google-genai SDK (plain-dict tool schema format).
"""
from google.genai import types

HA_TOOLS = [
    types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name="get_ha_entities",
                description="List Home Assistant entities. Use this to find entity IDs before controlling devices.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "domain": types.Schema(
                            type="STRING",
                            description=(
                                "HA domain to filter by, e.g. 'light', 'switch', 'scene', "
                                "'media_player', 'climate'. Omit to list all entities."
                            ),
                        )
                    },
                ),
            ),
            types.FunctionDeclaration(
                name="control_ha_entity",
                description="Turn on, turn off, or toggle a Home Assistant entity.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "entity_id": types.Schema(
                            type="STRING",
                            description="Full HA entity_id, e.g. 'light.living_room'.",
                        ),
                        "action": types.Schema(
                            type="STRING",
                            description="One of: turn_on, turn_off, toggle.",
                        ),
                        "brightness_pct": types.Schema(
                            type="INTEGER",
                            description="Brightness percentage 0–100 (lights only, optional).",
                        ),
                        "color_name": types.Schema(
                            type="STRING",
                            description="Color name like 'warm white', 'blue' (lights only, optional).",
                        ),
                    },
                    required=["entity_id", "action"],
                ),
            ),
            types.FunctionDeclaration(
                name="activate_ha_scene",
                description="Activate a Home Assistant scene by its entity_id.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "scene_entity_id": types.Schema(
                            type="STRING",
                            description="Scene entity_id, e.g. 'scene.movie_night'.",
                        )
                    },
                    required=["scene_entity_id"],
                ),
            ),
            types.FunctionDeclaration(
                name="call_ha_service",
                description="Call any Home Assistant service directly (escape hatch for advanced commands).",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "domain": types.Schema(type="STRING", description="HA domain, e.g. 'light'."),
                        "service": types.Schema(type="STRING", description="Service name, e.g. 'turn_on'."),
                        "service_data": types.Schema(
                            type="OBJECT",
                            description="Arbitrary service data payload.",
                        ),
                    },
                    required=["domain", "service"],
                ),
            ),
        ]
    )
]
