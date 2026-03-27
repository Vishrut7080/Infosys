from flask import Blueprint, render_template, request, jsonify, session
from app.database import database
from app.web import socketio
from app.core.logging import logger
from app.web.utils import login_required
from app.core.config import settings
from datetime import datetime
import re

# Maps tool names to (toast_type, message) for real-time UI feedback
TOOL_TOASTS: dict[str, tuple[str, str]] = {
    'verify_gmail_pin':          ('warning', '🔐 Verifying Gmail access…'),
    'send_email':                ('success', '📧 Email sent'),
    'get_emails':                ('info',    '📬 Emails fetched'),
    'search_emails':             ('info',    '🔍 Emails searched'),
    'get_email_overview':        ('info',    '📊 Email overview ready'),
    'get_important_emails':      ('info',    '⭐ Important emails loaded'),
    'get_email_body':            ('info',    '📄 Email loaded'),
    'verify_telegram_pin':       ('warning', '🔐 Verifying Telegram…'),
    'send_telegram':             ('success', '✈️ Telegram sent'),
    'get_telegram_messages':     ('info',    '📨 Telegram fetched'),
    'get_telegram_conversation': ('info',    '💬 Conversation loaded'),
    'add_task':                  ('success', '✅ Task added'),
    'list_tasks':                ('info',    '📋 Tasks loaded'),
    'complete_task':             ('success', '☑ Task completed'),
    'delete_task':               ('info',    '🗑 Task deleted'),
    'navigate':                  ('info',    '🧭 Navigating…'),
    'get_time':                  ('info',    '🕐 Time fetched'),
    'get_date':                  ('info',    '📅 Date fetched'),
    'get_datetime':              ('info',    '🗓 Date & time ready'),
    'get_system_info':           ('info',    '💻 System info'),
    'random_number':             ('info',    '🎲 Random number'),
    'calculate':                 ('info',    '🔢 Calculated'),
    'get_user_profile':          ('info',    '👤 Profile loaded'),
    'set_reminder':              ('success', '⏰ Reminder set'),
    'tell_joke':                 ('success', '😄 Here comes a joke!'),
    'switch_language':           ('success', '🔤 Language updated'),
}

from app.services.mocks.mock_agent import MockAgent
if not settings.mock_llm:
    from app.agent.core import OpenRouterAgent, GroqAgent, LLMUnavailableError
import concurrent.futures

# Executor for running agent.chat with a timeout to avoid blocking request threads
_agent_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)

assistant_bp = Blueprint('assistant', __name__)

agents = {}


def get_agent(email: str):
    if email not in agents:
        if settings.mock_llm:
            agents[email] = MockAgent(email)
        elif settings.GROQ_API_KEY:
            agents[email] = GroqAgent(settings.GROQ_API_KEY, email)
            logger.info(f"Using GroqAgent for {email} (model={settings.GROQ_MODEL})")
        else:
            agents[email] = OpenRouterAgent(settings.OPEN_ROUTER_API_key, email)
            logger.info(f"Using OpenRouterAgent for {email} (model={settings.OPENROUTER_MODEL})")
    return agents[email]

@assistant_bp.route('/dashboard')
@login_required
def dashboard():
    from app.services.telegram import telegram_is_ready, start_telegram_in_thread
    email = session.get('user', {}).get('email')
    creds = database.get_user_credentials(email) if email else None
    
    # Auto-start telegram if credentials present but not running
    if creds and creds.get('tg_api_id') and not telegram_is_ready(email):
        start_telegram_in_thread(email)

    has_gmail = bool(creds and creds.get('gmail_token'))
    has_telegram = telegram_is_ready(email)
    return render_template('dashboard.html', user=session['user'], has_gmail=has_gmail, has_telegram=has_telegram)

@assistant_bp.route('/api/chat', methods=['POST'])
@login_required
def api_chat():
    data = request.get_json()
    text = data.get('text', '')
    lang_hint = data.get('lang', '')
    email = session.get('user', {}).get('email')
    
    if not email:
        return jsonify({'error': 'Not logged in'})
    
    if not session.get('voice_auth'):
        from app.services.auth import auth_service
        matched, name, _ = auth_service.verify_audio_password(text)
        if matched:
            session['voice_auth'] = True
            database.log_activity(email, 'login', 'voice')
            creds = database.get_user_credentials(email)
            if creds and creds.get('tg_api_id'):
                if settings.mock_telegram:
                    from app.services.mocks.mock_telegram import start_telegram_in_thread
                else:
                    from app.services.telegram import start_telegram_in_thread
                start_telegram_in_thread(email)
            return jsonify({'response': f'Welcome back, {name}. How can I help you?', 'lang': 'en'})
        return jsonify({'response': 'Audio password not recognized. Please try again.', 'lang': 'en'})

    import time as _time

    # ── Tier 1: real LLM ─────────────────────────────────────────────────
    active_agent = get_agent(email)
    timeout_val = getattr(settings, 'OPENROUTER_TIMEOUT', None)
    logger.info(f"Submitting agent.chat for user={email} with timeout={timeout_val}")
    start_exec = _time.monotonic()
    future = _agent_executor.submit(active_agent.chat, text, lang_hint)
    try:
        response = future.result(timeout=timeout_val)
        logger.info(f"agent.chat completed in {_time.monotonic() - start_exec:.2f}s for user={email}")
    except (concurrent.futures.TimeoutError, Exception) as e:
        elapsed = _time.monotonic() - start_exec
        future.cancel()
        if isinstance(e, concurrent.futures.TimeoutError):
            logger.warning(f"LLM timed out after {elapsed:.2f}s for user={email}")
        else:
            logger.warning(f"LLM failed after {elapsed:.2f}s for user={email}: {e}")
        # ── Tier 2: offline fallback ──────────────────────────────────────
        socketio.emit('toast', {'message': '⚠️ AI unavailable — using offline mode', 'type': 'warning'})
        fallback = MockAgent(email)
        active_agent = fallback
        response = fallback.chat(text, lang_hint)
    database.log_activity(email, 'voice_command', response[:200])

    # Determine which services were involved and if navigation was requested
    nav_url = None
    services_used = set()
    for tr in active_agent.last_tool_results:
        tool_name = tr.get('tool', '')
        result = tr.get('result', '')
        if tool_name == 'navigate' and result.startswith('NAVIGATE:'):
            nav_url = result.split('NAVIGATE:', 1)[1].strip()
        if tool_name in ('send_email', 'get_emails', 'search_emails', 'verify_gmail_pin'):
            services_used.add('gmail')
        if tool_name in ('send_telegram', 'get_telegram_messages', 'verify_telegram_pin'):
            services_used.add('telegram')

    # Detect language (simple heuristic: Devanagari characters => Hindi)
    lang = 'hi' if re.search(r'[\u0900-\u097F]', response) else 'en'
    socketio.emit('feed_update', {'text': response, 'time': datetime.now().strftime('%H:%M:%S'), 'lang': lang}, room=email)

    # Emit a toast for each tool that was called
    for tr in active_agent.last_tool_results:
        tool_name = tr.get('tool', '')
        if tool_name in TOOL_TOASTS:
            toast_type, toast_msg = TOOL_TOASTS[tool_name]
            socketio.emit('toast', {'message': toast_msg, 'type': toast_type}, room=email)

    result = {'response': response, 'lang': lang}
    # Include raw LLM response for debugging if available
    try:
        if hasattr(active_agent, 'last_raw_response') and active_agent.last_raw_response:
            result['raw_llm'] = active_agent.last_raw_response
    except Exception:
        pass
    if nav_url:
        result['navigate'] = nav_url
    if services_used:
        result['services'] = list(services_used)
    return jsonify(result)


@assistant_bp.route('/get-inbox')
@login_required
def get_inbox():
    email = session.get('user', {}).get('email')
    if not email: return jsonify({'messages': []})
    
    messages = []
    creds = database.get_user_credentials(email)
    if not creds:
        return jsonify({'messages': []})

    # Check Gmail credentials
    if creds.get('gmail_token'):
        try:
            if settings.mock_email:
                from app.services.mocks.mock_email import MockEmailService as EmailService
            else:
                from app.services.email import EmailService
            service = EmailService(creds['gmail_token'])
            for e in service.get_emails(count=5):
                if isinstance(e, dict) and 'error' not in e:
                    messages.append({
                        'source': 'gmail', 'from': e.get('sender', 'Unknown'), 'to': 'Me', 
                        'text': f"{e.get('subject', 'No Subject')} — {e.get('summary', '')}", 
                        'dir': 'Incoming', 'time': e.get('date', '')
                    })
        except Exception as e:
            print(f"[Assistant] Gmail error: {e}")

    # Check Telegram credentials
    if creds.get('tg_api_id') and creds.get('tg_api_hash'):
        try:
            if settings.mock_telegram:
                from app.services.mocks.mock_telegram import telegram_get_messages
            else:
                from app.services.telegram import telegram_get_messages
            for m in telegram_get_messages(5, email=email):
                if isinstance(m, dict):
                    messages.append({
                        'source': 'telegram', 'from': m.get('name', 'Unknown'), 'to': 'Me', 
                        'text': m.get('message', ''), 
                        'dir': f"{m.get('unread')} unread" if m.get('unread') else 'Incoming', 
                        'time': m.get('date', '')
                    })
        except Exception as e:
            print(f"[Assistant] Telegram error: {e}")
            
    messages.sort(key=lambda x: x.get('time', ''), reverse=True)
    return jsonify({'messages': messages})

@assistant_bp.route('/suggest-audio')
def suggest_audio():
    return jsonify({'word': database.suggest_audio_word()})

@assistant_bp.route('/log-activity', methods=['POST'])
def log_activity():
    email = session.get('user', {}).get('email')
    if not email: return '', 204
    data = request.get_json()
    if data.get('action'): 
        database.log_activity(email, data['action'], data.get('detail', ''))
    return '', 204

@assistant_bp.route('/translate', methods=['POST'])
def translate_text():
    try:
        from deep_translator import GoogleTranslator
        data = request.get_json()
        texts, target = data.get('texts', []), data.get('target', 'en')
        if target == 'en': return jsonify({'translated': texts})
        translated = []
        for text in texts:
            try:
                result = GoogleTranslator(source='auto', target=target).translate(text)
                translated.append(result if result else text)
            except: translated.append(text)
        return jsonify({'translated': translated})
    except ImportError:
        return jsonify({'translated': request.get_json().get('texts', [])})

@assistant_bp.route('/telegram/contacts')
@login_required
def telegram_contacts():
    email = session['user'].get('email')
    if settings.mock_telegram:
        # Return canned contacts in mock mode
        from app.services.mocks.mock_telegram import MockTelegramState
        if email not in MockTelegramState._connected_emails:
            return jsonify({'contacts': []})
        return jsonify({'contacts': [
            {'name': 'Mock-Alice', 'unread': 1, 'last_message': 'Hey there!', 'date': '18 Mar 10:00'},
            {'name': 'Mock-Bob', 'unread': 0, 'last_message': 'See you later', 'date': '18 Mar 09:30'},
        ]})
    try:
        from app.services.telegram import _run_async, _clients, _loops, _get_name
        if email not in _loops or email not in _clients: return jsonify({'contacts': []})
        client = _clients[email]
        async def _get_contacts():
            contacts = []
            async for dialog in client.iter_dialogs(limit=20):
                contacts.append({'name': _get_name(dialog.entity), 'unread': dialog.unread_count, 'last_message': dialog.message.message[:50] if dialog.message and dialog.message.message else '', 'date': dialog.message.date.strftime("%d %b %H:%M") if dialog.message and dialog.message.date else ''})
            return contacts
        return jsonify({'contacts': _run_async(email, _get_contacts())})
    except: return jsonify({'contacts': []})

@assistant_bp.route('/update-profile-name', methods=['POST'])
@login_required
def update_profile_name():
    email = session['user'].get('email')
    new_name = request.get_json().get('name', '').strip()
    ok, msg = database.update_name(email, new_name)
    if ok: session['user']['name'] = new_name
    return jsonify({'status': 'success' if ok else 'error', 'message': msg})

@assistant_bp.route('/update-profile-password', methods=['POST'])
@login_required
def update_profile_password():
    email = session['user'].get('email')
    data = request.get_json()
    ok, msg = database.update_password(email, data.get('old_password', ''), data.get('new_password', ''))
    return jsonify({'status': 'success' if ok else 'error', 'message': msg})

@assistant_bp.route('/update-profile-audio', methods=['POST'])
@login_required
def update_profile_audio():
    email = session['user'].get('email')
    ok, msg = database.update_audio(email, request.get_json().get('audio_password', '').strip())
    return jsonify({'status': 'success' if ok else 'error', 'message': msg})

@assistant_bp.route('/delete-profile-account', methods=['POST'])
@login_required
def delete_profile_account():
    email = session['user'].get('email')
    ok, msg = database.delete_user(email, request.get_json().get('password', ''))
    if ok:
        session.clear()
    return jsonify({'status': 'success' if ok else 'error', 'message': msg})

@assistant_bp.route('/telegram-auth')
@login_required
def telegram_auth_page():
    return render_template('telegram_auth.html')

@assistant_bp.route('/telegram/send-code', methods=['POST'])
@login_required
def telegram_send_code():
    from app.services.telegram import _clients, _loops, start_telegram_in_thread
    email = session['user'].get('email')
    if not email:
        return jsonify({'status': 'error', 'message': 'Not logged in'})

    # Start the client if it hasn't been initialized yet
    if email not in _clients:
        start_telegram_in_thread(email)
        import time
        for _ in range(10):
            time.sleep(0.5)
            if email in _clients:
                break

    if email not in _clients:
        return jsonify({'status': 'error', 'message': 'Telegram failed to initialize. Check your API ID and Hash.'})

    data = request.get_json()
    phone = data.get('phone', '').strip()
    if not phone:
        return jsonify({'status': 'error', 'message': 'Phone number is required.'})

    try:
        import asyncio

        client = _clients[email]
        loop = _loops[email]

        # Force reconnect if disconnected
        async def connect_and_send():
            if not client.is_connected():
                await client.connect()
                for _ in range(10):
                    if client.is_connected():
                        break
                    await asyncio.sleep(0.5)
            if not client.is_connected():
                raise ConnectionError("Failed to connect to Telegram")
            return await client.send_code_request(phone)

        asyncio.run_coroutine_threadsafe(
            connect_and_send(),
            loop
        ).result(timeout=20)

        session['telegram_phone'] = phone
        return jsonify({'status': 'ok'})
    except Exception as e:
        import traceback
        logger.error(f'[Telegram] send_code error for {email}: {e}')
        logger.error(traceback.format_exc())
        return jsonify({'status': 'error', 'message': f"{type(e).__name__}: {str(e)}"})

@assistant_bp.route('/telegram/verify-otp', methods=['POST'])
@login_required
def telegram_verify_otp():
    from app.services.telegram import _clients, _loops
    email = session['user'].get('email')
    if not email or email not in _clients: return jsonify({'status': 'error', 'message': 'Telegram not initialized'})
    data = request.get_json()
    phone = data.get('phone', session.get('telegram_phone', ''))
    otp = data.get('otp', '').strip()
    try:
        import asyncio
        asyncio.run_coroutine_threadsafe(_clients[email].sign_in(phone, otp), _loops[email]).result(timeout=15)
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@assistant_bp.route('/telegram/status')
@login_required
def telegram_status_route():
    from app.services.telegram import telegram_is_ready
    email = session['user'].get('email')
    return jsonify({'ready': telegram_is_ready(email)})

@assistant_bp.route('/voice-logout', methods=['POST'])
@login_required
def voice_logout():
    from app.web.routes.auth import logout_user
    email = session['user'].get('email')
    logout_user(email)
    return '', 204


@assistant_bp.route('/get-stats')
@login_required
def get_stats():
    email = session['user'].get('email')
    return jsonify({
        'emails': database.get_activity_count(email, 'email_read') + database.get_activity_count(email, 'email_sent'),
        'commands': database.get_activity_count(email, 'voice_command'),
        'sessions': database.get_activity_count(email, 'login'),
    })


@assistant_bp.route('/get-user-info')
@login_required
def get_user_info():
    email = session['user'].get('email')
    return jsonify({
        'name': session['user'].get('name', ''),
        'email': email,
        'is_admin': database.is_admin(email),
    })


@assistant_bp.route('/get-services')
@login_required
def get_services():
    email = session['user'].get('email')
    creds = database.get_user_credentials(email)
    services = []
    if creds and creds.get('gmail_token'):
        services.append('gmail')
    if creds and creds.get('tg_api_id') and creds.get('tg_api_hash'):
        services.append('telegram')
    return jsonify({'services': services})


@assistant_bp.route('/select-services', methods=['POST'])
@login_required
def select_services():
    # Services are auto-detected from user credentials
    return jsonify({'status': 'ok'})


@assistant_bp.route('/typing', methods=['POST'])
def typing():
    return '', 204


@assistant_bp.route('/signup-closed', methods=['POST'])
def signup_closed():
    return '', 204


# ── TASKS API ─────────────────────────────────────────────────────────────

@assistant_bp.route('/api/tasks', methods=['GET'])
@login_required
def api_list_tasks():
    email = session['user']['email']
    status = request.args.get('status', 'pending')
    tasks = database.list_tasks(email, status)
    return jsonify({'tasks': tasks})


@assistant_bp.route('/api/tasks', methods=['POST'])
@login_required
def api_add_task():
    email = session['user']['email']
    data = request.get_json()
    title = (data.get('title') or '').strip()
    if not title:
        return jsonify({'status': 'error', 'message': 'Title required'}), 400
    task = database.add_task(
        email,
        title,
        description=(data.get('description') or '').strip(),
        priority=data.get('priority', 'normal'),
        source='manual'
    )
    return jsonify({'status': 'ok', 'task': task})


@assistant_bp.route('/api/tasks/<int:task_id>/complete', methods=['POST'])
@login_required
def api_complete_task(task_id):
    email = session['user']['email']
    updated = database.complete_task(email, task_id)
    return jsonify({'status': 'ok' if updated else 'not_found'})


@assistant_bp.route('/api/tasks/<int:task_id>', methods=['DELETE'])
@login_required
def api_delete_task(task_id):
    email = session['user']['email']
    deleted = database.delete_task(email, task_id)
    return jsonify({'status': 'ok' if deleted else 'not_found'})


@assistant_bp.route('/api/my-pins')
@login_required
def get_my_pins():
    email = session['user']['email']
    pins = database.get_user_pins(email)
    return jsonify({
        'gmail_pin': pins.get('gmail_pin') if pins else '',
        'telegram_pin': pins.get('telegram_pin') if pins else '',
    })

