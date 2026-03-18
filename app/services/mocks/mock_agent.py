"""Mock LLM Agent — allows the app to run without an OpenRouter API key.

When MOCK_SERVICES=True, this agent replaces OpenRouterAgent. It pattern-
matches user input and dispatches tool calls locally, returning canned
LLM-like responses so the full UI loop can be exercised.
"""

import json
import re
from app.tools.registry import registry
from app.core.logging import logger


class MockAgent:
    """Drop-in replacement for ``OpenRouterAgent`` that needs no API key."""

    def __init__(self, user_email: str):
        self.user_email = user_email
        self.last_tool_results: list[dict] = []

    def chat(self, user_input: str) -> str:
        """Always returns a string; falls back to a hint message if unrecognised."""
        result = self.try_chat(user_input)
        if result is not None:
            return result
        return (
            f"I heard: \"{user_input}\". "
            "I'm running in offline mode, so I can help with emails, Telegram, "
            "navigation, tasks, time, date, and jokes. Try asking something specific!"
        )

    def try_chat(self, user_input: str) -> str | None:
        """Pattern-match user_input and return a response, or None if unrecognised."""
        self.last_tool_results = []
        text = user_input.lower().strip()

        # ── Navigation ───────────────────────────────────
        nav_map = {
            "dashboard": "/dashboard#dashboard",
            "profile": "/dashboard#profile",
            "inbox": "/dashboard#inbox",
            "tasks": "/dashboard#tasks",
            "login": "/",
            "signup": "/signup",
        }
        for keyword, url in nav_map.items():
            if keyword in text and any(w in text for w in ("go to", "open", "navigate", "show")):
                result = self._call_tool("navigate", {"page": url.split("#")[-1] if "#" in url else url})
                if result:
                    return f"Navigating to {keyword}."
                break

        # ── Email ────────────────────────────────────────
        if "send email" in text or "send an email" in text:
            return "Sure, I can send an email. Who should I send it to? Also, please provide your 4-digit Gmail PIN."

        if re.search(r"(check|read|get|fetch).*(email|inbox|mail)", text):
            result = self._call_tool("get_emails", {"count": 5})
            suggestion = (" By the way, I spotted a meeting in one of those emails — want me to add it as a task?")
            return (result or "I couldn't fetch your emails right now.") + suggestion

        if re.search(r"(overview|summary).*(inbox|email|mail)", text):
            result = self._call_tool("get_email_overview", {"count": 10})
            return result or "I couldn't get your inbox overview."

        if re.search(r"(important|urgent|priority).*(email|mail)", text):
            result = self._call_tool("get_important_emails", {"count": 5})
            return result or "No important emails found."

        if re.search(r"(read|open|body|full|content).*(email|mail)", text):
            result = self._call_tool("get_email_body", {"index": 1})
            return result or "I couldn't read that email."

        if re.search(r"search.*(email|mail)", text):
            query = re.sub(r"^.*search\s+(emails?|mails?)\s+(for\s+)?", "", text).strip() or "meeting"
            result = self._call_tool("search_emails", {"query": query, "count": 5})
            return result or f"No emails found for '{query}'."

        if "verify" in text and "gmail" in text:
            pin_match = re.search(r"\b(\d{4})\b", text)
            if pin_match:
                result = self._call_tool("verify_gmail_pin", {"pin": pin_match.group(1)})
                return result or "PIN verification failed."
            return "Please provide your 4-digit Gmail PIN."

        # ── Telegram ─────────────────────────────────────
        if "send telegram" in text or "send a telegram" in text:
            return "Sure, I can send a Telegram message. Who should I send it to? Also, please provide your 4-digit Telegram PIN."

        if re.search(r"(check|read|get|fetch).*(telegram|tg)", text):
            result = self._call_tool("get_telegram_messages", {"count": 5})
            return result or "No Telegram messages found."

        if re.search(r"(conversation|chat|history).*(with|from)\s+(\w[\w\s-]*)", text):
            m = re.search(r"(with|from)\s+([\w][\w\s-]*?)(?:\s*\?)?$", text)
            contact = m.group(2).strip().title() if m else "Mock-Alice"
            result = self._call_tool("get_telegram_conversation", {"contact": contact, "count": 10})
            return result or f"No conversation found with {contact}."

        if "verify" in text and "telegram" in text:
            pin_match = re.search(r"\b(\d{4})\b", text)
            if pin_match:
                result = self._call_tool("verify_telegram_pin", {"pin": pin_match.group(1)})
                return result or "PIN verification failed."
            return "Please provide your 4-digit Telegram PIN."

        # ── Tasks ────────────────────────────────────────
        if re.search(r"(add|create|new|remind me).*(task|todo|to.?do)", text):
            title = re.sub(r"^.*(add|create|new)\s+(a\s+)?(task|todo|to-do)\s*", "", text).strip() or "New task"
            result = self._call_tool("add_task", {"title": title.capitalize()})
            return result or "Task created."

        if re.search(r"(list|show|what are|my)\s*(pending|done|all)?\s*(tasks?|todos?|to.?dos?)", text):
            status_m = re.search(r"\b(pending|done|all)\b", text)
            status = status_m.group(1) if status_m else "pending"
            result = self._call_tool("list_tasks", {"status": status})
            return result or "No tasks found."

        if re.search(r"(complete|finish|done|mark).*(task)\s*#?(\d+)", text):
            id_m = re.search(r"#?(\d+)", text)
            if id_m:
                result = self._call_tool("complete_task", {"task_id": int(id_m.group(1))})
                return result or "Task updated."
            return "Please specify the task number."

        if re.search(r"(delete|remove).*(task)\s*#?(\d+)", text):
            id_m = re.search(r"#?(\d+)", text)
            if id_m:
                result = self._call_tool("delete_task", {"task_id": int(id_m.group(1))})
                return result or "Task deleted."
            return "Please specify the task number."

        # ── System tools ─────────────────────────────────
        if re.search(r"(what time|current time|time is it)", text):
            result = self._call_tool("get_time", {})
            return result or "I couldn't check the time."

        if re.search(r"(what date|today.?s date|what is the date)", text):
            result = self._call_tool("get_date", {})
            return result or "I couldn't check the date."

        if re.search(r"(tell|say).*(joke|funny)", text):
            result = self._call_tool("tell_joke", {})
            return result or "Why don't scientists trust atoms? Because they make up everything!"

        if re.search(r"(who am i|my profile|user profile)", text):
            result = self._call_tool("get_user_profile", {})
            return result or "I couldn't fetch your profile."

        if re.search(r"(system status|system info)", text):
            result = self._call_tool("get_system_status", {})
            return result or "All systems are running normally."

        # ── Cancel ───────────────────────────────────────
        if re.search(r"(cancel|never ?mind|stop|abort)", text):
            return "Okay, cancelled."

        # ── Greeting ─────────────────────────────────────
        if re.search(r"^(hi|hello|hey|good morning|good afternoon|good evening)\b", text):
            return "Hello! How can I help you today? I can manage your emails, Telegram messages, or navigate the app."

        if re.search(r"(help|what can you do|capabilities|what do you do|what are you|tell me about yourself|introduce yourself|what do you know)", text):
            return ("I'm your personal voice assistant! I can: "
                    "read your Gmail inbox (overview, important emails, full email body, search) and send emails, "
                    "read your Telegram messages and conversations and send Telegram messages, "
                    "manage your tasks (add, list, complete, delete), "
                    "check the date and time, do calculations, tell jokes, show your profile, "
                    "and navigate the app by voice. Just ask!")

        if re.search(r"(bye|goodbye|see you|good night)", text):
            return "Goodbye! Have a great day."

        # ── Unrecognised — caller decides what to do ──────
        return None

    def _call_tool(self, tool_name: str, args: dict) -> str | None:
        """Call a registered tool and track the result."""
        tool = registry.get_tool(tool_name)
        if not tool:
            logger.warning(f"[MockAgent] Tool '{tool_name}' not found")
            return None
        try:
            result = tool["handler"](self.user_email, **args)
            result_str = str(result)
            self.last_tool_results.append({"tool": tool_name, "result": result_str})
            return result_str
        except Exception as e:
            logger.error(f"[MockAgent] Tool error {tool_name}: {e}")
            return f"Error: {e}"
