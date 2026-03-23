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

> **Security note:** Keep all secrets (API keys, credentials, tokens) **outside the repo folder**.
> The steps below store them in `~/.config/famlobster/` so they can never accidentally be committed,
> even if `.gitignore` is misconfigured or you run `git add .` by mistake.

### 1. Clone and install dependencies

```bash
git clone <repo-url>
cd famlobster
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Create a secrets directory outside the repo

```bash
mkdir -p ~/.config/famlobster
chmod 700 ~/.config/famlobster
```

All sensitive files go here — never inside the repo folder.

### 3. Create a Telegram bot

1. Open Telegram and message **@BotFather**
2. Send `/newbot` and follow the prompts
3. Copy the bot token (looks like `123456789:ABCdef...`)

### 4. Set up Google Calendar API (Service Account)

No browser or OAuth flow needed — the bot uses a service account key file.

1. Go to [console.cloud.google.com](https://console.cloud.google.com) and create a new project (e.g., "FamLobster")
2. Navigate to **APIs & Services → Library**, search for **Google Calendar API**, and enable it
3. Go to **APIs & Services → Credentials → Create Credentials → Service account**
4. Give it a name (e.g., "famlobster"), click **Create and Continue**, skip the optional steps, click **Done**
5. Click the service account you just created, go to the **Keys** tab
6. Click **Add Key → Create new key → JSON → Create**
7. A JSON file downloads — save it to your secrets directory:
   ```bash
   mv ~/Downloads/*.json ~/.config/famlobster/service-account.json
   ```
8. Copy the service account's email address (looks like `famlobster@your-project.iam.gserviceaccount.com`) — you'll need it in the next step

### 5. Share your Google Calendar with the service account

The bot can only access calendars explicitly shared with it.

1. Open **Google Calendar** on the web
2. Find your family calendar in the left sidebar → click the three dots → **Settings and sharing**
3. Scroll to **Share with specific people** → **Add people**
4. Paste the service account email from step 4
5. Set permission to **Make changes to events**
6. Click **Send**

### 6. Configure environment

Create your `.env` file in the secrets directory:

```bash
cp .env.example ~/.config/famlobster/.env
```

Edit `~/.config/famlobster/.env` and fill in:
- `TELEGRAM_BOT_TOKEN` — from BotFather
- `ANTHROPIC_API_KEY` — from [console.anthropic.com](https://console.anthropic.com)
- `TIMEZONE` — your family's timezone (e.g., `America/Chicago`)
- `GOOGLE_SERVICE_ACCOUNT_FILE` — full path to your key file:
  ```
  GOOGLE_SERVICE_ACCOUNT_FILE=/home/famlobster/.config/famlobster/service-account.json
  ```
- Leave `REMINDER_CHAT_ID` blank for now (see step 8)

### 7. Run the bot

```bash
dotenv -f ~/.config/famlobster/.env run python bot.py
```

No browser auth needed — it connects immediately using the service account key.

### 8. Get your group chat ID (for reminders)

1. Add your bot to your family Telegram group chat
2. Send `/get_id` in the group chat
3. The bot replies with the chat ID (a negative number like `-1001234567890`)
4. Add it to `~/.config/famlobster/.env` as `REMINDER_CHAT_ID`
5. Restart the bot

---

## Running

```bash
cd famlobster
source .venv/bin/activate
export $(cat ~/.config/famlobster/.env | grep -v '#' | xargs)
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
EnvironmentFile=/home/your-username/.config/famlobster/.env
ExecStart=/path/to/famlobster/.venv/bin/python bot.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

The `EnvironmentFile` line loads secrets directly from `~/.config/famlobster/.env` without
touching the repo at all.

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

**"service-account.json not found"** — Check that `GOOGLE_SERVICE_ACCOUNT_FILE` in your `.env` points to the correct absolute path (e.g., `/home/famlobster/.config/famlobster/service-account.json`).

**"Calendar not found" or no events showing** — Make sure you shared the calendar with the service account email address and set permission to "Make changes to events".

**Bot doesn't respond** — Check that the bot token in `.env` is correct and that the bot is not already running elsewhere.

**"Quota exceeded"** — The Google Calendar API has a free quota of 1 million requests/day, which is more than enough for family use.

**Reminders not sending** — Make sure `REMINDER_CHAT_ID` is set correctly (it should be a negative number for group chats). Use `/get_id` in the group to confirm.

**Calendar changes going to the wrong calendar** — Set `GOOGLE_CALENDAR_ID` in `.env` to the specific calendar ID. Find it in Google Calendar settings under each calendar's details.
