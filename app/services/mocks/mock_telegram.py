"""Mock Telegram service — simulates send/receive without Telethon.

Replaces the public API in ``app.services.telegram`` so the agent can
exercise ``send_telegram`` / ``get_telegram_messages`` tool calls without
a real Telegram connection.
"""

from datetime import datetime
from typing import Optional
from app.core.logging import logger


class MockTelegramState:
    """Process-wide store for mock Telegram data."""

    _sent: list[dict] = []
    _inbox: list[dict] = [
        {
            "name": "Mock-Alice",
            "message": "Hey, are you coming to the meeting?",
            "date": datetime.now().strftime("%d %b %H:%M"),
            "unread": 1,
        },
        {
            "name": "Mock-Bob",
            "message": "I sent you the document.",
            "date": datetime.now().strftime("%d %b %H:%M"),
            "unread": 0,
        },
        {
            "name": "Mock-Carol",
            "message": "The deployment went smoothly. All tests passing.",
            "date": datetime.now().strftime("%d %b %H:%M"),
            "unread": 3,
        },
        {
            "name": "Mock-Dave",
            "message": "Can you review my PR when you get a chance?",
            "date": datetime.now().strftime("%d %b %H:%M"),
            "unread": 1,
        },
        {
            "name": "Team Chat",
            "message": "Sprint retro moved to 3 PM today.",
            "date": datetime.now().strftime("%d %b %H:%M"),
            "unread": 5,
        },
        {
            "name": "Mock-Eve",
            "message": "Happy birthday! 🎂",
            "date": datetime.now().strftime("%d %b %H:%M"),
            "unread": 0,
        },
    ]
    # Per-contact conversation history for get_telegram_conversation tool
    _conversations: dict[str, list[dict]] = {
        "Mock-Alice": [
            {"sender": "Mock-Alice", "text": "Hey! Are you free tomorrow for a quick sync?", "date": "Today 09:10"},
            {"sender": "You",        "text": "Sure, around 11 works for me.",                "date": "Today 09:12"},
            {"sender": "Mock-Alice", "text": "Perfect. I'll send a calendar invite.",         "date": "Today 09:13"},
            {"sender": "Mock-Alice", "text": "Hey, are you coming to the meeting?",           "date": "Today 10:00"},
        ],
        "Mock-Bob": [
            {"sender": "Mock-Bob", "text": "Hi! I just sent you the Q3 report doc.",         "date": "Today 08:45"},
            {"sender": "You",      "text": "Got it, I'll review it later today.",             "date": "Today 08:50"},
            {"sender": "Mock-Bob", "text": "I sent you the document.",                        "date": "Today 08:55"},
        ],
        "Team Chat": [
            {"sender": "Mock-Carol", "text": "Morning everyone! The build is green.",         "date": "Today 08:00"},
            {"sender": "Mock-Dave",  "text": "Sprint retro moved to 3 PM today.",             "date": "Today 08:30"},
            {"sender": "Mock-Alice", "text": "Works for me.",                                 "date": "Today 08:35"},
            {"sender": "Team Chat",  "text": "Sprint retro moved to 3 PM today.",             "date": "Today 09:00"},
        ],
    }
    _connected_emails: set[str] = set()

    @classmethod
    def reset(cls):
        cls._sent.clear()
        cls._connected_emails.clear()

    @classmethod
    def get_sent_messages(cls) -> list[dict]:
        return list(cls._sent)


# ---------------------------------------------------------------------------
#  Public API — mirrors app.services.telegram function signatures
# ---------------------------------------------------------------------------

def telegram_get_messages(count: int = 5, email: Optional[str] = None) -> list[dict]:
    logger.info(f"[MockTelegram] get_messages count={count} email={email}")
    return MockTelegramState._inbox[:count]


def telegram_get_conversation(contact: str, count: int = 10, email: Optional[str] = None) -> list[dict]:
    """Return the conversation history with a specific contact."""
    logger.info(f"[MockTelegram] get_conversation contact={contact} count={count} email={email}")
    # Case-insensitive match
    for key, messages in MockTelegramState._conversations.items():
        if key.lower() == contact.lower():
            return messages[-count:]
    # Fall back to inbox message if no conversation history
    for msg in MockTelegramState._inbox:
        if msg['name'].lower() == contact.lower():
            return [{"sender": msg['name'], "text": msg['message'], "date": msg['date']}]
    return []


def telegram_send_message(recipient: str, message: str, email: Optional[str] = None) -> tuple[bool, str]:
    entry = {
        "to": recipient,
        "message": message,
        "from_email": email,
        "timestamp": datetime.now().isoformat(),
    }
    MockTelegramState._sent.append(entry)
    logger.info(f"[MockTelegram] Sent message to {recipient}: {message[:60]}")
    return True, f"[MOCK] Message sent to {recipient}."


def telegram_get_latest(email: Optional[str] = None) -> dict | None:
    msgs = telegram_get_messages(1, email=email)
    return msgs[0] if msgs else None


def telegram_is_authorized(email: Optional[str] = None) -> bool:
    return email in MockTelegramState._connected_emails if email else False


def telegram_status(email: Optional[str] = None) -> str:
    if email and email in MockTelegramState._connected_emails:
        return "ready"
    return "disconnected"


def telegram_is_ready(email: Optional[str] = None) -> bool:
    return telegram_status(email) == "ready"


def start_telegram_in_thread(email: str):
    logger.info(f"[MockTelegram] start_telegram_in_thread({email}) — marking as connected")
    MockTelegramState._connected_emails.add(email)


def stop_telegram_in_thread(email: str):
    logger.info(f"[MockTelegram] stop_telegram_in_thread({email}) — marking as disconnected")
    MockTelegramState._connected_emails.discard(email)


# Stubs for variables that assistant.py's telegram_contacts route accesses
_clients: dict = {}
_loops: dict = {}


def _run_async(email, coro):
    raise RuntimeError("[MockTelegram] _run_async not supported in mock mode")


def _get_name(entity):
    return "MockEntity"
