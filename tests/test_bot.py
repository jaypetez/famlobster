from datetime import datetime
from unittest.mock import MagicMock

import pytest
from telegram import Chat, Message, MessageEntity, Update, User
from telegram.ext import Application

from famlobster.bot import (
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
