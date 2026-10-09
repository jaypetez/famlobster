from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import Chat, Message, MessageEntity, Update, User
from telegram.ext import Application

from famlobster.bot import (
    handle_action_callback,
    handle_get_id,
    handle_message,
    handle_personality,
    handle_reset,
    handle_start,
    handle_unauthorized,
    parse_allowed_user_ids,
    register_handlers,
)

OWNER_ID = 1001
STRANGER_ID = 2002


def _update(user_id: int, text: str) -> Update:
    entities = []
    if text.startswith("/"):
        entities = [MessageEntity(MessageEntity.BOT_COMMAND, 0, len(text.split()[0]))]
    message = Message(
        message_id=1,
        date=datetime.now(),
        chat=Chat(id=user_id, type=Chat.PRIVATE),
        from_user=User(id=user_id, first_name="Test", is_bot=False),
        text=text,
        entities=entities,
    )
    return Update(update_id=1, message=message)


def _dispatched_callback(app: Application, update: Update):
    """Return the callback PTB would run for this update (first matching handler)."""
    # CommandHandler reads the bot username; avoid a network call to getMe
    update.message.set_bot(MagicMock(username="famlobster_bot"))
    for handler in app.handlers[0]:
        if handler.check_update(update):
            return handler.callback
    return None


@pytest.fixture
def make_app():
    def _make(allowed: set[int]) -> Application:
        app = Application.builder().token("123:TEST").build()
        register_handlers(app, allowed)
        return app

    return _make


def test_parse_allowed_user_ids():
    assert parse_allowed_user_ids("1001, 2002,,") == {1001, 2002}
    assert parse_allowed_user_ids("1001,not-a-number") == {1001}
    assert parse_allowed_user_ids("") == set()
    assert parse_allowed_user_ids(None) == set()


def test_authorized_user_reaches_agent(make_app):
    app = make_app({OWNER_ID})
    assert _dispatched_callback(app, _update(OWNER_ID, "what's on today?")) is handle_message
    assert _dispatched_callback(app, _update(OWNER_ID, "/reset")) is handle_reset
    assert _dispatched_callback(app, _update(OWNER_ID, "/personality pirate")) is (
        handle_personality
    )


@pytest.mark.parametrize("text", ["what's on today?", "/reset", "/personality pirate"])
def test_unauthorized_user_is_ignored(make_app, text):
    app = make_app({OWNER_ID})
    assert _dispatched_callback(app, _update(STRANGER_ID, text)) is handle_unauthorized


@pytest.mark.parametrize("text", ["what's on today?", "/reset", "/personality pirate"])
def test_empty_allowlist_fails_closed(make_app, text):
    app = make_app(set())
    assert _dispatched_callback(app, _update(OWNER_ID, text)) is handle_unauthorized


def test_setup_commands_stay_open(make_app):
    app = make_app(set())
    assert _dispatched_callback(app, _update(STRANGER_ID, "/start")) is handle_start
    assert _dispatched_callback(app, _update(STRANGER_ID, "/get_id")) is handle_get_id


# -------------------------------------------------------------------
# Confirmation callbacks
# -------------------------------------------------------------------


def _callback_update(user_id: int, data: str, chat_id: int = OWNER_ID):
    query = MagicMock()
    query.from_user.id = user_id
    query.data = data
    query.message.chat.id = chat_id
    query.message.text = "Send this email?"
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    return SimpleNamespace(callback_query=query), query


def _context(agent):
    return SimpleNamespace(bot_data={"agent": agent, "allowed_user_ids": {OWNER_ID}})


async def test_callback_confirm_executes_action():
    agent = MagicMock()
    agent.take_pending_action.return_value = "action"
    agent.execute_action = AsyncMock(return_value={"status": "sent"})
    update, query = _callback_update(OWNER_ID, "act:ok:abc")

    await handle_action_callback(update, _context(agent))

    agent.take_pending_action.assert_called_once_with("abc", OWNER_ID)
    agent.execute_action.assert_awaited_once_with("action")
    assert "Done" in query.edit_message_text.call_args.args[0]


async def test_callback_cancel_does_not_execute():
    agent = MagicMock()
    agent.take_pending_action.return_value = "action"
    agent.execute_action = AsyncMock()
    update, query = _callback_update(OWNER_ID, "act:no:abc")

    await handle_action_callback(update, _context(agent))

    agent.execute_action.assert_not_called()
    assert "Cancelled" in query.edit_message_text.call_args.args[0]


async def test_callback_from_unauthorized_user_is_rejected():
    agent = MagicMock()
    agent.execute_action = AsyncMock()
    update, query = _callback_update(STRANGER_ID, "act:ok:abc")

    await handle_action_callback(update, _context(agent))

    agent.take_pending_action.assert_not_called()
    agent.execute_action.assert_not_called()


async def test_callback_expired_action():
    agent = MagicMock()
    agent.take_pending_action.return_value = None
    agent.execute_action = AsyncMock()
    update, query = _callback_update(OWNER_ID, "act:ok:abc")

    await handle_action_callback(update, _context(agent))

    agent.execute_action.assert_not_called()
    assert "Expired" in query.edit_message_text.call_args.args[0]


def test_callback_handler_registered(make_app):
    from telegram.ext import CallbackQueryHandler

    app = make_app({OWNER_ID})
    assert any(
        isinstance(h, CallbackQueryHandler) and h.callback is handle_action_callback
        for h in app.handlers[0]
    )


def test_httpx_request_logging_suppressed():
    """httpx INFO logs include the bot token in Telegram API URLs."""
    import logging

    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING


def test_mcp_server_env_withholds_unrelated_secrets(monkeypatch):
    from famlobster.bot import mcp_server_env

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:secret")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret")
    monkeypatch.setenv("GOOGLE_TOKEN_FILE", "/srv/token.json")
    monkeypatch.setenv("GOOGLE_CALENDAR_ID", "family")
    monkeypatch.setenv("TIMEZONE", "America/Denver")

    env = mcp_server_env()

    assert "TELEGRAM_BOT_TOKEN" not in env
    assert "ANTHROPIC_API_KEY" not in env
    assert env["GOOGLE_TOKEN_FILE"] == "/srv/token.json"
    assert env["GOOGLE_CALENDAR_ID"] == "family"
    assert env["TIMEZONE"] == "America/Denver"


async def test_reply_falls_back_to_plain_text_on_bad_markdown():
    from telegram.error import BadRequest

    agent = MagicMock()
    agent.process_message = AsyncMock(return_value="unbalanced *markdown")
    agent.pop_new_actions.return_value = []
    message = MagicMock(text="hi")
    message.reply_text = AsyncMock(side_effect=[BadRequest("Can't parse entities"), None])
    update = SimpleNamespace(message=message, effective_chat=SimpleNamespace(id=OWNER_ID))
    context = SimpleNamespace(
        bot_data={"agent": agent}, bot=MagicMock(send_chat_action=AsyncMock())
    )

    await handle_message(update, context)

    assert message.reply_text.await_count == 2
    assert message.reply_text.call_args.args == ("unbalanced *markdown",)
    assert "parse_mode" not in message.reply_text.call_args.kwargs
