# FamLobster — Feature Roadmap

Ideas for future bot capabilities, roughly ordered by usefulness and ease of implementation.

---

## 🛒 Grocery & Shopping Lists
**Difficulty:** Easy
**Backend:** Google Tasks API or a Google Sheet

Family members can add, view, and check off items from a shared grocery list. Claude understands natural language so "we're out of milk and we need more cereal" just works.

**Example messages:**
- "Add milk, eggs, and cereal to the grocery list"
- "What's on the grocery list?"
- "Remove eggs, I already got them"
- "Clear the list, we did the shopping"

**Implementation notes:**
- Google Tasks API is the simplest option — free, no extra setup, already in the OAuth scope family
- One task list named "Groceries" acts as the shared list
- Add `tasks` scope to `auth.py` and a `GoogleTasksService` alongside the calendar
- Tools needed: `list_tasks`, `add_task`, `complete_task`, `clear_completed_tasks`
- Could also use a Google Sheet if you want a persistent history of past lists

---

## 📋 Family To-Do / Chores
**Difficulty:** Easy
**Backend:** Google Tasks API

Assign tasks to family members and track completion. Could have separate task lists per person or a single shared "Family Chores" list.

**Example messages:**
- "Add 'mow the lawn' to Jude's chore list"
- "What chores are still pending?"
- "Mark 'take out trash' as done"
- "What does everyone have to do this week?"

**Implementation notes:**
- Same Google Tasks API as grocery lists — separate task lists per person
- Can be added alongside grocery list in the same implementation pass

---

## 🌤️ Weather for Events
**Difficulty:** Easy
**Backend:** Open-Meteo API (free, no API key needed)

When someone asks about an event or a day, the bot can automatically include a weather forecast. Especially useful for outdoor events like Jude's baseball games.

**Example messages:**
- "What's the weather like for Saturday's game?"
- "Will it rain this week?"
- "What should the kids wear tomorrow?"

**Implementation notes:**
- Open-Meteo is completely free with no API key — just an HTTP call with lat/lon
- Add `FAMILY_LATITUDE` and `FAMILY_LONGITUDE` to `.env`
- Single `get_weather(date)` tool — Claude will call it when a message involves weather or outdoor plans
- Can combine with calendar: "show me this week's events with weather"

---

## 🎂 Birthday & Anniversary Reminders
**Difficulty:** Easy
**Backend:** Google Calendar (already connected)

A dedicated "Birthdays" calendar (or labels in the main calendar) that the bot monitors. Sends a morning reminder on the day and a heads-up a few days before.

**Example messages:**
- "When is mom's birthday?"
- "Add dad's birthday on April 15"
- "What family birthdays are coming up this month?"

**Implementation notes:**
- Could use a separate Google Calendar named "Birthdays" — set `BIRTHDAY_CALENDAR_ID` in `.env`
- Existing `list_events` and `create_event` tools already handle this
- Add a new APScheduler job: weekly scan for birthdays in the next 7 days, send a heads-up
- No new tools needed — just scheduler logic

---

## 🍽️ Meal Planning
**Difficulty:** Medium
**Backend:** Google Sheets

Plan what's for dinner each day of the week. Family can check the plan, suggest changes, and the bot can automatically build a grocery list from the meal plan.

**Example messages:**
- "What's for dinner tonight?"
- "Put tacos on Tuesday and pasta on Thursday"
- "Build a grocery list from this week's meals"
- "What are we having this week?"

**Implementation notes:**
- Google Sheets as the backend — one sheet per week, columns for each day
- Needs Google Sheets API enabled + `spreadsheets` scope added to `auth.py`
- Tools: `get_meal_plan`, `set_meal`, `generate_grocery_list_from_meals`
- The grocery list generation is a great Claude use case — it reasons about ingredients

---

## 📍 Family Location Check-In
**Difficulty:** Medium
**Backend:** None (Telegram-native)

Family members can share their location or status with the group ("I'm leaving school now", "running 20 min late"). The bot can log these and answer "where is everyone?"

**Example messages:**
- "Where's Jude?"
- "Tell the family I'm on my way home"
- "I'll be 30 minutes late"

**Implementation notes:**
- Simplest version: bot relays messages to the group with a timestamp ("Jude said: leaving school — 3:42pm")
- More advanced: store last-known status in memory, bot answers "where is everyone" from that
- No external API needed — pure bot logic

---

## 💰 Family Budget Tracker
**Difficulty:** Medium
**Backend:** Google Sheets

Log family expenses by category and get summaries. Useful for tracking how much is being spent on groceries, gas, activities, etc.

**Example messages:**
- "Log $47 at Costco under groceries"
- "How much have we spent on groceries this month?"
- "Show me this month's spending by category"
- "We spent $120 on Jude's baseball gear"

**Implementation notes:**
- Google Sheets as the ledger — one row per expense, columns for date/amount/category/note
- Tools: `log_expense`, `get_spending_summary`, `get_expenses_by_category`
- Needs Google Sheets API + scope (same as meal planning)

---

## 📬 Family Broadcast Messages
**Difficulty:** Easy
**Backend:** Telegram (already connected)

Send an announcement to the whole family group from any family member via the bot, with a consistent format so it's clear it's an "official" family notice.

**Example messages:**
- "Announce that dinner is at 6:30 tonight"
- "Send a family reminder that grandma's visit is this weekend"

**Implementation notes:**
- No new API needed — bot already sends to `REMINDER_CHAT_ID`
- Just a new bot command or Claude tool: format the message prominently and post it
- Could include a `/announce` command as a shortcut

---

## 🔑 Quick Notes / Family Wiki
**Difficulty:** Easy
**Backend:** Google Docs or a Google Sheet

A place to store frequently referenced info: wifi password, alarm code, vet's phone number, school contact list, etc. Family can ask the bot and it looks it up.

**Example messages:**
- "What's the wifi password?"
- "What's Dr. Smith's phone number?"
- "Save the new garage code as 4821"

**Implementation notes:**
- A single Google Sheet with two columns: key and value
- Tools: `lookup_note`, `save_note`, `list_notes`
- Simple but surprisingly useful for a family

---

## Implementation Priority (suggested order)

| # | Feature | Why first |
|---|---------|-----------|
| 1 | Grocery & shopping lists | Immediately useful, easy, Google Tasks already in OAuth scope |
| 2 | Weather for events | Zero auth setup, free API, high value for outdoor events |
| 3 | Birthday reminders | Reuses existing calendar tools, just needs scheduler logic |
| 4 | Quick notes / family wiki | Simple, high daily utility |
| 5 | Meal planning | Medium effort, unlocks grocery list generation |
| 6 | Chores / to-do | Same API as grocery lists, easy add-on |
| 7 | Budget tracker | Needs Sheets API but very useful |
| 8 | Broadcast messages | Trivial to add |
| 9 | Location check-in | Nice to have, no external API |
