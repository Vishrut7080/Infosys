# ========================
# Telegram/telegram.py
# ========================
import os
import asyncio
import threading
import time
from datetime import datetime
from dotenv import load_dotenv

from telethon import TelegramClient, events
from telethon.tl.types import User, Chat, Channel

load_dotenv()

# ----------------------
# Global state
# ----------------------
_client               = None   
_loop                 = None   
_notification_callback = None  
_current_session_user  = None

def _get_session_path(email: str):
    """Returns a unique session file path for each user email."""
    if not email: return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'telegram_session')
    safe_email = email.replace('@', '_at_').replace('.', '_')
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), f'session_{safe_email}')

def _get_name(entity) -> str:
    if isinstance(entity, User):
        name = ' '.join(filter(None, [entity.first_name, entity.last_name]))
        return name or entity.username or 'Unknown'
    elif isinstance(entity, (Chat, Channel)):
        return entity.title or 'Unknown Group'
    return 'Unknown'


async def _init_client(email: str):
    global _client, _current_session_user
    try:
        api_id_str = os.getenv('TELEGRAM_API_ID', '0')
        api_hash = os.getenv('TELEGRAM_API_HASH', '')
        
        if not api_id_str or api_id_str == '0' or not api_hash:
            print('[Telegram] API credentials not found in environment.')
            return

        api_id = int(api_id_str)
        session_path = _get_session_path(email)
        _current_session_user = email
        
        print(f'[Telegram] Initializing client for {email} with API ID: {api_id}')
        
        _client = TelegramClient(
            session_path, api_id, api_hash,
            device_model="Desktop", system_version="Windows 10",
            app_version="1.0", lang_code="en", system_lang_code="en",
            request_retries=1,
            connection_retries=3,
            retry_delay=2
        )
        
        await _client.connect()
        print('[Telegram] Connected to Telegram servers.')

        if await _client.is_user_authorized():
            print('[Telegram] Authorized automatically.')
            return

        print('[Telegram] Not authorized. User must complete OTP login.')
    except Exception as e:
        print(f'[Telegram] Init error: {e}')


async def _get_messages(count: int = 5) -> list[dict]:
    results = []
    if not _client: return results
    try:
        async for dialog in _client.iter_dialogs(limit=count):
            entity = dialog.entity
            name   = _get_name(entity)
            msg = dialog.message
            text = msg.message if msg and msg.message else '[Media/Empty]'
            date_str = msg.date.strftime("%d %b %H:%M") if msg and msg.date else ''
            results.append({
                'name'   : name,
                'message': text[:200],
                'date'   : date_str,
                'unread' : dialog.unread_count,
            })
    except Exception as e:
        print(f'[Telegram] _get_messages error: {e}')
    return results


async def _send_message(recipient_name: str, message: str) -> tuple[bool, str]:
    if not _client: return False, "Client not initialized"
    try:
        try:
            entity = await _client.get_entity(recipient_name)
            await _client.send_message(entity, message)
            return True, f'Sent to {recipient_name}.'
        except:
            async for dialog in _client.iter_dialogs(limit=50):
                if recipient_name.lower() in _get_name(dialog.entity).lower():
                    await _client.send_message(dialog.entity, message)
                    return True, f'Sent to {_get_name(dialog.entity)}.'
            return False, f'Could not find contact: {recipient_name}'
    except Exception as e:
        return False, f'Send error: {str(e)}'


async def _start_listener():
    if _client is None: return
    @_client.on(events.NewMessage(incoming=True))
    async def handler(event):
        if _notification_callback:
            sender = await event.get_sender()
            _notification_callback(_get_name(sender), event.raw_text)
    print('[Telegram] Listener started.')
    await _client.run_until_disconnected()


def _run_async(coro):
    if _loop is None:
        raise RuntimeError('Telegram loop not started.')
    return asyncio.run_coroutine_threadsafe(coro, _loop).result(timeout=20)


def telegram_get_messages(count: int = 5) -> list[dict]:
    if not _client or not _loop: return []
    return _run_async(_get_messages(count))


def telegram_send_message(recipient: str, message: str) -> tuple[bool, str]:
    if not _client or not _loop: return False, 'Telegram not connected.'
    return _run_async(_send_message(recipient, message))


def telegram_get_latest() -> dict | None:
    msgs = telegram_get_messages(1)
    return msgs[0] if msgs else None


def telegram_is_authorized() -> bool:
    if not _client or not _loop: return False
    try:
        return _run_async(_client.is_user_authorized())
    except:
        return False

def telegram_status() -> str:
    """Returns 'ready', 'unauthorized', 'connecting', or 'disconnected'."""
    if not _client or not _loop: return 'disconnected'
    try:
        if not _client.is_connected(): return 'connecting'
        if not _run_async(_client.is_user_authorized()): return 'unauthorized'
        return 'ready'
    except:
        return 'disconnected'

def telegram_is_ready() -> bool:
    return telegram_status() == 'ready'


def set_notification_callback(callback):
    global _notification_callback
    _notification_callback = callback


def start_telegram_in_thread(email: str = None):
    global _loop, _client
    if _client and _client.is_connected() and _current_session_user == email:
        return
    def run():
        global _loop
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
        _loop.run_until_complete(_init_client(email))
        if _client and _client.is_connected():
            _loop.run_until_complete(_start_listener())
    threading.Thread(target=run, daemon=True).start()
    print(f'[Telegram] Background thread started for {email}.')


__all__ = [
    'start_telegram_in_thread',
    'telegram_get_messages',
    'telegram_send_message',
    'telegram_get_latest',
    'telegram_is_authorized',
    'telegram_is_ready',
    'telegram_status',
    'set_notification_callback',
]
