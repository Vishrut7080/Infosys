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
_loops                  = {}   # email -> asyncio.AbstractEventLoop
_state_lock             = threading.Lock()
_starting: set[str]     = set()  # emails currently being initialized

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


def _safe_remove_with_retry(path: str, max_retries: int = 3) -> bool:
    """
    Safely remove a file with exponential backoff retry logic.
    Returns True if file was removed or didn't exist, False if removal failed.
    """
    import time
    if not os.path.exists(path):
        return True
    
    for attempt in range(max_retries):
        try:
            os.remove(path)
            logger.debug(f'[Telegram] Removed file: {path}')
            return True
        except (PermissionError, OSError) as e:
            # On Windows, WindowsError is a subclass of OSError, so we catch both
            if attempt == max_retries - 1:
                logger.warning(f'[Telegram] Failed to remove {path} after {max_retries} attempts: {e}')
                return False
            # Exponential backoff: 0.5s, 1s, 2s
            sleep_time = 0.5 * (2 ** attempt)
            logger.debug(f'[Telegram] File {path} locked, retrying in {sleep_time}s (attempt {attempt + 1}/{max_retries})')
            time.sleep(sleep_time)
        except Exception as e:
            logger.warning(f'[Telegram] Unexpected error removing {path}: {e}')
            return False
    return False


def cleanup_stale_session_files():
    """
    Clean up session files that are older than 7 days.
    Called on server startup to prevent accumulation of stale files.
    """
    import time
    session_dir = os.path.dirname(os.path.abspath(__file__))
    current_time = time.time()
    max_age_seconds = 7 * 24 * 3600  # 7 days
    
    cleaned_count = 0
    for filename in os.listdir(session_dir):
        if filename.startswith('session_') and filename.endswith('.session'):
            filepath = os.path.join(session_dir, filename)
            try:
                file_age = current_time - os.path.getmtime(filepath)
                if file_age > max_age_seconds:
                    if _safe_remove_with_retry(filepath):
                        logger.info(f'[Telegram] Cleaned up stale session file: {filename} (age: {file_age/3600:.1f} hours)')
                        cleaned_count += 1
            except Exception as e:
                logger.debug(f'[Telegram] Could not check/clean {filename}: {e}')
    
    if cleaned_count > 0:
        logger.info(f'[Telegram] Cleaned up {cleaned_count} stale session files')
    return cleaned_count


def delete_all_session_files(max_age_hours: int = 1):
    """
    Delete session files older than max_age_hours for clean break after updates.
    Forces users to re-authenticate with Telegram.
    Called on server startup for major updates.
    """
    import time
    session_dir = os.path.dirname(os.path.abspath(__file__))
    current_time = time.time()
    max_age_seconds = max_age_hours * 3600
    deleted_count = 0
    
    for filename in os.listdir(session_dir):
        if filename.startswith('session_') and filename.endswith('.session'):
            filepath = os.path.join(session_dir, filename)
            try:
                file_age = current_time - os.path.getmtime(filepath)
                if file_age > max_age_seconds:
                    if _safe_remove_with_retry(filepath):
                        logger.info(f'[Telegram] Deleted old session file for clean break: {filename} (age: {file_age/3600:.1f} hours)')
                        deleted_count += 1
                else:
                    logger.debug(f'[Telegram] Keeping recent session file: {filename} (age: {file_age/3600:.1f} hours)')
            except Exception as e:
                logger.warning(f'[Telegram] Could not delete {filename}: {e}')
    
    # Also delete any lock/journal files (they are always stale)
    for ext in ('.session.lock', '.session-journal', '.lock', '-journal'):
        for filename in os.listdir(session_dir):
            if filename.startswith('session_') and filename.endswith(ext):
                filepath = os.path.join(session_dir, filename)
                try:
                    if _safe_remove_with_retry(filepath):
                        logger.debug(f'[Telegram] Deleted associated file: {filename}')
                except Exception as e:
                    logger.debug(f'[Telegram] Could not delete {filename}: {e}')
    
    if deleted_count > 0:
        logger.info(f'[Telegram] Clean break: deleted {deleted_count} old session files. Users will need to re-authenticate.')
    return deleted_count


async def _init_client(email: str, loop=None):
    max_retries = 3
    for attempt in range(max_retries):
        try:
            creds = database.get_user_credentials(email) or {}
            api_id_str = (creds.get('tg_api_id') or '').strip() or '0'
            api_hash = (creds.get('tg_api_hash') or '').strip()

            if not api_id_str or api_id_str == '0' or not api_hash:
                logger.error(f'[Telegram] API credentials not found for {email}.')
                return None

            api_id = int(api_id_str)
            session_path = _get_session_path(email)

            # Clean up ALL stale lock/journal files before connecting with retry logic
            for ext in ('.session.lock', '.session-journal', '.lock', '-journal'):
                p = session_path + ext
                if os.path.exists(p):
                    success = _safe_remove_with_retry(p, max_retries=3)
                    if not success:
                        logger.warning(f'[Telegram] Could not remove {p} after retries, may cause connection issues')
                    else:
                        logger.debug(f'[Telegram] Removed stale file: {p}')

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
            if "database is locked" in str(e).lower() and attempt < max_retries - 1:
                logger.warning(f'[Telegram] Database locked for {email}, retrying in 2s...')
                await asyncio.sleep(2)
                continue
            logger.error(f'[Telegram] Init error for {email}: {e}')
            raise TelegramError(f"Failed to initialize Telegram: {e}")
    return None


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
        
        # Log incoming message to activity (removed live TTS announcement)
        from app.database import database
        database.log_activity(email, 'telegram_received', f"From {sender_name}")
            
    logger.info(f'[Telegram] Listener started for {email}.')
    await client.run_until_disconnected() # This is correct for Telethon


def _run_async(email, coro):
    loop = _loops.get(email)
    if loop is None or not isinstance(loop, asyncio.AbstractEventLoop):
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
    
    # Avoid starting multiple threads for the same email — never sleep under lock
    with _state_lock:
        if email in _starting:
            logger.debug(f'[Telegram] Already starting for {email}')
            return
        loop_val = _loops.get(email)
        if isinstance(loop_val, asyncio.AbstractEventLoop) and loop_val.is_running():
            logger.debug(f'[Telegram] Loop already running for {email}')
            return
        _starting.add(email)

    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        with _state_lock:
            _loops[email] = loop
            _starting.discard(email)
        
        async def main_task():
            logger.info(f'[Telegram] Main task starting for {email}')
            try:
                client = await _init_client(email, loop=loop)
                if not client:
                    logger.warning(f'[Telegram] Client initialization failed for {email} (check API credentials)')
                    loop.stop()
                    return

                _clients[email] = client
                
                async def run_client(c, retries=0):
                    try:
                        if c.is_connected():
                            # Register listener regardless of auth state
                            @c.on(events.NewMessage(incoming=True))
                            async def handler(event):
                                try:
                                    if not await c.is_user_authorized():
                                        return
                                    sender = await event.get_sender()
                                    sender_name = _get_name(sender)
                                    text = event.raw_text
                                    # Log incoming message (removed live TTS announcement)
                                    from app.database import database
                                    database.log_activity(email, 'telegram_received', f"From {sender_name}")
                                except Exception as e:
                                    logger.error(f"[Telegram] Event handler error: {e}")

                            is_auth = await c.is_user_authorized()
                            logger.info(f'[Telegram] Client connected for {email}. Authorized: {is_auth}')
                            
                            if is_auth:
                                await c.run_until_disconnected()
                            else:
                                logger.info(f'[Telegram] Waiting for authorization for {email}...')
                                # Polling for authorization state. 
                                # This avoids GetStateRequest failures on some unauthorized sessions.
                                while c.is_connected() and not await c.is_user_authorized():
                                    await asyncio.sleep(5)
                                
                                if c.is_connected():
                                    logger.info(f'[Telegram] {email} authorized! Starting listener.')
                                    await c.run_until_disconnected()

                    except (AuthKeyUnregisteredError, Exception) as e:
                        is_unregistered = isinstance(e, AuthKeyUnregisteredError) or 'AuthRestartError' in str(e)
                        
                        if is_unregistered:
                            logger.warning(f'[Telegram] Session invalid for {email}: {e}')
                        else:
                            logger.error(f'[Telegram] Client error for {email}: {e}')

                        # Best-effort cleanup
                        try:
                            await c.disconnect()
                        except Exception:
                            pass
                        
                        # Retry logic: try multiple times before giving up
                        if retries < 2:
                            logger.info(f'[Telegram] Retrying connection for {email} (attempt {retries + 1}/3)')
                            await asyncio.sleep(2)  # Brief delay before retry
                            
                            try:
                                # Try with fresh client (without deleting session file first)
                                new_client = await _init_client(email, loop=loop)
                                if new_client:
                                    _clients[email] = new_client
                                    await run_client(new_client, retries + 1)
                                    return  # Successfully reconnected, exit this handler
                            except Exception as e2:
                                logger.warning(f'[Telegram] Retry {retries + 1} failed for {email}: {e2}')
                        
                        # All retries exhausted - only now delete session and notify user
                        if is_unregistered:
                            logger.warning(f'[Telegram] All retries exhausted for {email} — clearing session')
                            session_path = _get_session_path(email)
                            for ext in ('', '.session', '.session-journal', '.session.lock'):
                                p = session_path + ext
                                try:
                                    if os.path.exists(p):
                                        os.remove(p)
                                        logger.info(f'[Telegram] Removed session file {p}')
                                except Exception as ex:
                                    logger.debug(f'[Telegram] Could not remove session file {p}: {ex}')

                            # Notify the frontend
                            try:
                                from app.web import socketio
                                socketio.emit('toast', {
                                    'message': f'⚠️ Telegram needs re-authorization for {email}',
                                    'type': 'warning',
                                    'duration': 8000,
                                    'link': {'url': '/telegram-auth', 'text': 'Re-authorize'}
                                })
                            except Exception:
                                pass
                        
                        logger.error(f'[Telegram] Giving up for {email} after {retries + 1} attempts')
                        loop.stop()
                
                await run_client(client)
            except (asyncio.CancelledError, GeneratorExit):
                logger.debug(f'[Telegram] Background task exiting for {email}')
            except Exception as e:
                logger.error(f'[Telegram] Main task error for {email}: {e}')
                loop.stop()
                
        loop.create_task(main_task())
        try:
            loop.run_forever()
        finally:
            # Cleanup on exit
            try:
                # Disconnect client first if still there
                if email in _clients:
                    c = _clients[email]
                    if c.is_connected():
                        loop.run_until_complete(c.disconnect())
            except:
                pass

            try:
                tasks = [t for t in asyncio.all_tasks(loop) if not t.done()]
                for t in tasks: t.cancel()
                # Give tasks a moment to cancel
                if tasks:
                    loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
            except:
                pass
            
            with _state_lock:
                _loops.pop(email, None)
                _clients.pop(email, None)
                _starting.discard(email)            
            loop.close()
                
    threading.Thread(target=run, daemon=True).start()
    logger.info(f'[Telegram] Background thread started for {email}.')

def stop_telegram_in_thread(email: str):
    """Signals the Telegram background thread to stop."""
    if not email: return
    with _state_lock:
        # Don't pop yet, let the thread's finally block do it
        client = _clients.get(email)
        loop = _loops.get(email)

    if client:
        try:
            if loop and hasattr(loop, 'is_running') and loop.is_running():
                asyncio.run_coroutine_threadsafe(client.disconnect(), loop)
        except Exception as e:
            logger.error(f"[Telegram] Error disconnecting client for {email}: {e}")

    if loop and hasattr(loop, 'call_soon_threadsafe'):
        try:
            loop.call_soon_threadsafe(loop.stop)
            logger.info(f"[Telegram] Signaled telegram thread to stop for {email}")
        except Exception as e:
            logger.error(f"[Telegram] Error stopping loop for {email}: {e}")

__all__ = [
    'start_telegram_in_thread',
    'stop_telegram_in_thread',
    'telegram_get_messages',
    'telegram_send_message',
    'telegram_get_latest',
    'telegram_is_authorized',
    'telegram_is_ready',
    'telegram_status',
    'cleanup_stale_session_files',
    'delete_all_session_files',
]
