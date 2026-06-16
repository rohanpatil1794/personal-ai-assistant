from integrations.base import Integration
from utils.logger import get_logger

log = get_logger(__name__)


class IntegrationRegistry:
    """
    Central registry for all feature integrations.
    Collects tool schemas and routes tool calls to the correct integration.
    """

    def __init__(self) -> None:
        self._integrations: list[Integration] = []
        self._tool_map: dict[str, Integration] = {}

    def register(self, integration: Integration) -> None:
        if not integration.is_available():
            log.info("registry: skipping unavailable integration", name=integration.name)
            return
        self._integrations.append(integration)
        for tool in integration.get_tools():
            tool_name = tool["function"]["name"]
            self._tool_map[tool_name] = integration
        log.info("registry: registered integration", name=integration.name,
                 tools=len(integration.get_tools()))

    def get_all_tools(self) -> list[dict]:
        tools = []
        for integration in self._integrations:
            tools.extend(integration.get_tools())
        return tools

    def dispatch(self, tool_name: str, args: dict) -> dict:
        integration = self._tool_map.get(tool_name)
        if integration is None:
            return {"error": f"Unknown tool: {tool_name}"}
        return integration.dispatch(tool_name, args)

    def get_integration(self, name: str) -> Integration | None:
        return next((i for i in self._integrations if i.name == name), None)
