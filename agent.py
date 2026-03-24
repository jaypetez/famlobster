"""
Claude AI agent with Google Calendar MCP tools.

Maintains per-chat conversation history and runs the tool-use loop
so Claude can make multiple calendar API calls per user message.
"""

import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import anthropic
from mcp import ClientSession

logger = logging.getLogger(__name__)

MAX_HISTORY_TURNS = 20  # max user+assistant pairs to keep per chat

SYSTEM_PROMPT = """You are FamLobster, a friendly family assistant bot that manages \
the family Google Calendar. Today is {today}. The family's timezone is {timezone}.

Help family members view, add, edit, and delete calendar events using natural language. \
Keep responses concise and friendly — this is a family group chat.

When listing events, format them clearly with day, date, time, and title.
When creating events, confirm the details back to the user after saving.
When you're unsure about a date or time, ask for clarification before acting.
If a calendar operation fails, explain what went wrong in plain English."""


class FamilyAgent:
    def __init__(self, mcp_session: ClientSession):
        self.session = mcp_session
        self.client = anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        self.model = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
        self.timezone = os.getenv("TIMEZONE", "America/Chicago")
        self.conversation_history: dict[int, list[dict]] = {}
        self.tools: list[dict] = []

    async def load_tools(self) -> None:
        """Fetch tool definitions from the MCP server and convert to Anthropic format."""
        result = await self.session.list_tools()
        self.tools = [
            {
                "name": tool.name,
                "description": tool.description or "",
                "input_schema": tool.inputSchema,
            }
            for tool in result.tools
        ]
        logger.info("Loaded %d calendar tools from MCP server", len(self.tools))

    def clear_history(self, chat_id: int) -> None:
        self.conversation_history.pop(chat_id, None)

    async def process_message(self, chat_id: int, user_text: str) -> str:
        """Main entry point — append user message to history, run tool loop, return reply."""
        history = self.conversation_history.setdefault(chat_id, [])

        # Snapshot length BEFORE adding anything so we can fully restore on error
        snapshot_len = len(history)

        history.append({"role": "user", "content": user_text})
        self._trim_history(history)

        try:
            reply = await self._run_tool_loop(chat_id)
        except anthropic.BadRequestError as e:
            # History is corrupted (mismatched tool_use/tool_result). Clear it
            # entirely and tell the user so they can just repeat their message.
            logger.error("Corrupted history for chat %d, clearing: %s", chat_id, e)
            self.clear_history(chat_id)
            return (
                "I hit a conversation error and had to reset. "
                "Sorry about that — please send your message again."
            )
        except Exception:
            logger.exception("Error in tool loop for chat %d", chat_id)
            # Restore history to exactly where it was before this request
            del history[snapshot_len:]
            raise

        return reply

    async def _run_tool_loop(self, chat_id: int) -> str:
        """Run the Claude tool-use loop until end_turn, return final text."""
        history = self.conversation_history[chat_id]
        today = datetime.now(ZoneInfo(self.timezone)).date().isoformat()
        system = SYSTEM_PROMPT.format(
            today=today,
            timezone=self.timezone,
        )

        while True:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=system,
                messages=history,
                tools=self.tools,
            )

            if response.stop_reason == "end_turn":
                # Extract text from the response and save to history
                text = self._extract_text(response.content)
                history.append(
                    {"role": "assistant", "content": response.content}
                )
                return text

            if response.stop_reason == "tool_use":
                # Append the full assistant message (text + tool_use blocks)
                history.append(
                    {"role": "assistant", "content": response.content}
                )

                # Execute every tool call and collect results
                tool_results = []
                for block in response.content:
                    if block.type != "tool_use":
                        continue
                    logger.info("Calling tool %s with args %s", block.name, block.input)
                    mcp_result = await self.session.call_tool(block.name, block.input)
                    result_text = (
                        mcp_result.content[0].text
                        if mcp_result.content
                        else '{"error": "no result"}'
                    )
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result_text,
                        }
                    )

                # All tool results go back in a single user message
                history.append({"role": "user", "content": tool_results})
                continue

            # Unexpected stop reason — return whatever text we have
            return self._extract_text(response.content) or "(no response)"

    def _extract_text(self, content: list) -> str:
        parts = [block.text for block in content if hasattr(block, "text")]
        return "\n".join(parts).strip()

    def _trim_history(self, history: list) -> None:
        """Keep history within MAX_HISTORY_TURNS pairs to avoid unbounded growth."""
        # Count user messages as a proxy for turns
        user_count = sum(1 for m in history if m["role"] == "user")
        while user_count > MAX_HISTORY_TURNS and len(history) >= 2:
            # Remove the oldest user+assistant pair
            history.pop(0)
            if history and history[0]["role"] == "assistant":
                history.pop(0)
            user_count -= 1
