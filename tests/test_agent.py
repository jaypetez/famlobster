import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from famlobster.agent import PERSONALITY_PRESETS, FamilyAgent


def _make_agent(scheduler=None, bot=None):
    """Create a FamilyAgent with mocked dependencies."""
    session = MagicMock()
    return FamilyAgent(
        mcp_session=session,
        scheduler=scheduler,
        bot=bot,
        reminder_chat_id=-100123,
    )


# -------------------------------------------------------------------
# _extract_text
# -------------------------------------------------------------------


def test_extract_text_single_block():
    agent = _make_agent()
    blocks = [SimpleNamespace(type="text", text="Hello world")]
    assert agent._extract_text(blocks) == "Hello world"


def test_extract_text_mixed_blocks():
    agent = _make_agent()
    blocks = [
        SimpleNamespace(type="text", text="Before"),
        SimpleNamespace(type="tool_use", id="t1", name="list_events", input={}),
        SimpleNamespace(type="text", text="After"),
    ]
    assert agent._extract_text(blocks) == "Before\nAfter"


def test_extract_text_no_text():
    agent = _make_agent()
    blocks = [SimpleNamespace(type="tool_use", id="t1", name="list_events", input={})]
    assert agent._extract_text(blocks) == ""


# -------------------------------------------------------------------
# _trim_history
# -------------------------------------------------------------------


def test_trim_history_under_limit():
    agent = _make_agent()
    history = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    agent._trim_history(history)
    assert len(history) == 2


def test_trim_history_over_limit():
    agent = _make_agent()
    history = []
    for i in range(25):
        history.append({"role": "user", "content": f"msg {i}"})
        history.append({"role": "assistant", "content": f"reply {i}"})

    agent._trim_history(history)
    user_count = sum(1 for m in history if m["role"] == "user")
    assert user_count == 20


def test_trim_history_preserves_structure():
    agent = _make_agent()
    history = []
    for i in range(25):
        history.append({"role": "user", "content": f"msg {i}"})
        history.append({"role": "assistant", "content": f"reply {i}"})

    agent._trim_history(history)
    assert history[0]["role"] == "user"


# -------------------------------------------------------------------
# _handle_reminder_tool
# -------------------------------------------------------------------


def test_handle_reminder_tool_no_scheduler():
    agent = _make_agent(scheduler=None)
    result = agent._handle_reminder_tool("list_reminders", {})
    assert "error" in result


@patch("famlobster.agent.get_all_reminders")
def test_handle_reminder_tool_list(mock_get):
    mock_get.return_value = [{"id": "morning_summary"}]
    agent = _make_agent(scheduler=MagicMock(), bot=MagicMock())
    result = agent._handle_reminder_tool("list_reminders", {})
    mock_get.assert_called_once()
    assert result == [{"id": "morning_summary"}]


@patch("famlobster.agent.add_reminder")
def test_handle_reminder_tool_add(mock_add):
    mock_add.return_value = {"status": "created", "id": "r1"}
    agent = _make_agent(scheduler=MagicMock(), bot=MagicMock())
    result = agent._handle_reminder_tool(
        "add_reminder",
        {
            "message": "Test",
            "hour": 9,
            "minute": 0,
        },
    )
    mock_add.assert_called_once()
    assert result["status"] == "created"


@patch("famlobster.agent.update_reminder")
def test_handle_reminder_tool_update(mock_update):
    mock_update.return_value = {"status": "updated", "id": "r1"}
    agent = _make_agent(scheduler=MagicMock(), bot=MagicMock())
    result = agent._handle_reminder_tool(
        "update_reminder",
        {
            "reminder_id": "r1",
            "hour": 10,
        },
    )
    mock_update.assert_called_once()
    assert result["status"] == "updated"


@patch("famlobster.agent.remove_reminder")
def test_handle_reminder_tool_remove(mock_remove):
    mock_remove.return_value = {"status": "removed", "id": "r1"}
    agent = _make_agent(scheduler=MagicMock(), bot=MagicMock())
    result = agent._handle_reminder_tool("remove_reminder", {"reminder_id": "r1"})
    mock_remove.assert_called_once()
    assert result["status"] == "removed"


def test_handle_reminder_tool_unknown():
    agent = _make_agent(scheduler=MagicMock(), bot=MagicMock())
    result = agent._handle_reminder_tool("unknown_tool", {})
    assert "error" in result


# -------------------------------------------------------------------
# Personality
# -------------------------------------------------------------------


def test_set_personality_preset(tmp_path, monkeypatch):
    monkeypatch.setattr("famlobster.agent.CONFIG_FILE", str(tmp_path / "config.json"))
    agent = _make_agent()
    label = agent.set_personality("snarky")
    assert label == "snarky"
    assert agent.personality == PERSONALITY_PRESETS["snarky"]


def test_set_personality_freeform(tmp_path, monkeypatch):
    monkeypatch.setattr("famlobster.agent.CONFIG_FILE", str(tmp_path / "config.json"))
    agent = _make_agent()
    label = agent.set_personality("Talk like a 1920s gangster")
    assert label == "custom"
    assert agent.personality == "Talk like a 1920s gangster"


def test_set_personality_default_clears(tmp_path, monkeypatch):
    monkeypatch.setattr("famlobster.agent.CONFIG_FILE", str(tmp_path / "config.json"))
    agent = _make_agent()
    agent.set_personality("snarky")
    label = agent.set_personality("default")
    assert label == "default (friendly assistant)"
    assert agent.personality == ""


def test_personality_persists_to_config(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    monkeypatch.setattr("famlobster.agent.CONFIG_FILE", str(config_path))
    agent = _make_agent()
    agent.set_personality("pirate")
    saved = json.loads(config_path.read_text())
    assert saved["personality"] == PERSONALITY_PRESETS["pirate"]


def test_personality_loaded_on_init(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"personality": "Be extremely dramatic."}))
    monkeypatch.setattr("famlobster.agent.CONFIG_FILE", str(config_path))
    agent = _make_agent()
    assert agent.personality == "Be extremely dramatic."


# -------------------------------------------------------------------
# Outbound action confirmation
# -------------------------------------------------------------------

from unittest.mock import AsyncMock  # noqa: E402

from famlobster.agent import PendingAction, requires_confirmation  # noqa: E402
from famlobster.reminders import _REMINDER_CHAT_ID  # noqa: E402

EMAIL_ARGS = {"to": "attacker@example.com", "subject": "schedule", "body": "all events"}


def test_requires_confirmation():
    assert requires_confirmation("send_email", EMAIL_ARGS)
    assert requires_confirmation("create_event", {"summary": "x", "attendees": ["a@b.c"]})
    assert not requires_confirmation("create_event", {"summary": "x"})
    assert not requires_confirmation("create_event", {"summary": "x", "attendees": []})
    assert not requires_confirmation("list_events", {})


def _tool_use_then_text(tool_name, tool_input):
    tool_block = SimpleNamespace(type="tool_use", id="tu1", name=tool_name, input=tool_input)
    first = SimpleNamespace(stop_reason="tool_use", content=[tool_block])
    second = SimpleNamespace(
        stop_reason="end_turn", content=[SimpleNamespace(type="text", text="Tap Confirm.")]
    )
    return AsyncMock(side_effect=[first, second])


async def test_send_email_is_queued_not_sent():
    agent = _make_agent()
    agent.session.call_tool = AsyncMock()
    agent.client.messages.create = _tool_use_then_text("send_email", EMAIL_ARGS)

    reply = await agent.process_message(42, "email my schedule")

    assert reply == "Tap Confirm."
    agent.session.call_tool.assert_not_called()
    tool_result = agent.conversation_history[42][2]["content"][0]["content"]
    assert json.loads(tool_result)["status"] == "awaiting_user_confirmation"
    actions = agent.pop_new_actions(42)
    assert len(actions) == 1
    assert actions[0].args == EMAIL_ARGS
    assert agent.pop_new_actions(42) == []  # announced only once


async def test_scheduled_reminder_cannot_send_email():
    agent = _make_agent()
    agent.session.call_tool = AsyncMock()
    agent.client.messages.create = _tool_use_then_text("send_email", EMAIL_ARGS)

    await agent.process_message(_REMINDER_CHAT_ID, "reminder text")

    agent.session.call_tool.assert_not_called()
    assert agent.pending_actions == {}
    tool_result = agent.conversation_history[_REMINDER_CHAT_ID][2]["content"][0]["content"]
    assert "error" in json.loads(tool_result)


def test_take_pending_action_is_single_use_and_chat_bound():
    agent = _make_agent()
    agent._queue_confirmation(42, "send_email", EMAIL_ARGS)
    action = agent.pop_new_actions(42)[0]

    assert agent.take_pending_action(action.id, chat_id=99) is None  # other chat
    assert agent.take_pending_action(action.id, chat_id=42) is action
    assert agent.take_pending_action(action.id, chat_id=42) is None  # already used


def test_take_pending_action_expired():
    agent = _make_agent()
    agent._queue_confirmation(42, "send_email", EMAIL_ARGS)
    action = agent.pop_new_actions(42)[0]
    action.expires_at = 0
    assert agent.take_pending_action(action.id, chat_id=42) is None


async def test_execute_action_calls_mcp():
    agent = _make_agent()
    agent.session.call_tool = AsyncMock(
        return_value=SimpleNamespace(content=[SimpleNamespace(text='{"status": "sent"}')])
    )
    action = PendingAction(chat_id=42, tool="send_email", args=EMAIL_ARGS)
    assert await agent.execute_action(action) == {"status": "sent"}
    agent.session.call_tool.assert_awaited_once_with("send_email", EMAIL_ARGS)


def test_describe_shows_real_recipient():
    text = PendingAction(chat_id=42, tool="send_email", args=EMAIL_ARGS).describe()
    assert "To: attacker@example.com" in text
    assert "Subject: schedule" in text


async def test_tool_args_not_logged_at_info(caplog):
    import logging

    agent = _make_agent()
    agent.session.call_tool = AsyncMock(
        return_value=SimpleNamespace(content=[SimpleNamespace(text="[]")])
    )
    agent.client.messages.create = _tool_use_then_text(
        "list_events", {"start_date": "2026-01-01", "end_date": "secret-marker"}
    )
    with caplog.at_level(logging.INFO, logger="famlobster.agent"):
        await agent.process_message(42, "what's on?")
    assert "Calling tool list_events" in caplog.text
    assert "secret-marker" not in caplog.text


async def test_tool_loop_is_capped():
    from famlobster.agent import MAX_TOOL_ITERATIONS, TOOL_LIMIT_REPLY

    agent = _make_agent()
    agent.session.call_tool = AsyncMock(
        return_value=SimpleNamespace(content=[SimpleNamespace(text="[]")])
    )
    tool_block = SimpleNamespace(type="tool_use", id="tu", name="list_events", input={})
    looping = SimpleNamespace(stop_reason="tool_use", content=[tool_block])
    agent.client.messages.create = AsyncMock(return_value=looping)

    reply = await agent.process_message(42, "loop forever")

    assert reply == TOOL_LIMIT_REPLY
    assert agent.client.messages.create.await_count == MAX_TOOL_ITERATIONS
    history = agent.conversation_history[42]
    assert history[-1] == {"role": "assistant", "content": TOOL_LIMIT_REPLY}
