"""
FamLobster — Family Telegram Calendar Bot

Entry point. Wires together:
  - Telegram bot (python-telegram-bot v21)
  - mcp_server.py (subprocess MCP server for Google Calendar, Gmail, Tasks)
  - FamilyAgent (Claude Haiku + tool-use loop)
  - APScheduler (morning summary + pre-event reminders)

Run:
    python bot.py
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

load_dotenv()

from .agent import PERSONALITY_PRESETS, FamilyAgent  # noqa: E402
from .reminders import load_custom_reminders, setup_scheduler  # noqa: E402

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def parse_allowed_user_ids(raw: str | None) -> set[int]:
    """Parse ALLOWED_USER_IDS (comma-separated Telegram user IDs) into a set."""
    ids: set[int] = set()
    for part in (raw or "").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.add(int(part))
        except ValueError:
            logger.warning("Ignoring invalid entry in ALLOWED_USER_IDS: %r", part)
    return ids


def build_auth_filter(user_ids: set[int]) -> filters.User:
    """Allowlist filter for handlers that act on data. Matches nobody when empty."""
    return filters.User(user_id=user_ids, allow_empty=False)


# ---------------------------------------------------------------------------
# Telegram handlers
# ---------------------------------------------------------------------------


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Hi! I'm FamLobster, your personal assistant.\n\n"
        "Just talk to me naturally — try things like:\n"
        '• "What\'s on the calendar this week?"\n'
        '• "Add soccer practice tomorrow at 4:30pm"\n'
        '• "Move Tuesday\'s dentist to Thursday at 2pm"\n'
        '• "Delete the PTA meeting on Friday"\n\n'
        "Use /reset to clear our conversation history.\n"
        "Use /get_id to see your user ID and this chat's ID (needed for setup).\n"
        "Use /personality to change my tone (try: snarky, pirate, formal, butler)."
    )


async def handle_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    agent: FamilyAgent = context.bot_data["agent"]
    agent.clear_history(update.effective_chat.id)
    await update.message.reply_text("Conversation history cleared!")


async def handle_get_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id if update.effective_user else None
    await update.message.reply_text(
        f"Your user ID is: `{user_id}`\n"
        f"This chat's ID is: `{chat_id}`\n\n"
        "Add your user ID to `ALLOWED_USER_IDS` in your `.env` file to use the bot.\n"
        f"Set `REMINDER_CHAT_ID={chat_id}` to enable "
        "morning summaries and pre-event reminders here.",
        parse_mode=ParseMode.MARKDOWN,
    )


async def handle_unauthorized(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    logger.warning(
        "Ignoring update from unauthorized user %s (add to ALLOWED_USER_IDS to allow)",
        user.id if user else "unknown",
    )


async def handle_personality(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    agent: FamilyAgent = context.bot_data["agent"]
    args = " ".join(context.args) if context.args else ""

    if not args:
        current = agent.personality or "default (friendly assistant)"
        presets = ", ".join(k for k in PERSONALITY_PRESETS if k != "default")
        await update.message.reply_text(
            f"Current personality: {current}\n\n"
            f"Usage: /personality <style>\n"
            f"Presets: {presets}\n"
            f"Or use any freeform description."
        )
        return

    label = agent.set_personality(args)
    await update.message.reply_text(f"Personality set to: {label}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    chat_id = update.effective_chat.id
    user_text = update.message.text
    agent: FamilyAgent = context.bot_data["agent"]

    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

    try:
        reply = await agent.process_message(chat_id, user_text)
    except Exception:
        logger.exception("Agent error for chat %d", chat_id)
        await update.message.reply_text("Sorry, something went wrong. Please try again.")
        return

    await update.message.reply_text(reply, parse_mode=ParseMode.MARKDOWN)

    for action in agent.pop_new_actions(chat_id):
        buttons = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("Confirm", callback_data=f"act:ok:{action.id}"),
                    InlineKeyboardButton("Cancel", callback_data=f"act:no:{action.id}"),
                ]
            ]
        )
        # Plain text: the preview contains untrusted content (recipients, bodies)
        await update.message.reply_text(action.describe(), reply_markup=buttons)


async def handle_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Run or cancel a pending outbound action when an authorized user taps a button."""
    query = update.callback_query
    if query is None or query.message is None:
        return
    if query.from_user.id not in context.bot_data.get("allowed_user_ids", set()):
        logger.warning("Ignoring confirmation from unauthorized user %s", query.from_user.id)
        await query.answer("You're not allowed to do that.")
        return

    _, decision, action_id = (query.data or "").split(":", 2)
    agent: FamilyAgent = context.bot_data["agent"]
    action = agent.take_pending_action(action_id, query.message.chat.id)
    preview = getattr(query.message, "text", None) or ""
    await query.answer()

    if action is None:
        await query.edit_message_text(f"{preview}\n\n⌛ Expired or already handled.")
        return
    if decision != "ok":
        await query.edit_message_text(f"{preview}\n\n✖ Cancelled.")
        return

    try:
        result = await agent.execute_action(action)
    except Exception:
        logger.exception("Confirmed action %s failed", action.tool)
        result = {"error": "unexpected error"}
    if "error" in result:
        await query.edit_message_text(f"{preview}\n\n⚠ Failed: {result['error']}")
    else:
        await query.edit_message_text(f"{preview}\n\n✅ Done.")


# ---------------------------------------------------------------------------
# Startup / shutdown hooks
# ---------------------------------------------------------------------------


async def _run_mcp_subprocess(
    params: StdioServerParameters,
    session_ready: asyncio.Event,
    shutdown_event: asyncio.Event,
    application: Application,
) -> None:
    """Keep the MCP subprocess alive for the bot's lifetime.

    Runs as a background task. stdio_client's anyio cancel scope must
    be entered and exited within the same task, so we hold it open here
    and signal readiness via session_ready.
    """
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            application.bot_data["mcp_session"] = session
            session_ready.set()
            await shutdown_event.wait()


async def post_init(application: Application) -> None:
    """Called by PTB after the event loop starts — wire up all components."""
    logger.info("Starting FamLobster...")

    server_path = Path(__file__).parent / "mcp_server.py"
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(server_path)],
        env=dict(os.environ),
    )

    session_ready = asyncio.Event()
    shutdown_event = asyncio.Event()
    application.bot_data["shutdown_event"] = shutdown_event

    mcp_task = asyncio.create_task(
        _run_mcp_subprocess(params, session_ready, shutdown_event, application)
    )
    application.bot_data["mcp_task"] = mcp_task

    await session_ready.wait()
    mcp_session = application.bot_data["mcp_session"]
    logger.info("MCP calendar server ready")

    # Start the reminder scheduler (built-in jobs only — custom reminders
    # are loaded after the agent is created so they can process through Claude)
    scheduler = setup_scheduler(application.bot, mcp_session)
    application.bot_data["scheduler"] = scheduler

    # Create and configure the agent with scheduler access for reminder tools
    reminder_chat_id = os.getenv("REMINDER_CHAT_ID")
    agent = FamilyAgent(
        mcp_session,
        scheduler=scheduler,
        bot=application.bot,
        reminder_chat_id=int(reminder_chat_id) if reminder_chat_id else None,
    )
    await agent.load_tools()
    application.bot_data["agent"] = agent
    logger.info("FamilyAgent ready with %d tools", len(agent.tools))

    # Load custom reminders now that the agent exists — reminders are
    # processed through the agent so Claude can call tools when they fire
    load_custom_reminders(scheduler, agent)

    logger.info("FamLobster is ready!")


async def post_shutdown(application: Application) -> None:
    """Clean up on shutdown."""
    scheduler = application.bot_data.get("scheduler")
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)

    # Signal the MCP subprocess task to exit cleanly
    shutdown_event = application.bot_data.get("shutdown_event")
    if shutdown_event:
        shutdown_event.set()

    mcp_task = application.bot_data.get("mcp_task")
    if mcp_task and not mcp_task.done():
        try:
            await asyncio.wait_for(mcp_task, timeout=5.0)
        except (TimeoutError, Exception):
            mcp_task.cancel()

    logger.info("FamLobster shut down cleanly")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def register_handlers(application: Application, allowed_user_ids: set[int]) -> None:
    if not allowed_user_ids:
        logger.warning(
            "ALLOWED_USER_IDS is not set — the bot will ignore everyone except /start "
            "and /get_id. Send /get_id to the bot to find your user ID."
        )
    authorized = build_auth_filter(allowed_user_ids)
    application.bot_data["allowed_user_ids"] = allowed_user_ids

    # /start and /get_id stay open so new owners can discover their IDs
    application.add_handler(CommandHandler("start", handle_start))
    application.add_handler(CommandHandler("get_id", handle_get_id))
    application.add_handler(CommandHandler("reset", handle_reset, filters=authorized))
    application.add_handler(CommandHandler("personality", handle_personality, filters=authorized))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND & authorized, handle_message)
    )
    application.add_handler(MessageHandler(~authorized, handle_unauthorized))
    application.add_handler(CallbackQueryHandler(handle_action_callback, pattern=r"^act:(ok|no):"))


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set in .env")

    application = (
        Application.builder().token(token).post_init(post_init).post_shutdown(post_shutdown).build()
    )
    register_handlers(application, parse_allowed_user_ids(os.getenv("ALLOWED_USER_IDS")))

    logger.info("Starting polling...")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
