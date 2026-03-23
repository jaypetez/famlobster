# FamLobster

A family Telegram bot that manages your Google Calendar using natural language, powered by Claude Haiku and the Model Context Protocol (MCP).

**Example messages:**
- "What's on the calendar this week?"
- "Add Jude's baseball game tomorrow at 4:30pm"
- "Move Tuesday's dentist appointment to Thursday at 2pm"
- "Delete the PTA meeting on Friday"

---

## Prerequisites

- Python 3.11+
- A Google account with access to the family calendar
- A Telegram account

---

## Setup

### 1. Clone and install dependencies

```bash
git clone <repo-url>
cd famlobster
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Create a Telegram bot

1. Open Telegram and message **@BotFather**
2. Send `/newbot` and follow the prompts
3. Copy the bot token (looks like `123456789:ABCdef...`)

### 3. Set up Google Calendar API

1. Go to [console.cloud.google.com](https://console.cloud.google.com) and create a new project (e.g., "FamLobster")
2. Navigate to **APIs & Services → Library**, search for **Google Calendar API**, and enable it
3. Go to **APIs & Services → Credentials → Create Credentials → OAuth client ID**
4. Set application type to **Desktop app**, give it any name, then click **Create**
5. Click the download icon to download the JSON file
6. Save it as `credentials.json` in the project root
7. Go to **APIs & Services → OAuth consent screen**:
   - If using a personal Google account: set to **External**, add your email as a test user
   - If using Google Workspace: set to **Internal**

### 4. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and fill in:
- `TELEGRAM_BOT_TOKEN` — from BotFather
- `ANTHROPIC_API_KEY` — from [console.anthropic.com](https://console.anthropic.com)
- `TIMEZONE` — your family's timezone (e.g., `America/Chicago`)
- Leave `REMINDER_CHAT_ID` blank for now (see step 6)

### 5. First run — authorize Google Calendar

```bash
python bot.py
```

On first run, a browser window will open asking you to authorize access to Google Calendar. Sign in with the account that owns the family calendar. After authorizing, a `token.json` file is saved and the browser can be closed.

### 6. Get your group chat ID (for reminders)

1. Add your bot to your family Telegram group chat
2. Send `/get_id` in the group chat
3. The bot will reply with the chat ID (a negative number like `-1001234567890`)
4. Add it to `.env` as `REMINDER_CHAT_ID`
5. Restart `python bot.py`

---

## Running

```bash
source .venv/bin/activate
python bot.py
```

### Running in production (systemd)

Create `/etc/systemd/system/famlobster.service`:

```ini
[Unit]
Description=FamLobster Telegram Bot
After=network.target

[Service]
Type=simple
User=your-username
WorkingDirectory=/path/to/famlobster
ExecStart=/path/to/famlobster/.venv/bin/python bot.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Then:
```bash
sudo systemctl enable --now famlobster
sudo journalctl -u famlobster -f   # view logs
```

---

## Bot commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message and usage examples |
| `/reset` | Clear conversation history for this chat |
| `/get_id` | Show the current chat's ID (for `REMINDER_CHAT_ID`) |

Everything else is natural language — just talk to the bot.

---

## Troubleshooting

**"credentials.json not found"** — Make sure you downloaded and saved the OAuth credentials file as `credentials.json` in the project root.

**"Token has been expired or revoked"** — Delete `token.json` and restart the bot to re-authorize.

**Bot doesn't respond** — Check that the bot token in `.env` is correct and that the bot is not already running elsewhere.

**"Quota exceeded"** — The Google Calendar API has a free quota of 1 million requests/day, which is more than enough for family use.

**Reminders not sending** — Make sure `REMINDER_CHAT_ID` is set correctly (it should be a negative number for group chats). Use `/get_id` in the group to confirm.

**Calendar changes going to the wrong calendar** — Set `GOOGLE_CALENDAR_ID` in `.env` to the specific calendar ID. Find it in Google Calendar settings under each calendar's details.
