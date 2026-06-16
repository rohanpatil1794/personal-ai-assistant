GOOGLE_CALENDAR_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "calendar_list_events",
            "description": "List upcoming events from the user's Google Calendar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days_ahead": {
                        "type": "integer",
                        "description": "Number of days ahead to look for events. Default is 7.",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_create_event",
            "description": "Create a new event in the user's Google Calendar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Title of the event.",
                    },
                    "start_datetime": {
                        "type": "string",
                        "description": "Start date and time in ISO 8601 format, e.g. 2026-06-16T15:00:00+05:30",
                    },
                    "end_datetime": {
                        "type": "string",
                        "description": "End date and time in ISO 8601 format, e.g. 2026-06-16T16:00:00+05:30",
                    },
                    "description": {
                        "type": "string",
                        "description": "Optional description or notes for the event.",
                    },
                    "location": {
                        "type": "string",
                        "description": "Optional location of the event.",
                    },
                },
                "required": ["summary", "start_datetime", "end_datetime"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_delete_event",
            "description": "Delete an event from the user's Google Calendar by its event ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {
                        "type": "string",
                        "description": "The Google Calendar event ID to delete.",
                    }
                },
                "required": ["event_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_check_availability",
            "description": "Check if the user is free or busy on a specific date.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "The date to check in YYYY-MM-DD format.",
                    }
                },
                "required": ["date"],
            },
        },
    },
]
