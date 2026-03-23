# ========================
# Telegram/telegram.py
# ========================
import os
import asyncio
import threading
import concurrent.futures
from datetime import datetime

from telethon import TelegramClient, events
from telethon.tl.types import User, Chat, Channel
from telethon.errors.rpcerrorlist import AuthKeyUnregisteredError

from app.core.logging import logger
from app.core.errors import TelegramError
from app.core.config import settings
from app.database import database

# ----------------------
# Global state
# ----------------------
_clients                = {}   # email -> TelegramClient
_loops                  = {}   # email -> EventLoop

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


async def _init_client(email: str, loop=None):
    try:
        # Load per-user Telegram credentials from the database (do not rely on process env for per-user secrets)
        creds = database.get_user_credentials(email) or {}
        api_id_str = (creds.get('tg_api_id') or '').strip() or '0'
        api_hash = (creds.get('tg_api_hash') or '').strip()

        if not api_id_str or api_id_str == '0' or not api_hash:
            logger.error(f'[Telegram] API credentials not found for {email}.')
            return None

        api_id = int(api_id_str)
        session_path = _get_session_path(email)
        
        logger.info(f'[Telegram] Initializing client for {email} with API ID: {api_id}')
        
        client = TelegramClient(
            session_path, api_id, api_hash,
            device_model="Desktop", system_version="Windows 10",
            app_version="1.0", lang_code="en", system_lang_code="en",
            request_retries=1,
            connection_retries=3,
            retry_delay=2,
            loop=loop
        )
        
        await client.connect()
        logger.info(f'[Telegram] Connected to Telegram for {email}.')

        return client
    except Exception as e:
        logger.error(f'[Telegram] Init error for {email}: {e}')
        raise TelegramError(f"Failed to initialize Telegram: {e}")


async def _get_messages(client, count: int = 5) -> list[dict]:
    results = []
    if not client: return results
    try:
        async for dialog in client.iter_dialogs(limit=count):
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
        logger.error(f'[Telegram] _get_messages error: {e}')
    return results


async def _send_message(client, recipient_name: str, message: str) -> tuple[bool, str]:
    if not client: return False, "Client not initialized"
    try:
        try:
            entity = await client.get_entity(recipient_name)
            await client.send_message(entity, message)
            return True, f'Sent to {recipient_name}.'
        except:
            async for dialog in client.iter_dialogs(limit=50):
                if recipient_name.lower() in _get_name(dialog.entity).lower():
                    await client.send_message(dialog.entity, message)
                    return True, f'Sent to {_get_name(dialog.entity)}.'
            return False, f'Could not find contact: {recipient_name}'
    except Exception as e:
        return False, f'Send error: {str(e)}'


async def _start_listener(email: str, client: TelegramClient):
    if client is None: return
    
    @client.on(events.NewMessage(incoming=True))
    async def handler(event):
        sender = await event.get_sender()
        sender_name = _get_name(sender)
        text = event.raw_text
        
        # Emit notification directly via socketio
        from app.web import socketio
        socketio.emit('tts', {'text': f"New Telegram from {sender_name}: {text}", 'lang': 'en'})
        from app.database import database
        database.log_activity(email, 'telegram_received', f"From {sender_name}")
            
    logger.info(f'[Telegram] Listener started for {email}.')
    await client.run_until_disconnected() # This is correct for Telethon


def _run_async(email, coro):
    loop = _loops.get(email)
    if loop is None:
        # If the loop is not initialized, we cannot run the coroutine safely
        # because the client object is tied to that specific loop.
        raise TelegramError(f'Telegram loop not started for {email}. User might need to re-login.')

    # If the background loop exists but isn't running, we cannot execute tasks on it.
    try:
        is_running = loop.is_running()
    except Exception:
        is_running = False

    if not is_running:
        raise TelegramError(f'Telegram background service is not running for {email}.')

    try:
        return asyncio.run_coroutine_threadsafe(coro, loop).result(timeout=20)
    except concurrent.futures.TimeoutError:
        logger.error(f'[Telegram] run_coroutine_threadsafe timed out for {email}')
        raise TelegramError('Telegram operation timed out.')
    except Exception as e:
        logger.error(f'[Telegram] _run_async error for {email}: {e}')
        raise


from typing import Optional

def telegram_get_messages(count: int = 5, email: Optional[str] = None) -> list[dict]:
    if not email: return []
    client = _clients.get(email)
    if not client or email not in _loops: return []
    return _run_async(email, _get_messages(client, count))


def telegram_get_conversation(contact: str, count: int = 10, email: Optional[str] = None) -> list[dict]:
    """Fetch conversation history with a specific contact (real Telegram)."""
    if not email: return []
    client = _clients.get(email)
    if not client or email not in _loops: return []

    async def _fetch():
        messages = []
        async for msg in client.iter_messages(contact, limit=count):
            sender = 'You' if msg.out else (getattr(msg.sender, 'first_name', None) or contact)
            messages.append({'sender': sender, 'text': msg.text or '', 'date': str(msg.date)})
        return list(reversed(messages))

    return _run_async(email, _fetch())


def telegram_send_message(recipient: str, message: str, email: Optional[str] = None) -> tuple[bool, str]:
    if not email: return False, 'No email provided.'
    client = _clients.get(email)
    if not client or email not in _loops: return False, 'Telegram not connected.'
    return _run_async(email, _send_message(client, recipient, message))


def telegram_get_latest(email: Optional[str] = None) -> dict | None:
    if not email: return None
    msgs = telegram_get_messages(1, email=email)
    return msgs[0] if msgs else None


def telegram_is_authorized(email: Optional[str] = None) -> bool:
    if not email: return False
    client = _clients.get(email)
    if not client or email not in _loops: return False
    try:
        return _run_async(email, client.is_user_authorized())
    except:
        return False

def telegram_status(email: Optional[str] = None) -> str:
    """Returns 'ready', 'unauthorized', 'connecting', or 'disconnected'."""
    if not email: return 'disconnected'
    client = _clients.get(email)
    if not client or email not in _loops: return 'disconnected'
    try:
        if not client.is_connected(): return 'connecting'
        if not _run_async(email, client.is_user_authorized()): return 'unauthorized'
        return 'ready'
    except:
        return 'disconnected'

def telegram_is_ready(email: Optional[str] = None) -> bool:
    return telegram_status(email) == 'ready'


def start_telegram_in_thread(email: str):
    if not email: return
    
    if email in _clients and _clients[email].is_connected():
        return
        
    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        _loops[email] = loop
        
        client = loop.run_until_complete(_init_client(email, loop=loop))
        if not client:
            return

        _clients[email] = client
        try:
            if client.is_connected():
                loop.run_until_complete(_start_listener(email, client))
        except AuthKeyUnregisteredError as e:
            logger.warning(f'[Telegram] AuthKeyUnregistered for {email}: {e} — clearing session and retrying')
            # Best-effort cleanup of local session files so the user can re-authorize
            try:
                loop.run_until_complete(client.disconnect())
            except Exception:
                pass
            session_path = _get_session_path(email)
            for ext in ('', '.session', '.session-journal', '.session.lock'):
                p = session_path + ext
                try:
                    if os.path.exists(p):
                        os.remove(p)
                        logger.info(f'[Telegram] Removed session file {p}')
                except Exception:
                    logger.debug(f'[Telegram] Could not remove session file {p}')

            # Notify the frontend so the user can re-authorize Telegram
            try:
                from app.web import socketio
                socketio.emit('toast', {'message': f'⚠️ Telegram needs re-authorization for {email}', 'type': 'warning', 'duration': 8000})
            except Exception:
                logger.debug('[Telegram] Could not emit re-authorization toast')

            # Try once more to initialize a fresh client (will require user to re-auth)
            try:
                client = loop.run_until_complete(_init_client(email))
                if client:
                    _clients[email] = client
                    if client.is_connected():
                        loop.run_until_complete(_start_listener(email, client))
            except Exception as e2:
                logger.error(f'[Telegram] Retry init failed for {email}: {e2}')
        except Exception as e:
            logger.error(f'[Telegram] Listener error for {email}: {e}')
                
    threading.Thread(target=run, daemon=True).start()
    logger.info(f'[Telegram] Background thread started for {email}.')


__all__ = [
    'start_telegram_in_thread',
    'telegram_get_messages',
    'telegram_send_message',
    'telegram_get_latest',
    'telegram_is_authorized',
    'telegram_is_ready',
    'telegram_status',
]
