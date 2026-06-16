from integrations.base import Integration
from integrations.ha_client import HAClient
from integrations.ha_tools import HA_TOOLS
from utils.logger import get_logger

log = get_logger(__name__)


class HAIntegration(Integration):
    name = "ha"

    def __init__(self, client: HAClient) -> None:
        self._ha = client

    @classmethod
    def get_tools(cls) -> list[dict]:
        return HA_TOOLS

    def dispatch(self, tool_name: str, args: dict) -> dict:
        try:
            if tool_name == "get_ha_entities":
                domain = args.get("domain") or None
                entities = self._ha.get_states(domain=domain)
                return {"entities": entities}

            elif tool_name == "control_ha_entity":
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

            elif tool_name == "activate_ha_scene":
                self._ha.activate_scene(args["scene_entity_id"])
                return {"success": True, "scene": args["scene_entity_id"]}

            elif tool_name == "call_ha_service":
                result = self._ha.call_service(
                    args["domain"],
                    args["service"],
                    args.get("service_data", {}),
                )
                return {"success": True, "result": result}

            else:
                return {"error": f"Unknown HA tool: {tool_name}"}

        except Exception as e:
            log.error("ha_integration: dispatch error", tool=tool_name, error=str(e))
            return {"error": str(e)}
