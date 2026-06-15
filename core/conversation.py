"""
Manages the Gemini Chat session and the two-step tool-call / tool-result exchange.
Uses the new google-genai SDK.
"""
from google import genai
from google.genai import types

from integrations.ha_client import HAClient
from services.gemini import GeminiClient
from utils.exceptions import GeminiError
from utils.logger import get_logger

log = get_logger(__name__)

SYSTEM_PROMPT_TEMPLATE = """
You are a helpful home AI assistant. You control smart home devices via Home Assistant.

Available entities:
{entity_list}

Rules:
- If the user asks to control a device, use the provided tools.
- Always confirm what you did in ONE short, friendly spoken sentence (no markdown).
- If you are unsure which entity the user means, ask for clarification.
- For general questions unrelated to home control, answer conversationally.
- Current date/time context will be provided in queries when relevant.
""".strip()


class ConversationManager:
    def __init__(self, gemini: GeminiClient, ha: HAClient) -> None:
        self._gemini = gemini
        self._ha = ha
        self._session: genai.chats.Chat | None = None

    def start(self) -> None:
        """Fetch HA entities and start a Gemini chat session."""
        try:
            entities = self._ha.get_states()
            entity_lines = "\n".join(
                f"- {e['entity_id']} ({e['name']}): {e['state']}"
                for e in entities[:150]
            )
        except Exception as e:
            log.warning("conversation: could not fetch HA entities", error=str(e))
            entity_lines = "(Could not fetch entity list)"

        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(entity_list=entity_lines)
        self._session = self._gemini.start_chat(system_prompt)
        log.info("conversation: session started")

    def send(self, user_text: str) -> str:
        """
        Send a user message, handle any tool calls, and return the final reply text.
        """
        if self._session is None:
            raise GeminiError("ConversationManager.start() has not been called.")

        log.info("conversation: user input", text=user_text)
        try:
            response = self._session.send_message(user_text)
        except Exception as e:
            raise GeminiError(f"Gemini send_message failed: {e}") from e

        # Handle tool call loop
        while True:
            candidate = response.candidates[0]
            part = candidate.content.parts[0]

            if part.function_call is not None:
                fc = part.function_call
                tool_result = self._dispatch_tool(fc.name, dict(fc.args or {}))
                log.info("conversation: tool result", tool=fc.name, result=tool_result)

                try:
                    response = self._session.send_message(
                        types.Part.from_function_response(
                            name=fc.name,
                            response={"result": tool_result},
                        )
                    )
                except Exception as e:
                    raise GeminiError(f"Gemini tool response failed: {e}") from e
            else:
                reply = response.text.strip()
                log.info("conversation: assistant reply", text=reply[:100])
                return reply

    def _dispatch_tool(self, name: str, args: dict) -> dict:
        """Route a Gemini function call to the appropriate HA client method."""
        try:
            if name == "get_ha_entities":
                entities = self._ha.get_states(domain=args.get("domain"))
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

            else:
                return {"error": f"Unknown tool: {name}"}

        except Exception as e:
            log.error("conversation: tool dispatch error", tool=name, error=str(e))
            return {"error": str(e)}
