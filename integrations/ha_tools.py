"""
Gemini function declarations for Home Assistant control.
"""
import google.generativeai as genai

HA_TOOLS = [
    genai.protos.Tool(
        function_declarations=[
            genai.protos.FunctionDeclaration(
                name="get_ha_entities",
                description="List Home Assistant entities. Use this to find entity IDs before controlling devices.",
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={
                        "domain": genai.protos.Schema(
                            type=genai.protos.Type.STRING,
                            description=(
                                "HA domain to filter by, e.g. 'light', 'switch', 'scene', "
                                "'media_player', 'climate'. Omit to list all entities."
                            ),
                        )
                    },
                ),
            ),
            genai.protos.FunctionDeclaration(
                name="control_ha_entity",
                description="Turn on, turn off, or toggle a Home Assistant entity.",
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={
                        "entity_id": genai.protos.Schema(
                            type=genai.protos.Type.STRING,
                            description="Full HA entity_id, e.g. 'light.living_room'.",
                        ),
                        "action": genai.protos.Schema(
                            type=genai.protos.Type.STRING,
                            description="One of: turn_on, turn_off, toggle.",
                        ),
                        "brightness_pct": genai.protos.Schema(
                            type=genai.protos.Type.INTEGER,
                            description="Brightness percentage 0–100 (lights only, optional).",
                        ),
                        "color_name": genai.protos.Schema(
                            type=genai.protos.Type.STRING,
                            description="Color name like 'warm white', 'blue' (lights only, optional).",
                        ),
                    },
                    required=["entity_id", "action"],
                ),
            ),
            genai.protos.FunctionDeclaration(
                name="activate_ha_scene",
                description="Activate a Home Assistant scene by its entity_id.",
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={
                        "scene_entity_id": genai.protos.Schema(
                            type=genai.protos.Type.STRING,
                            description="Scene entity_id, e.g. 'scene.movie_night'.",
                        )
                    },
                    required=["scene_entity_id"],
                ),
            ),
            genai.protos.FunctionDeclaration(
                name="call_ha_service",
                description="Call any Home Assistant service directly (escape hatch for advanced commands).",
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={
                        "domain": genai.protos.Schema(type=genai.protos.Type.STRING, description="HA domain, e.g. 'light'."),
                        "service": genai.protos.Schema(type=genai.protos.Type.STRING, description="Service name, e.g. 'turn_on'."),
                        "service_data": genai.protos.Schema(
                            type=genai.protos.Type.OBJECT,
                            description="Arbitrary service data payload.",
                        ),
                    },
                    required=["domain", "service"],
                ),
            ),
        ]
    )
]
