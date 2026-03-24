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
_startup_lock           = threading.Lock()

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
    
    # Avoid starting multiple threads for the same email
    with _startup_lock:
        if email in _loops:
            try:
                if _loops[email].is_running():
                    logger.debug(f'[Telegram] Loop already running for {email}')
                    return
            except Exception:
                pass

    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        with _startup_lock:
            _loops[email] = loop
        
        async def main_task():
            logger.info(f'[Telegram] Main task starting for {email}')
            try:
                client = await _init_client(email, loop=loop)
                if not client:
                    logger.warning(f'[Telegram] Client initialization failed for {email} (check API credentials)')
                    return

                _clients[email] = client
                
                try:
                    if client.is_connected():
                        is_auth = await client.is_user_authorized()
                        logger.info(f'[Telegram] Client connected for {email}. Authorized: {is_auth}')
                        
                        if is_auth:
                            await _start_listener(email, client)
                        else:
                            logger.info(f'[Telegram] User {email} not authorized. Waiting for auth...')
                            # Even if not authorized, we keep the client in _clients so 
                            # the web routes can trigger sign_in / send_code
                except AuthKeyUnregisteredError as e:
                    logger.warning(f'[Telegram] AuthKeyUnregistered for {email}: {e} — clearing session and retrying')
                    # Best-effort cleanup of local session files so the user can re-authorize
                    try:
                        await client.disconnect()
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
                        socketio.emit('toast', {
                            'message': f'⚠️ Telegram needs re-authorization for {email}',
                            'type': 'warning',
                            'duration': 8000,
                            'link': {'url': '/telegram-auth', 'text': 'Re-authorize'}
                        })
                    except Exception:
                        logger.debug('[Telegram] Could not emit re-authorization toast')

                    try:
                        client = await _init_client(email, loop=loop)
                        if client:
                            _clients[email] = client
                            if client.is_connected():
                                await _start_listener(email, client)
                    except AuthKeyUnregisteredError:
                        logger.error(f'[Telegram] AuthKeyUnregistered again for {email} after cleanup.')
                        # Remove session file again just in case
                        session_path = _get_session_path(email)
                        for ext in ('.session', '.session-journal', '.session.lock'):
                            p = session_path + ext
                            if os.path.exists(p): os.remove(p)
                    except Exception as e2:
                        logger.error(f'[Telegram] Retry init failed for {email}: {e2}')
                except (asyncio.CancelledError, GeneratorExit):
                    raise
                except Exception as e:
                    logger.error(f'[Telegram] Listener error for {email}: {e}')
            except (asyncio.CancelledError, GeneratorExit):
                logger.debug(f'[Telegram] Background task exiting for {email}')
            except Exception as e:
                logger.error(f'[Telegram] Main task error for {email}: {e}')
                
        loop.create_task(main_task())
        try:
            loop.run_forever()
        finally:
            # Cleanup on exit
            try:
                tasks = asyncio.all_tasks(loop)
                for t in tasks: t.cancel()
                # Give tasks a moment to cancel
                if tasks:
                    loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
            except:
                pass
            loop.close()
            with _startup_lock:
                _loops.pop(email, None)
                _clients.pop(email, None)
                
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
