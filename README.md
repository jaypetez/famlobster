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

### 4. Set up Google Calendar API

1. Go to [console.cloud.google.com](https://console.cloud.google.com) and create a new project (e.g., "FamLobster")
2. Navigate to **APIs & Services → Library**, search for **Google Calendar API**, and enable it
3. Go to **APIs & Services → Credentials → Create Credentials → OAuth client ID**
4. Set application type to **Desktop app**, give it any name, then click **Create**
5. Click the download icon to download the JSON file
6. Save it to your secrets directory — **not inside the repo**:
   ```bash
   mv ~/Downloads/client_secret_*.json ~/.config/famlobster/credentials.json
   ```
7. Go to **APIs & Services → OAuth consent screen**:
   - If using a personal Google account: set to **External**, add your email as a test user
   - If using Google Workspace: set to **Internal**

### 5. Configure environment

Create your `.env` file in the secrets directory:

```bash
cp .env.example ~/.config/famlobster/.env
```

Edit `~/.config/famlobster/.env` and fill in:
- `TELEGRAM_BOT_TOKEN` — from BotFather
- `ANTHROPIC_API_KEY` — from [console.anthropic.com](https://console.anthropic.com)
- `TIMEZONE` — your family's timezone (e.g., `America/Chicago`)
- Point the credential paths to your secrets directory:
  ```
  GOOGLE_CREDENTIALS_FILE=/home/YOUR_USERNAME/.config/famlobster/credentials.json
  GOOGLE_TOKEN_FILE=/home/YOUR_USERNAME/.config/famlobster/token.json
  ```
- Leave `REMINDER_CHAT_ID` blank for now (see step 7)

### 6. Authorize Google Calendar (run once on your laptop)

The bot runs headlessly on the server, so you generate the auth token on your **Windows laptop** where a browser is available, then copy it to the server. You only ever do this once.

**On your laptop:**

```bash
pip install google-auth-oauthlib
python auth.py
```

- It will ask for the path to your `credentials.json` (the file you downloaded from Google Cloud)
- A browser opens — sign in with the Google account that owns the family calendar
- Click through any "unverified app" warnings → Allow
- `token.json` is saved in the current folder

**Copy it to the server:**

```bash
scp token.json famlobster@yourserver:~/.config/famlobster/token.json
```

The token auto-refreshes silently — you'll never need to do this again unless you revoke access in your Google account settings.

### 7. Get your group chat ID (for reminders)

1. Add your bot to your family Telegram group chat
2. Send `/get_id` in the group chat
3. The bot will reply with the chat ID (a negative number like `-1001234567890`)
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

### Google Auth

**Token stops working every 7 days**
This happens when your OAuth app is still in "Testing" mode. Google limits refresh tokens to 7 days in testing mode. Fix it permanently:
1. Google Cloud Console → **APIs & Services → OAuth consent screen**
2. Click **Publish App** and confirm
3. Re-run `auth.py` on your laptop and SCP a fresh `token.json` to the server — this is the last time you'll need to do it

**"Token has been expired or revoked"**
Re-run `auth.py` on your laptop and SCP the new `token.json` to the server:
```bash
python auth.py
scp token.json famlobster@yourserver:~/.config/famlobster/token.json
```

**"token.json not found"**
You need to run `auth.py` on your laptop first — see the setup steps above.

**"credentials.json not found"**
Check that `GOOGLE_CREDENTIALS_FILE` in your `.env` points to the correct absolute path (e.g., `/home/famlobster/.config/famlobster/credentials.json`).

**Bot says "there's a technical issue with the calendar" or can't read/write events**
The Google Calendar API is probably not enabled in your Google Cloud project:
1. Go to Google Cloud Console → **APIs & Services → Library**
2. Search for **Google Calendar API** → click it → click **Enable**
3. Wait 30 seconds and try again

If it's already enabled, your token.json may have been generated before the API was enabled. Re-run `auth.py` on your laptop to get a fresh token:
```bash
python auth.py
scp token.json famlobster@yourserver:~/.config/famlobster/token.json
```

**"This app isn't verified" warning on the Google auth page**
This is normal for private apps. Click **Advanced → Go to FamLobster (unsafe)** to proceed. It just means Google hasn't reviewed the app — it's your own app so this is fine.

---

### Telegram

**Bot doesn't respond in the group chat**
- Make sure the bot is actually running (`python bot.py` in a terminal or systemd service active)
- Disable privacy mode in BotFather: `/mybots` → your bot → Bot Settings → Group Privacy → Turn off
- Remove the bot from the group and re-add it after changing privacy mode
- Try the command with your bot's username: `/get_id@YourBotName`

**Bot doesn't respond at all**
Check that `TELEGRAM_BOT_TOKEN` in `.env` is correct and the bot isn't already running in another terminal.

---

### Calendar

**"Quota exceeded"**
The Google Calendar API has a free quota of 1 million requests/day — more than enough for a family bot. If you hit this something is looping; check the logs.

**Reminders not sending**
Make sure `REMINDER_CHAT_ID` is set to a negative number (group chats always have negative IDs). Send `/get_id` in the group to confirm the correct value.

**Calendar changes going to the wrong calendar**
Set `GOOGLE_CALENDAR_ID` in `.env` to the specific calendar ID. Find it in Google Calendar → click the calendar → Settings → scroll down to "Calendar ID".
