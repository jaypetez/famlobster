"""
MCP server wrapping the Google Calendar API.

Exposes four tools to Claude:
  - list_events
  - create_event
  - update_event
  - delete_event

Runs in-process using anyio memory streams so no subprocess is needed.
"""

import asyncio
import json
import os
from datetime import datetime, timezone

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from mcp.server import Server
import mcp.types as types

SCOPES = ["https://www.googleapis.com/auth/calendar"]


class CalendarServer:
    def __init__(self):
        self.service = None
        self.calendar_id = os.getenv("GOOGLE_CALENDAR_ID", "primary")
        self.server = Server("famlobster-calendar")
        self._register_tools()

    # ------------------------------------------------------------------
    # Google Auth
    # ------------------------------------------------------------------

    def build_google_service(self) -> None:
        """Load OAuth2 token and build the Calendar service.

        token.json must already exist — generate it on your laptop by
        running auth.py, then SCP it to ~/.config/famlobster/token.json.
        The token auto-refreshes when expired.
        """
        token_file = os.getenv("GOOGLE_TOKEN_FILE", "token.json")
        creds_file = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")

        if not os.path.exists(token_file):
            raise FileNotFoundError(
                f"token.json not found at {token_file}.\n"
                "Run auth.py on your laptop to generate it, then SCP it to this server.\n"
                "See README.md for instructions."
            )

        creds = Credentials.from_authorized_user_file(token_file, SCOPES)

        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(token_file, "w") as f:
                f.write(creds.to_json())

        self.service = build("calendar", "v3", credentials=creds)

    # ------------------------------------------------------------------
    # Tool helpers
    # ------------------------------------------------------------------

    def _event_to_dict(self, event: dict) -> dict:
        start = event.get("start", {})
        end = event.get("end", {})
        return {
            "id": event.get("id"),
            "summary": event.get("summary", "(no title)"),
            "start": start.get("dateTime") or start.get("date"),
            "end": end.get("dateTime") or end.get("date"),
            "description": event.get("description", ""),
            "location": event.get("location", ""),
        }

    # ------------------------------------------------------------------
    # Tool registration
    # ------------------------------------------------------------------

    def _register_tools(self) -> None:
        @self.server.list_tools()
        async def handle_list_tools() -> list[types.Tool]:
            return [
                types.Tool(
                    name="list_events",
                    description="List upcoming calendar events in a date range.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "start_date": {
                                "type": "string",
                                "description": "Start date in ISO format (YYYY-MM-DD)",
                            },
                            "end_date": {
                                "type": "string",
                                "description": "End date in ISO format (YYYY-MM-DD)",
                            },
                            "max_results": {
                                "type": "integer",
                                "description": "Maximum number of events to return (default 20)",
                                "default": 20,
                            },
                        },
                        "required": ["start_date", "end_date"],
                    },
                ),
                types.Tool(
                    name="create_event",
                    description="Create a new calendar event.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "summary": {
                                "type": "string",
                                "description": "Event title",
                            },
                            "start_datetime": {
                                "type": "string",
                                "description": "Start date/time in ISO 8601 format with timezone (e.g. 2026-03-25T14:00:00-06:00). For all-day events use YYYY-MM-DD.",
                            },
                            "end_datetime": {
                                "type": "string",
                                "description": "End date/time in ISO 8601 format with timezone. For all-day events use YYYY-MM-DD.",
                            },
                            "description": {
                                "type": "string",
                                "description": "Event description (optional)",
                            },
                            "location": {
                                "type": "string",
                                "description": "Event location (optional)",
                            },
                            "attendees": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of attendee email addresses (optional)",
                            },
                        },
                        "required": ["summary", "start_datetime", "end_datetime"],
                    },
                ),
                types.Tool(
                    name="update_event",
                    description="Update an existing calendar event. Provide the event_id and only the fields you want to change.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "event_id": {
                                "type": "string",
                                "description": "The Google Calendar event ID",
                            },
                            "summary": {"type": "string"},
                            "start_datetime": {"type": "string"},
                            "end_datetime": {"type": "string"},
                            "description": {"type": "string"},
                            "location": {"type": "string"},
                        },
                        "required": ["event_id"],
                    },
                ),
                types.Tool(
                    name="delete_event",
                    description="Delete a calendar event by its ID.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "event_id": {
                                "type": "string",
                                "description": "The Google Calendar event ID to delete",
                            }
                        },
                        "required": ["event_id"],
                    },
                ),
            ]

        @self.server.call_tool()
        async def handle_call_tool(
            name: str, arguments: dict | None
        ) -> list[types.TextContent]:
            args = arguments or {}
            try:
                result = await asyncio.get_event_loop().run_in_executor(
                    None, self._dispatch, name, args
                )
                return [types.TextContent(type="text", text=json.dumps(result))]
            except HttpError as e:
                error = {"error": str(e.reason), "code": e.resp.status}
                return [types.TextContent(type="text", text=json.dumps(error))]
            except Exception as e:
                error = {"error": str(e)}
                return [types.TextContent(type="text", text=json.dumps(error))]

    def _dispatch(self, name: str, args: dict) -> dict | list:
        """Synchronous dispatch to the appropriate Google Calendar API call."""
        if name == "list_events":
            return self._list_events(args)
        elif name == "create_event":
            return self._create_event(args)
        elif name == "update_event":
            return self._update_event(args)
        elif name == "delete_event":
            return self._delete_event(args)
        else:
            return {"error": f"Unknown tool: {name}"}

    # ------------------------------------------------------------------
    # Google Calendar operations (synchronous, run in executor)
    # ------------------------------------------------------------------

    def _list_events(self, args: dict) -> list:
        start_date = args["start_date"]
        end_date = args["end_date"]
        max_results = args.get("max_results", 20)

        # Convert date strings to RFC3339 timestamps
        time_min = f"{start_date}T00:00:00Z"
        time_max = f"{end_date}T23:59:59Z"

        result = (
            self.service.events()
            .list(
                calendarId=self.calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        return [self._event_to_dict(e) for e in result.get("items", [])]

    def _create_event(self, args: dict) -> dict:
        start = args["start_datetime"]
        end = args["end_datetime"]

        # Detect all-day events (no time component)
        if "T" in start:
            start_obj = {"dateTime": start}
            end_obj = {"dateTime": end}
        else:
            start_obj = {"date": start}
            end_obj = {"date": end}

        body: dict = {
            "summary": args["summary"],
            "start": start_obj,
            "end": end_obj,
        }
        if "description" in args:
            body["description"] = args["description"]
        if "location" in args:
            body["location"] = args["location"]
        if "attendees" in args:
            body["attendees"] = [{"email": e} for e in args["attendees"]]

        event = (
            self.service.events()
            .insert(calendarId=self.calendar_id, body=body)
            .execute()
        )
        return {
            "id": event["id"],
            "summary": event.get("summary"),
            "htmlLink": event.get("htmlLink"),
        }

    def _update_event(self, args: dict) -> dict:
        event_id = args["event_id"]
        event = (
            self.service.events()
            .get(calendarId=self.calendar_id, eventId=event_id)
            .execute()
        )

        if "summary" in args:
            event["summary"] = args["summary"]
        if "description" in args:
            event["description"] = args["description"]
        if "location" in args:
            event["location"] = args["location"]
        if "start_datetime" in args:
            start = args["start_datetime"]
            event["start"] = (
                {"dateTime": start} if "T" in start else {"date": start}
            )
        if "end_datetime" in args:
            end = args["end_datetime"]
            event["end"] = {"dateTime": end} if "T" in end else {"date": end}

        updated = (
            self.service.events()
            .update(calendarId=self.calendar_id, eventId=event_id, body=event)
            .execute()
        )
        return self._event_to_dict(updated)

    def _delete_event(self, args: dict) -> dict:
        event_id = args["event_id"]
        self.service.events().delete(
            calendarId=self.calendar_id, eventId=event_id
        ).execute()
        return {"status": "deleted", "event_id": event_id}

if __name__ == "__main__":
    import asyncio
    from mcp.server.stdio import stdio_server

    async def _serve() -> None:
        cal = CalendarServer()
        cal.build_google_service()
        async with stdio_server() as (read_stream, write_stream):
            await cal.server.run(
                read_stream,
                write_stream,
                cal.server.create_initialization_options(),
            )

    asyncio.run(_serve())
