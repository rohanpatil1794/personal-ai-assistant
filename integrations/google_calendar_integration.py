from integrations.base import Integration
from integrations.google_calendar_client import GoogleCalendarClient, GoogleCalendarError
from integrations.google_calendar_tools import GOOGLE_CALENDAR_TOOLS
from utils.logger import get_logger

log = get_logger(__name__)


class GoogleCalendarIntegration(Integration):
    name = "calendar"

    def __init__(self, client: GoogleCalendarClient | None) -> None:
        self._gcal = client

    def is_available(self) -> bool:
        return self._gcal is not None

    @classmethod
    def get_tools(cls) -> list[dict]:
        return GOOGLE_CALENDAR_TOOLS

    def dispatch(self, tool_name: str, args: dict) -> dict:
        try:
            if tool_name == "calendar_list_events":
                days_ahead = args.get("days_ahead", 7)
                events = self._gcal.list_events(days_ahead=days_ahead)
                return {"events": events}

            elif tool_name == "calendar_create_event":
                event = self._gcal.create_event(
                    summary=args["summary"],
                    start_datetime=args["start_datetime"],
                    end_datetime=args["end_datetime"],
                    description=args.get("description", ""),
                    location=args.get("location", ""),
                )
                return {"success": True, "event": event}

            elif tool_name == "calendar_delete_event":
                self._gcal.delete_event(args["event_id"])
                return {"success": True, "event_id": args["event_id"]}

            elif tool_name == "calendar_check_availability":
                result = self._gcal.check_availability(args["date"])
                return result

            else:
                return {"error": f"Unknown calendar tool: {tool_name}"}

        except GoogleCalendarError as e:
            log.error("calendar_integration: api error", tool=tool_name, error=str(e))
            return {"error": str(e)}
        except Exception as e:
            log.error("calendar_integration: dispatch error", tool=tool_name, error=str(e))
            return {"error": str(e)}
