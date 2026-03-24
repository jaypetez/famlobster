from unittest.mock import MagicMock, patch

from famlobster.mcp_server import MCPServer


@patch("famlobster.mcp_server.Server")
def _make_server(mock_server_cls):
    """Create an MCPServer without starting a real MCP server."""
    server = MCPServer()
    return server


# -------------------------------------------------------------------
# _event_to_dict
# -------------------------------------------------------------------


def test_event_to_dict_full():
    server = _make_server()
    event = {
        "id": "abc123",
        "summary": "Team meeting",
        "start": {"dateTime": "2026-03-25T10:00:00-05:00"},
        "end": {"dateTime": "2026-03-25T11:00:00-05:00"},
        "description": "Weekly sync",
        "location": "Room 4B",
    }
    result = server._event_to_dict(event)
    assert result["id"] == "abc123"
    assert result["summary"] == "Team meeting"
    assert result["start"] == "2026-03-25T10:00:00-05:00"
    assert result["end"] == "2026-03-25T11:00:00-05:00"
    assert result["description"] == "Weekly sync"
    assert result["location"] == "Room 4B"


def test_event_to_dict_all_day():
    server = _make_server()
    event = {
        "id": "day1",
        "summary": "Holiday",
        "start": {"date": "2026-12-25"},
        "end": {"date": "2026-12-26"},
    }
    result = server._event_to_dict(event)
    assert result["start"] == "2026-12-25"
    assert result["end"] == "2026-12-26"


def test_event_to_dict_missing_fields():
    server = _make_server()
    event = {"id": "x"}
    result = server._event_to_dict(event)
    assert result["summary"] == "(no title)"
    assert result["description"] == ""
    assert result["location"] == ""
    assert result["start"] is None
    assert result["end"] is None


# -------------------------------------------------------------------
# _dispatch
# -------------------------------------------------------------------


def test_dispatch_unknown_tool():
    server = _make_server()
    result = server._dispatch("nonexistent_tool", {})
    assert result == {"error": "Unknown tool: nonexistent_tool"}


def test_dispatch_all_tools_registered():
    server = _make_server()
    expected_tools = [
        "list_events", "create_event", "update_event", "delete_event",
        "send_email",
        "list_tasks", "add_tasks", "complete_task", "delete_task", "clear_completed",
    ]
    for tool_name in expected_tools:
        # Mock the actual handler to avoid calling Google APIs
        handler = MagicMock(return_value={"ok": True})
        setattr(server, f"_{tool_name}", handler)

    # Patch the dispatch table to use our mocked handlers
    for tool_name in expected_tools:
        result = server._dispatch(tool_name, {"test": True})
        # Should not return "Unknown tool" error
        assert result != {"error": f"Unknown tool: {tool_name}"}, f"{tool_name} not registered"
