"""
FamLobster — Family Telegram Calendar Bot

Entry point. Wires together:
  - Telegram bot (python-telegram-bot v21)
  - CalendarServer (in-process MCP server over Google Calendar)
  - FamilyAgent (Claude Haiku + tool-use loop)
  - APScheduler (morning summary + pre-event reminders)

Run:
    python bot.py
"""

import asyncio
import logging
import os

from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

load_dotenv()

from agent import FamilyAgent
from calendar_server import CalendarServer
from reminders import setup_scheduler

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Telegram handlers
# ---------------------------------------------------------------------------


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Hi! I'm FamLobster, your family calendar assistant.\n\n"
        "Just talk to me naturally — try things like:\n"
        '• "What\'s on the calendar this week?"\n'
        '• "Add Jude\'s baseball game tomorrow at 4:30pm"\n'
        '• "Move Tuesday\'s dentist to Thursday at 2pm"\n'
        '• "Delete the PTA meeting on Friday"\n\n'
        "Use /reset to clear our conversation history.\n"
        "Use /get_id to see this chat's ID (useful for setting up reminders)."
    )


async def handle_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    agent: FamilyAgent = context.bot_data["agent"]
    agent.clear_history(update.effective_chat.id)
    await update.message.reply_text("Conversation history cleared!")


async def handle_get_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    await update.message.reply_text(
        f"This chat's ID is: `{chat_id}`\n\n"
        "Set `REMINDER_CHAT_ID={chat_id}` in your `.env` file to enable "
        "morning summaries and pre-event reminders here.",
        parse_mode=ParseMode.MARKDOWN,
    )


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
        await update.message.reply_text(
            "Sorry, something went wrong. Please try again."
        )
        return

    await update.message.reply_text(reply, parse_mode=ParseMode.MARKDOWN)


# ---------------------------------------------------------------------------
# Startup / shutdown hooks
# ---------------------------------------------------------------------------


async def post_init(application: Application) -> None:
    """Called by PTB after the event loop starts — wire up all components."""
    logger.info("Starting FamLobster...")

    # Build Google Calendar service (runs sync OAuth flow if needed)
    calendar_server = CalendarServer()
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, calendar_server.build_google_service)
    logger.info("Google Calendar service ready")

    # Start in-process MCP server
    mcp_session, server_task = await calendar_server.run_in_process()
    application.bot_data["server_task"] = server_task
    logger.info("MCP server running in-process")

    # Create and configure the agent
    agent = FamilyAgent(mcp_session)
    await agent.load_tools()
    application.bot_data["agent"] = agent
    logger.info("FamilyAgent ready with %d tools", len(agent.tools))

    # Start the reminder scheduler
    scheduler = setup_scheduler(application.bot, mcp_session)
    application.bot_data["scheduler"] = scheduler

    logger.info("FamLobster is ready!")


async def post_shutdown(application: Application) -> None:
    """Clean up background tasks on shutdown."""
    scheduler = application.bot_data.get("scheduler")
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)

    server_task = application.bot_data.get("server_task")
    if server_task and not server_task.done():
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass

    logger.info("FamLobster shut down cleanly")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set in .env")

    application = (
        Application.builder()
        .token(token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    application.add_handler(CommandHandler("start", handle_start))
    application.add_handler(CommandHandler("reset", handle_reset))
    application.add_handler(CommandHandler("get_id", handle_get_id))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    logger.info("Starting polling...")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
