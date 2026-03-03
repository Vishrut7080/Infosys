# ========================
# Telegram/telegram.py
# ========================
# Uses Telethon (User API) to interact with YOUR personal Telegram account.
# This is NOT a bot — it logs in as YOU and reads/sends your actual messages.
#
# Requirements:
#   uv add telethon
#
# .env variables needed:
#   TELEGRAM_API_ID=12345678
#   TELEGRAM_API_HASH=abcdef1234567890abcdef
#   TELEGRAM_PHONE=+91xxxxxxxxxx
# ========================

import os
import asyncio
import threading
import time
from dotenv import load_dotenv

from telethon import TelegramClient, events
from telethon.tl.types import User, Chat, Channel

load_dotenv()

API_ID   = int(os.getenv('TELEGRAM_API_ID', 0))
API_HASH = os.getenv('TELEGRAM_API_HASH', '')
PHONE    = os.getenv('TELEGRAM_PHONE', '')

# Session file stored in Telegram/ folder — created on first login
SESSION_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'telegram_session')

# ----------------------
# Global state
# ----------------------
_client               = None   # TelegramClient instance
_loop                 = None   # asyncio event loop in background thread
_notification_callback = None  # called when new message arrives


# ----------------------
# Helper: Get display name
# ----------------------
def _get_name(entity) -> str:
    if isinstance(entity, User):
        name = ' '.join(filter(None, [entity.first_name, entity.last_name]))
        return name or entity.username or 'Unknown'
    elif isinstance(entity, (Chat, Channel)):
        return entity.title or 'Unknown Group'
    return 'Unknown'


# ----------------------
# Async: Initialize and connect client
# ----------------------
async def _init_client(phone_callback=None, code_callback=None):
    global _client
    _client = TelegramClient(
        SESSION_FILE,
        API_ID,
        API_HASH,
        device_model="Desktop",
        system_version="Windows 10",
        app_version="1.0",
        lang_code="en",
        system_lang_code="en"
    )

    # If session file already exists, just connect silently
    if os.path.exists(SESSION_FILE + '.session'):
        await _client.connect()
        if await _client.is_user_authorized():
            print('[Telegram] Session found. Logged in automatically.')
            return

    # First run — need phone + OTP
    await _client.connect()

    if not await _client.is_user_authorized():
        # Get phone number via callback (voice) or fallback to input()
        phone = phone_callback() if phone_callback else input('Enter phone number: ')
        await _client.send_code_request(phone)

        # Get OTP via callback (voice) or fallback to input()
        code = code_callback() if code_callback else input('Enter OTP: ')
        await _client.sign_in(phone, code)
        print('[Telegram] Signed in successfully.')


# ----------------------
# Async: Fetch latest N conversations
# ----------------------
async def _get_messages(count: int = 5) -> list[dict]:
    results = []
    async for dialog in _client.iter_dialogs(limit=count):
        entity = dialog.entity
        name   = _get_name(entity)

        msg = dialog.message
        if msg and msg.message:
            text = msg.message
        elif msg:
            text = '[Media or unsupported message]'
        else:
            text = '[No messages]'

        date_str = msg.date.strftime("%a, %d %b %Y %H:%M") if msg and msg.date else 'Unknown'

        results.append({
            'name'   : name,
            'message': text[:200],
            'date'   : date_str,
            'unread' : dialog.unread_count,
        })

    return results


# ----------------------
# Async: Send message to a contact
# ----------------------
async def _send_message(recipient_name: str, message: str) -> tuple[bool, str]:
    try:
        # Try direct username/phone lookup first
        result = await _client.get_entity(recipient_name)
        await _client.send_message(result, message)
        return True, f'Message sent to {recipient_name}.'
    except Exception:
        # Search through dialogs by name
        async for dialog in _client.iter_dialogs():
            name = _get_name(dialog.entity).lower()
            if recipient_name.lower() in name:
                await _client.send_message(dialog.entity, message)
                return True, f'Message sent to {_get_name(dialog.entity)}.'
        return False, f'Could not find contact: {recipient_name}.'


# ----------------------
# Async: Listen for incoming messages
# ----------------------
async def _start_listener():
    @_client.on(events.NewMessage(incoming=True))
    async def handler(event):
        sender = await event.get_sender()
        name   = _get_name(sender) if sender else 'Unknown'
        text   = event.raw_text or '[Media]'

        if _notification_callback:
            _notification_callback(name, text)

    await _client.run_until_disconnected()


# ========================
# PUBLIC API — synchronous wrappers
# ========================

def _run_async(coro):
    """Runs async coroutine from synchronous code using the background loop."""
    if _loop is None:
        raise RuntimeError('[Telegram] Client not started. Call start_telegram_in_thread() first.')
    future = asyncio.run_coroutine_threadsafe(coro, _loop)
    return future.result(timeout=15)


def telegram_get_messages(count: int = 5) -> list[dict]:
    """Fetches latest N Telegram conversations."""
    return _run_async(_get_messages(count))


def telegram_send_message(recipient: str, message: str) -> tuple[bool, str]:
    """Sends a Telegram message to a contact by name."""
    return _run_async(_send_message(recipient, message))


def telegram_get_latest() -> dict | None:
    """Returns the single most recent Telegram message."""
    messages = _run_async(_get_messages(1))
    return messages[0] if messages else None


def set_notification_callback(callback):
    """
    Sets a function called when a new Telegram message arrives.
    callback(sender_name: str, message_text: str)
    """
    global _notification_callback
    _notification_callback = callback


# ----------------------
# Start client in background thread
# ----------------------
def start_telegram_in_thread(phone_callback=None, code_callback=None):
    """
    Starts Telethon client in a background thread with its own event loop.
    First run will prompt for phone number OTP in terminal.
    After that, session file handles auth automatically.
    """
    global _loop

    def run():
        global _loop
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
        _loop.run_until_complete(_init_client(phone_callback, code_callback))
        _loop.run_until_complete(_start_listener())

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    print('[Telegram] Client starting in background...')

    # Wait up to 15 seconds for client to connect
    for _ in range(30):
        if _client and _client.is_connected():
            print('[Telegram] Client connected successfully.')
            break
        time.sleep(0.5)
    else:
        print('[Telegram] Warning: Client took too long to connect.')

    return thread


__all__ = [
    'start_telegram_in_thread',
    'telegram_get_messages',
    'telegram_send_message',
    'telegram_get_latest',
    'set_notification_callback',
]