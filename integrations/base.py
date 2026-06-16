from abc import ABC, abstractmethod


class Integration(ABC):
    """
    Base class for all feature integrations (HA, Swiggy, Google Calendar, etc.).
    To add a new feature: subclass this, implement get_tools() and dispatch(),
    then register an instance via IntegrationRegistry in server.py.
    """

    name: str  # unique identifier, set as a class attribute in each subclass

    @classmethod
    @abstractmethod
    def get_tools(cls) -> list[dict]:
        """Return the list of OpenAI-format tool schemas this integration provides."""
        ...

    @abstractmethod
    def dispatch(self, tool_name: str, args: dict) -> dict:
        """Execute the named tool with the given args and return a result dict."""
        ...

    def is_available(self) -> bool:
        """Return False to silently skip registration (e.g. missing credentials)."""
        return True
