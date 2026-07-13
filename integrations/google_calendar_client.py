import os
from datetime import datetime, timedelta, timezone

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from utils.logger import get_logger

log = get_logger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar"]
IST = timezone(timedelta(hours=5, minutes=30))


class GoogleCalendarError(Exception):
    pass


class GoogleCalendarClient:
    def __init__(self, token_path: str = "token.json", credentials_path: str = "credentials.json") -> None:
        self._token_path = token_path
        self._credentials_path = credentials_path
        self._service = None
        self._calendar_ids: list[str] | None = None  # cached list of all calendar IDs

        if os.path.exists(token_path):
            try:
                self._service = self._build_service()
                log.info("google_calendar: client initialised")
            except Exception as e:
                log.warning("google_calendar: failed to initialise — calendar disabled. Re-run integrations/google_auth.py to reauthorize. Error: %s", e)
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

    def _get_calendar_ids(self) -> list[str]:
        """Return all writable calendar IDs for this account (cached)."""
        if self._calendar_ids is not None:
            return self._calendar_ids
        try:
            result = self._service.calendarList().list().execute()
            calendars = result.get("items", [])
            # Include all calendars the user can write to (own + shared editable)
            ids = [c["id"] for c in calendars if c.get("accessRole") in ("owner", "writer")]
            if not ids:
                ids = ["primary"]
            self._calendar_ids = ids
            log.info("google_calendar: discovered calendars", count=len(ids), ids=ids)
        except HttpError:
            self._calendar_ids = ["primary"]
        return self._calendar_ids

    def list_events(self, days_ahead: int = 7) -> list[dict]:
        self._ensure_available()
        # Start from midnight IST today so events earlier today are included
        today_midnight = datetime.now(IST).replace(hour=0, minute=0, second=0, microsecond=0)
        end = today_midnight + timedelta(days=days_ahead)
        time_min = today_midnight.isoformat()
        time_max = end.isoformat()

        all_events: list[dict] = []
        for cal_id in self._get_calendar_ids():
            try:
                result = self._service.events().list(
                    calendarId=cal_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    maxResults=50,
                    singleEvents=True,
                    orderBy="startTime",
                ).execute()
                for e in result.get("items", []):
                    all_events.append({
                        "id": e["id"],
                        "calendar_id": cal_id,
                        "summary": e.get("summary", "(No title)"),
                        "start": e["start"].get("dateTime", e["start"].get("date")),
                        "end": e["end"].get("dateTime", e["end"].get("date")),
                        "location": e.get("location", ""),
                        "description": e.get("description", ""),
                    })
            except HttpError as e:
                log.warning("google_calendar: failed to list events for calendar", cal_id=cal_id, error=str(e))

        # Sort all results by start time
        all_events.sort(key=lambda e: e["start"])
        log.info("google_calendar: list_events", total=len(all_events), calendars=len(self._get_calendar_ids()))
        return all_events

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

    def delete_event(self, event_id: str, calendar_id: str | None = None) -> bool:
        self._ensure_available()
        # If caller knows which calendar, use it directly
        candidates = [calendar_id] if calendar_id else self._get_calendar_ids()
        for cal_id in candidates:
            try:
                self._service.events().delete(calendarId=cal_id, eventId=event_id).execute()
                return True
            except HttpError as e:
                if e.resp.status == 404:
                    continue  # not on this calendar, try next
                raise GoogleCalendarError(f"Failed to delete event: {e}") from e
        raise GoogleCalendarError(f"Event {event_id} not found on any calendar.")

    def check_availability(self, date: str) -> dict:
        """Returns busy periods and free slots for a given date (YYYY-MM-DD)."""
        self._ensure_available()
        day_start = datetime.fromisoformat(f"{date}T00:00:00").replace(tzinfo=IST)
        day_end = datetime.fromisoformat(f"{date}T23:59:59").replace(tzinfo=IST)
        try:
            body = {
                "timeMin": day_start.isoformat(),
                "timeMax": day_end.isoformat(),
                "items": [{"id": cal_id} for cal_id in self._get_calendar_ids()],
            }
            result = self._service.freebusy().query(body=body).execute()
            # Merge busy periods across all calendars
            all_busy = []
            for cal_data in result.get("calendars", {}).values():
                all_busy.extend(cal_data.get("busy", []))
            all_busy.sort(key=lambda b: b["start"])
            return {"date": date, "busy_periods": all_busy, "is_free_all_day": len(all_busy) == 0}
        except HttpError as e:
            raise GoogleCalendarError(f"Failed to check availability: {e}") from e
