import json
from pathlib import Path

from famlobster.reminders import (
    _format_time,
    _read_reminders_file,
    _write_reminders_file,
    add_reminder,
    get_all_reminders,
    remove_reminder,
    update_reminder,
)


# -------------------------------------------------------------------
# _format_time
# -------------------------------------------------------------------


def test_format_time_with_datetime():
    assert _format_time("2026-03-24T14:30:00-05:00") == "2:30 PM"


def test_format_time_all_day():
    assert _format_time("2026-03-24") == "2026-03-24"


def test_format_time_empty():
    assert _format_time("") == "unknown time"


def test_format_time_invalid():
    assert _format_time("not-a-date") == "not-a-date"


# -------------------------------------------------------------------
# JSON persistence
# -------------------------------------------------------------------


def test_read_reminders_file_missing(tmp_reminders_file):
    assert _read_reminders_file() == []


def test_read_reminders_file_corrupt(tmp_reminders_file):
    Path(tmp_reminders_file).write_text("{bad json")
    assert _read_reminders_file() == []


def test_write_then_read_roundtrip(tmp_reminders_file):
    data = [{"id": "r1", "message": "test", "schedule": {"type": "cron", "hour": 8, "minute": 0}}]
    _write_reminders_file(data)
    assert _read_reminders_file() == data


# -------------------------------------------------------------------
# add_reminder
# -------------------------------------------------------------------


def test_add_reminder_cron(mock_scheduler, mock_bot, tmp_reminders_file):
    result = add_reminder(
        scheduler=mock_scheduler,
        bot=mock_bot,
        message="Take out trash",
        hour=18,
        minute=0,
        chat_id=-100123,
    )
    assert result["id"].startswith("reminder_")
    assert result["message"] == "Take out trash"
    assert result["schedule"]["type"] == "cron"
    assert result["schedule"]["hour"] == 18
    assert result["schedule"]["minute"] == 0

    # Verify persisted to file
    saved = json.loads(Path(tmp_reminders_file).read_text())
    assert len(saved) == 1
    assert saved[0]["message"] == "Take out trash"

    # Verify scheduler was called
    mock_scheduler.add_job.assert_called_once()


def test_add_reminder_with_day_of_week(mock_scheduler, mock_bot, tmp_reminders_file):
    result = add_reminder(
        scheduler=mock_scheduler,
        bot=mock_bot,
        message="Prep lunches",
        hour=17,
        minute=0,
        chat_id=-100123,
        day_of_week="sun",
    )
    assert result["schedule"]["day_of_week"] == "sun"


# -------------------------------------------------------------------
# remove_reminder
# -------------------------------------------------------------------


def test_remove_reminder_success(mock_scheduler, mock_bot, tmp_reminders_file):
    added = add_reminder(
        scheduler=mock_scheduler, bot=mock_bot,
        message="Test", hour=9, minute=0, chat_id=-100,
    )
    result = remove_reminder(mock_scheduler, added["id"])
    assert result["status"] == "removed"

    saved = json.loads(Path(tmp_reminders_file).read_text())
    assert len(saved) == 0


def test_remove_reminder_builtin_rejected(mock_scheduler):
    result = remove_reminder(mock_scheduler, "morning_summary")
    assert "error" in result
    assert "Cannot remove" in result["error"]


def test_remove_reminder_not_found(mock_scheduler, tmp_reminders_file):
    result = remove_reminder(mock_scheduler, "nonexistent_id")
    assert "error" in result


# -------------------------------------------------------------------
# update_reminder
# -------------------------------------------------------------------


def test_update_reminder_custom(mock_scheduler, mock_bot, tmp_reminders_file):
    added = add_reminder(
        scheduler=mock_scheduler, bot=mock_bot,
        message="Old message", hour=9, minute=0, chat_id=-100,
    )
    mock_scheduler.reset_mock()

    result = update_reminder(
        scheduler=mock_scheduler, bot=mock_bot,
        reminder_id=added["id"],
        message="New message",
        hour=10,
    )
    assert result["status"] == "updated"

    saved = json.loads(Path(tmp_reminders_file).read_text())
    assert saved[0]["message"] == "New message"
    assert saved[0]["schedule"]["hour"] == 10


def test_update_reminder_not_found(mock_scheduler, mock_bot, tmp_reminders_file):
    result = update_reminder(
        scheduler=mock_scheduler, bot=mock_bot,
        reminder_id="nonexistent",
    )
    assert "error" in result


# -------------------------------------------------------------------
# get_all_reminders
# -------------------------------------------------------------------


def test_get_all_reminders_empty(mock_scheduler):
    result = get_all_reminders(mock_scheduler)
    assert result == []
