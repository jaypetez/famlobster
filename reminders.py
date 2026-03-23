"""
Proactive reminder jobs using APScheduler.

Two jobs:
  1. morning_summary  — sends today's events each morning at MORNING_REMINDER_TIME
  2. pre_event_check  — checks every 5 min for events about to start

Reminders call the MCP server directly (no Claude) for reliability and cost.
"""

import json
import logging
import os
from datetime import date, datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from mcp import ClientSession
from telegram import Bot

logger = logging.getLogger(__name__)


def setup_scheduler(bot: Bot, mcp_session: ClientSession) -> AsyncIOScheduler:
    """Create, configure, and start the scheduler. Returns the running scheduler."""
    tz = os.getenv("TIMEZONE", "America/Chicago")
    reminder_chat_id = os.getenv("REMINDER_CHAT_ID")
    morning_time = os.getenv("MORNING_REMINDER_TIME", "07:30")
    pre_event_minutes = int(os.getenv("PRE_EVENT_REMINDER_MINUTES", "30"))

    scheduler = AsyncIOScheduler(timezone=tz)

    if reminder_chat_id:
        hour, minute = morning_time.split(":")
        scheduler.add_job(
            send_morning_summary,
            CronTrigger(hour=int(hour), minute=int(minute), timezone=tz),
            args=[bot, mcp_session, reminder_chat_id],
            id="morning_summary",
            name="Morning calendar summary",
            misfire_grace_time=300,
        )
        logger.info("Morning summary scheduled at %s %s", morning_time, tz)

        if pre_event_minutes > 0:
            scheduler.add_job(
                send_pre_event_reminders,
                IntervalTrigger(minutes=5),
                args=[bot, mcp_session, reminder_chat_id, pre_event_minutes],
                id="pre_event_check",
                name="Pre-event reminder check",
            )
            logger.info("Pre-event check every 5 min (%d min warning)", pre_event_minutes)
    else:
        logger.warning(
            "REMINDER_CHAT_ID not set — morning summary and pre-event reminders disabled. "
            "Send /get_id in your family group chat to find the chat ID."
        )

    scheduler.start()
    return scheduler


async def send_morning_summary(
    bot: Bot, mcp_session: ClientSession, chat_id: str
) -> None:
    """Fetch today's events and send a morning briefing."""
    today = date.today().isoformat()
    try:
        result = await mcp_session.call_tool(
            "list_events", {"start_date": today, "end_date": today}
        )
        events = json.loads(result.content[0].text) if result.content else []
    except Exception:
        logger.exception("Failed to fetch events for morning summary")
        return

    if not events:
        text = f"Good morning! No events on the calendar for today ({today})."
    else:
        lines = [f"Good morning! Here's what's on the calendar today ({today}):\n"]
        for e in events:
            start = _format_time(e.get("start", ""))
            lines.append(f"• {e['summary']} — {start}")
        text = "\n".join(lines)

    try:
        await bot.send_message(chat_id=int(chat_id), text=text)
    except Exception:
        logger.exception("Failed to send morning summary to chat %s", chat_id)


# In-memory set to avoid sending duplicate pre-event reminders
_reminded_event_ids: set[str] = set()


async def send_pre_event_reminders(
    bot: Bot, mcp_session: ClientSession, chat_id: str, minutes_before: int
) -> None:
    """Check for events starting within `minutes_before` minutes and notify once."""
    now = datetime.now(tz=timezone.utc)
    window_end = now + timedelta(minutes=minutes_before + 5)

    today = now.date().isoformat()
    try:
        result = await mcp_session.call_tool(
            "list_events",
            {"start_date": today, "end_date": today, "max_results": 50},
        )
        events = json.loads(result.content[0].text) if result.content else []
    except Exception:
        logger.exception("Failed to fetch events for pre-event check")
        return

    for event in events:
        event_id = event.get("id")
        if not event_id or event_id in _reminded_event_ids:
            continue

        start_str = event.get("start", "")
        if not start_str or "T" not in start_str:
            continue  # skip all-day events

        try:
            start_dt = datetime.fromisoformat(start_str)
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue

        if now <= start_dt <= window_end:
            mins_away = int((start_dt - now).total_seconds() / 60)
            text = f"Reminder: *{event['summary']}* starts in {mins_away} minutes!"
            try:
                await bot.send_message(
                    chat_id=int(chat_id), text=text, parse_mode="Markdown"
                )
                _reminded_event_ids.add(event_id)
                logger.info("Sent pre-event reminder for event %s", event_id)
            except Exception:
                logger.exception("Failed to send pre-event reminder")

    # Prune event IDs for events that have already passed to keep the set small
    _reminded_event_ids.difference_update(
        eid
        for eid in list(_reminded_event_ids)
        if eid not in {e.get("id") for e in events}
    )


def _format_time(iso_str: str) -> str:
    """Format an ISO datetime string to a human-readable time."""
    if not iso_str:
        return "unknown time"
    if "T" not in iso_str:
        return iso_str  # all-day event, return date as-is
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%-I:%M %p")
    except ValueError:
        return iso_str
