import os
from datetime import datetime, timedelta, timezone

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from utils.logger import get_logger

log = get_logger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar"]


class GoogleCalendarError(Exception):
    pass


class GoogleCalendarClient:
    def __init__(self, token_path: str = "token.json", credentials_path: str = "credentials.json") -> None:
        self._token_path = token_path
        self._credentials_path = credentials_path
        self._service = None

        if os.path.exists(token_path):
            self._service = self._build_service()
            log.info("google_calendar: client initialised")
        else:
            log.warning("google_calendar: token.json not found — calendar disabled. Run integrations/google_auth.py to authorize.")

    @property
    def available(self) -> bool:
        return self._service is not None

    def _build_service(self):
        creds = Credentials.from_authorized_user_file(self._token_path, SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(self._token_path, "w") as f:
                f.write(creds.to_json())
        return build("calendar", "v3", credentials=creds)

    def _ensure_available(self):
        if not self.available:
            raise GoogleCalendarError("Google Calendar is not authorized. Run integrations/google_auth.py first.")

    def list_events(self, days_ahead: int = 7) -> list[dict]:
        self._ensure_available()
        now = datetime.now(timezone.utc)
        end = now + timedelta(days=days_ahead)
        try:
            result = self._service.events().list(
                calendarId="primary",
                timeMin=now.isoformat(),
                timeMax=end.isoformat(),
                maxResults=20,
                singleEvents=True,
                orderBy="startTime",
            ).execute()
            events = result.get("items", [])
            return [
                {
                    "id": e["id"],
                    "summary": e.get("summary", "(No title)"),
                    "start": e["start"].get("dateTime", e["start"].get("date")),
                    "end": e["end"].get("dateTime", e["end"].get("date")),
                    "location": e.get("location", ""),
                    "description": e.get("description", ""),
                }
                for e in events
            ]
        except HttpError as e:
            raise GoogleCalendarError(f"Failed to list events: {e}") from e

    def create_event(
        self,
        summary: str,
        start_datetime: str,
        end_datetime: str,
        description: str = "",
        location: str = "",
    ) -> dict:
        self._ensure_available()
        event = {
            "summary": summary,
            "start": {"dateTime": start_datetime, "timeZone": "Asia/Kolkata"},
            "end": {"dateTime": end_datetime, "timeZone": "Asia/Kolkata"},
        }
        if description:
            event["description"] = description
        if location:
            event["location"] = location
        try:
            created = self._service.events().insert(calendarId="primary", body=event).execute()
            return {"id": created["id"], "summary": created.get("summary"), "link": created.get("htmlLink")}
        except HttpError as e:
            raise GoogleCalendarError(f"Failed to create event: {e}") from e

    def delete_event(self, event_id: str) -> bool:
        self._ensure_available()
        try:
            self._service.events().delete(calendarId="primary", eventId=event_id).execute()
            return True
        except HttpError as e:
            raise GoogleCalendarError(f"Failed to delete event: {e}") from e

    def check_availability(self, date: str) -> dict:
        """Returns busy periods and free slots for a given date (YYYY-MM-DD)."""
        self._ensure_available()
        day_start = datetime.fromisoformat(f"{date}T00:00:00").astimezone(timezone.utc)
        day_end = datetime.fromisoformat(f"{date}T23:59:59").astimezone(timezone.utc)
        try:
            body = {
                "timeMin": day_start.isoformat(),
                "timeMax": day_end.isoformat(),
                "items": [{"id": "primary"}],
            }
            result = self._service.freebusy().query(body=body).execute()
            busy = result["calendars"]["primary"]["busy"]
            return {"date": date, "busy_periods": busy, "is_free_all_day": len(busy) == 0}
        except HttpError as e:
            raise GoogleCalendarError(f"Failed to check availability: {e}") from e
