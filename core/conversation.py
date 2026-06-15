"""
Manages the LLM conversation and the tool-call / tool-result exchange.
Uses the Groq SDK (OpenAI-compatible chat completions).
"""
import json

from integrations.ha_client import HAClient
from services.llm import LLMClient
from utils.exceptions import GeminiError as LLMError
from utils.logger import get_logger

log = get_logger(__name__)

SYSTEM_PROMPT_TEMPLATE = """
You are Ronny, a helpful personal AI assistant. You control smart home devices via Home Assistant. When asked your name or who you are, always say you are Ronny, a personal AI assistant.

Available entities:
{entity_list}

Rules:
- If the user asks to control a device, use the provided tools.
- Always confirm what you did in ONE short, friendly spoken sentence (no markdown).
- If you are unsure which entity the user means, ask for clarification.
- For general questions unrelated to home control, answer conversationally.
""".strip()


class ConversationManager:
    def __init__(self, llm: LLMClient, ha: HAClient) -> None:
        self._llm = llm
        self._ha = ha
        self._started = False

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

    def send(self, user_text: str) -> str:
        """Send a user message, handle tool calls, and return the final reply."""
        if not self._started:
            raise LLMError("ConversationManager.start() has not been called.")

        log.info("conversation: user input", text=user_text)
        try:
            response = self._llm.send_message(user_text)
        except Exception as e:
            raise LLMError(f"Gemini send_message failed: {e}") from e

        # Tool-call loop
        while True:
            message = response.choices[0].message

            if message.tool_calls:
                # Process all tool calls in this response
                for tc in message.tool_calls:
                    args = json.loads(tc.function.arguments)
                    tool_result = self._dispatch_tool(tc.function.name, args)
                    log.info("conversation: tool result", tool=tc.function.name, result=tool_result)

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
        """Route a tool call to the appropriate HA client method."""
        try:
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

            else:
                return {"error": f"Unknown tool: {name}"}

        except Exception as e:
            log.error("conversation: tool dispatch error", tool=name, error=str(e))
            return {"error": str(e)}
