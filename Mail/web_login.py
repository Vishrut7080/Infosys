from flask import Flask, render_template, jsonify, request, redirect, url_for, session
from authlib.integrations.flask_client import OAuth
from functools import wraps
import os, asyncio
from Backend import database
from Audio.text_to_speech import speak_text
from dotenv import load_dotenv
import threading
from datetime import datetime

try:
    from deep_translator import GoogleTranslator as _GTranslator
    _translator = True 
except Exception:
    _translator = None

load_dotenv()

# ========================
# GLOBAL VARIABLES/FLAGS
# ========================
selected_services = [] 
_feed_counter = 0
_action_queue = [] # list of {'type': '...', 'data': {...}}
_feed_lock    = threading.Lock()
_action_lock  = threading.Lock()
feed_log      = []          
signup_open   = False
login_from_signup = False
services_just_selected = False
force_logout = False
is_voice_authenticated = False
telegram_ready = False
login_status = 'waiting'

# -------------------------------------------------
# Load Credentials from env
# -------------------------------------------------
SECRET_AUD          = os.getenv("SECRET_AUD")
GOOGLE_CLIENT_ID    = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET= os.getenv("GOOGLE_CLIENT_SECRET")

app = Flask(__name__,
    template_folder='templates',
    static_folder='static'
)

app.config['verified_services'] = []
app.secret_key = os.getenv("FLASK_SECRET_KEY", "change-me-in-production")
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE']   = False

database.init_db()

oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

def apply_user_credentials(email: str):
    creds = database.get_user_credentials(email)
    if not creds: return
    if creds['gmail_address']: os.environ['EMAIL_USER'] = creds['gmail_address']
    if creds['gmail_app_pass']: os.environ['EMAIL_PASS'] = creds['gmail_app_pass']
    if creds['tg_api_id']: os.environ['TELEGRAM_API_ID'] = creds['tg_api_id']
    if creds['tg_api_hash']: os.environ['TELEGRAM_API_HASH'] = creds['tg_api_hash']
    if creds['tg_phone']: os.environ['TELEGRAM_PHONE'] = creds['tg_phone']

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session: return redirect(url_for('login_page'))
        if not database.is_admin(session['user'].get('email', '')): return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated

def push_to_feed(text: str):
    global _feed_counter
    with _feed_lock:
        feed_log.append({
            'text':  text,
            'time':  datetime.now().strftime('%H:%M:%S'),
            'index': _feed_counter,
        })
        _feed_counter += 1
        if len(feed_log) > 300: feed_log.pop(0)

def push_action(action_type: str, data: dict = None):
    with _action_lock:
        _action_queue.append({'type': action_type, 'data': data or {}})

def push_nav_command(command: str):
    push_action('nav', {'command': command})

# -------------------------------------------------
# ROUTING
# -------------------------------------------------

@app.route('/')
def login_page():
    global login_status
    if login_status == 'failed': login_status = 'waiting'
    if 'user' not in session and login_status != 'success': login_status = 'waiting'
    from_signup = request.args.get('from') == 'signup'
    error       = request.args.get('error', '')
    return render_template('login.html', from_signup=from_signup, error=error)

user_typing = False
@app.route('/typing', methods=['POST'])
def set_typing():
    global user_typing
    data = request.get_json()
    if data.get('typing', False): user_typing = True
    return '', 204

@app.route('/check')
def check_login():
    global login_status
    status = login_status
    if status == 'success':
        email = app.config.get('current_email', '')
        if email:
            user_record = database.get_user_by_email(email)
            name = user_record['name'] if user_record else 'User'
            session.clear()
            session['user'] = {'name': name, 'email': email}
            session.permanent = True
            database.log_session(email, force_insert=True)
        login_status = 'waiting'
    redirect_url = '/dashboard'
    email = session.get('user', {}).get('email', '')
    if email and database.is_admin(email): redirect_url = '/admin'
    return jsonify({'status': status, 'redirect': redirect_url})

@app.route('/check-session')
def check_session():
    global force_logout
    if force_logout:
        session.clear()
        force_logout = False
        return jsonify({'logged_in': False})
    return jsonify({'logged_in': 'user' in session})

@app.route('/voice-logout', methods=['POST'])
def voice_logout():
    global login_status, is_voice_authenticated
    if 'user' in session:
        database.log_activity(session['user'].get('email', ''), 'logout', 'voice')
    session.clear()
    login_status = 'waiting'
    is_voice_authenticated = False
    return '', 204

@app.route('/login', methods=['POST'])
def login():
    global login_status, is_voice_authenticated
    try:
        data = request.get_json()
        email = data.get('email', '')
        password = data.get('password', '')
        success, result = database.verify_user(email, password)
        if success:
            login_status = 'success'
            is_voice_authenticated = True
            app.config['current_email'] = email
            session['user'] = {'name': result, 'email': email}
            database.log_session(email, force_insert=True)
            apply_user_credentials(email)
            database.log_activity(email, 'login', 'keyboard')
            return jsonify({'status': 'success', 'message': f'Welcome back, {result}!', 'redirect': '/admin' if database.is_admin(email) else '/dashboard'})
        else:
            login_status = 'failed'
            return jsonify({'status': 'failed', 'message': result})
    except Exception as e:
        login_status = 'failed'
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/start-audio-login', methods=['POST'])
def start_audio_login():
    global login_from_signup
    login_from_signup = True
    return '', 204

@app.route('/dashboard')
def dashboard():
    if 'user' not in session: return redirect(url_for('login_page'))
    return render_template('dashboard.html', user=session['user'])

@app.route('/select-services', methods=['POST'])
def select_services_route():
    global selected_services, services_just_selected
    data = request.get_json()
    selected_services = data.get('services', [])
    services_just_selected = True
    if selected_services:
       names = ' and '.join(s.capitalize() for s in selected_services)
       push_to_feed(f'[System]: {names} selected. Say "save services" or wait for confirmation.')
    return jsonify({'status': 'ok'})

@app.route('/get-services')
def get_services():
    return jsonify({
        'voice_confirmed': is_voice_authenticated,
        'services': app.config.get('verified_services', []),
    })

@app.route('/get-user-info')
def get_user_info():
    if 'user' not in session: return jsonify({'name': '', 'email': ''})
    email = session['user'].get('email', '')
    record = database.get_user_by_email(email)
    name = record['name'] if record else session['user'].get('name', 'User')
    session['user']['name'] = name
    return jsonify({'name': name, 'email': email, 'is_admin': database.is_admin(email)})

@app.route('/api/feed')
def api_feed():
    since = int(request.args.get('since', 0))
    with _feed_lock:
        new_entries = [e for e in feed_log if e['index'] >= since]
        next_index  = feed_log[-1]['index'] + 1 if feed_log else 0
    return jsonify({'entries': new_entries, 'next_index': next_index})

@app.route('/api/actions')
def api_get_actions():
    global _action_queue
    with _action_lock:
        actions = list(_action_queue)
        _action_queue = []
    return jsonify({'actions': actions})

@app.route('/api/nav_command')
def api_nav_command_legacy():
    # Keep for backwards compatibility if any old JS still polls this
    return jsonify({'command': None})

@app.route('/auth/google')
def auth_google():
    return google.authorize_redirect(url_for('auth_google_callback', _external=True), prompt='select_account')

@app.route('/auth/google/callback')
def auth_google_callback():
    global login_status, is_voice_authenticated
    try:
        token = google.authorize_access_token()
        user_info = token.get('userinfo') or google.get('https://openidconnect.googleapis.com/v1/userinfo').json()
        email = user_info.get('email')
        user_record = database.get_user_by_email(email)
        if not user_record:
            login_status = 'failed'
            return redirect(url_for('login_page') + '?error=not_registered')
        session['user'] = {'name': user_record['name'], 'email': email, 'picture': user_info.get('picture')}
        database.log_session(email, force_insert=True)
        apply_user_credentials(email)
        database.log_activity(email, 'login', 'google_oauth')
        login_status = 'success'
        is_voice_authenticated = True
        app.config['current_email'] = email
        return redirect('/admin' if database.is_admin(email) else '/dashboard')
    except Exception as e:
        login_status = 'failed'
        return redirect(url_for('login_page') + '?error=oauth_failed')

@app.route('/logout')
def logout():
    global login_status, is_voice_authenticated
    if 'user' in session: database.log_activity(session['user'].get('email', ''), 'logout', '')
    session.clear()
    login_status = 'waiting'
    is_voice_authenticated = False
    return redirect(url_for('login_page'))

@app.route('/signup')
def signup_page():
    global signup_open
    signup_open = True
    return render_template('signup.html')

@app.route('/signup-closed', methods=['POST'])
def signup_closed():
    global signup_open
    def _clear():
        import time
        time.sleep(3)
        global signup_open
        signup_open = False
    threading.Thread(target=_clear, daemon=True).start()
    return '', 204

@app.route('/register', methods=['POST'])
def register():
    try:
        data = request.get_json()
        name, email, password = data.get('name', '').strip(), data.get('email', '').strip(), data.get('password', '')
        if not name or not email or not password: return jsonify({'status': 'error', 'message': 'All fields required'})
        success, message = database.create_user(name, email, password, data.get('secret_audio', '').lower().strip(), data.get('gmail_address', '').strip(), data.get('gmail_app_pass', '').strip(), data.get('tg_api_id', '').strip(), data.get('tg_api_hash', '').strip(), data.get('tg_phone', '').strip())
        if success:
            pins = database.generate_pins(tg_included=bool(data.get('tg_api_id') and data.get('tg_api_hash')))
            database.store_pins(email, pins['gmail_pin'], pins.get('telegram_pin'))
            session['pending_pins'] = {'email': email, 'name': name, 'gmail_pin': pins['gmail_pin'], 'telegram_pin': pins.get('telegram_pin')}
            if data.get('is_admin') and data.get('admin_password', '').strip() == 'infosys':
                database.add_admin(email)
                session['pending_pins']['is_admin'] = True
            return jsonify({'status': 'success', 'message': 'Registration successful!'})
        return jsonify({'status': 'error', 'message': message})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/pin-reveal')
def pin_reveal():
    pins = session.get('pending_pins')
    if not pins: return redirect(url_for('login_page'))
    session.pop('pending_pins', None)
    return render_template('pin_reveal.html', pins=pins)

@app.route('/telegram-auth')
def telegram_auth_page():
    if 'user' not in session: return redirect(url_for('login_page'))
    return render_template('telegram_auth.html')

@app.route('/telegram/send-code', methods=['POST'])
def telegram_send_code():
    from Telegram.telegram import _client, _loop
    data = request.get_json()
    phone = data.get('phone', '').strip()
    try:
        asyncio.run_coroutine_threadsafe(_client.send_code_request(phone), _loop).result(timeout=15)
        app.config['telegram_phone'] = phone
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/telegram/verify-otp', methods=['POST'])
def telegram_verify_otp():
    global telegram_ready
    from Telegram.telegram import _client, _loop
    data = request.get_json()
    phone = data.get('phone', app.config.get('telegram_phone', ''))
    otp = data.get('otp', '').strip()
    try:
        asyncio.run_coroutine_threadsafe(_client.sign_in(phone, otp), _loop).result(timeout=15)
        telegram_ready = True
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/telegram/status')
def telegram_status():
    return jsonify({'ready': telegram_ready})

@app.route('/api/stt', methods=['POST'])
def api_stt():
    data = request.get_json()
    from Audio.io_queues import stt_queue
    stt_queue.put({"text": data.get('text', ''), "lang": data.get('lang', 'en')})
    return jsonify({'status': 'ok'})

@app.route('/api/tts')
def api_tts():
    from Audio.io_queues import tts_queue
    import queue
    messages = []
    try:
        while True: messages.append(tts_queue.get_nowait())
    except queue.Empty: pass
    return jsonify({'messages': messages})

@app.route('/suggest-audio')
def suggest_audio():
    return jsonify({'word': database.suggest_audio_word()})

@app.route('/get-stats')
def get_stats():
    if 'user' not in session: return jsonify({'emails': 0, 'commands': 0, 'sessions': 0})
    email = session['user'].get('email', '')
    try:
        with open('Audio/Transcribe.txt', 'r', encoding='utf-8') as f:
            commands = len([l for l in f.readlines() if l.strip()])
    except: commands = 0
    sessions_count = database.get_activity_count(email, 'login')
    emails_count = database.get_activity_count(email, 'email_read')
    return jsonify({'emails': emails_count, 'commands': commands, 'sessions': sessions_count})

@app.route('/get-inbox')
def get_inbox():
    if 'user' not in session: return jsonify({'messages': []})
    messages = []
    services = app.config.get('verified_services', []) or selected_services
    email = session['user'].get('email', '')
    if email: apply_user_credentials(email)
    if 'gmail' in services:
        try:
            from Mail.email_handler import get_top_senders
            for e in get_top_senders(count=5):
                if 'error' not in e:
                    messages.append({'source': 'gmail', 'from': e['sender'], 'to': 'Me', 'text': e['subject'] + ' — ' + e['summary'], 'dir': 'Incoming', 'time': e['date']})
        except: pass
    if 'telegram' in services:
        try:
            from Telegram.telegram import telegram_get_messages
            for m in telegram_get_messages(5):
                messages.append({'source': 'telegram', 'from': m['name'], 'to': 'Me', 'text': m['message'], 'dir': f"{m['unread']} unread" if m.get('unread') else 'Incoming', 'time': m['date']})
        except: pass
    messages.sort(key=lambda x: x.get('time', ''), reverse=True)
    return jsonify({'messages': messages})

@app.route('/admin')
@admin_required
def admin_page():
    return render_template('admin.html', user=session['user'])

@app.route('/is-admin')
def is_admin_check():
    if 'user' not in session: return jsonify({'is_admin': False})
    return jsonify({'is_admin': database.is_admin(session['user'].get('email', ''))})

@app.route('/admin/users')
@admin_required
def admin_get_users():
    return jsonify({'users': database.get_all_users()})

@app.route('/admin/active-users')
@admin_required
def admin_active_users():
    users = database.get_all_users()
    return jsonify({'total_users': len(users), 'active_users': len(database.get_active_users(minutes=30)), 'total_admins': sum(1 for u in users if u['is_admin']), 'total_commands': len(database.get_activity_log(action='voice_command', limit=10000)), 'total_logins': len(database.get_activity_log(action='login', limit=10000)), 'emails_sent': len(database.get_activity_log(action='email_sent', limit=10000)), 'tg_sent': len(database.get_activity_log(action='telegram_sent', limit=10000)), 'wa_sent': len(database.get_activity_log(action='whatsapp_sent', limit=10000))})

@app.route('/admin/activity')
@admin_required
def admin_get_activity():
    return jsonify({'log': database.get_activity_log(email=request.args.get('email'), action=request.args.get('action'), limit=int(request.args.get('limit', 100)))})

@app.route('/admin/delete-user', methods=['POST'])
@admin_required
def admin_delete_user_route():
    email = request.get_json().get('email', '')
    if email == session['user'].get('email', ''): return jsonify({'status': 'error', 'message': "You can't delete your own account from admin panel."})
    success, msg = database.admin_delete_user(email)
    return jsonify({'status': 'success' if success else 'error', 'message': msg})

@app.route('/admin/add-admin', methods=['POST'])
@admin_required
def admin_add_admin():
    success, msg = database.add_admin(request.get_json().get('email', ''))
    return jsonify({'status': 'success' if success else 'error', 'message': msg})

@app.route('/admin/remove-admin', methods=['POST'])
@admin_required
def admin_remove_admin():
    email = request.get_json().get('email', '')
    if email == session['user'].get('email', ''): return jsonify({'status': 'error', 'message': "You can't remove your own admin access."})
    success, msg = database.remove_admin(email)
    return jsonify({'status': 'success' if success else 'error', 'message': msg})

@app.route('/log-activity', methods=['POST'])
def log_activity_route():
    if 'user' not in session: return '', 204
    data = request.get_json()
    if session['user'].get('email') and data.get('action'): database.log_activity(session['user']['email'], data['action'], data.get('detail', ''))
    return '', 204

@app.route('/translate', methods=['POST'])
def translate_text():
    data = request.get_json()
    texts, target = data.get('texts', []), data.get('target', 'en')
    if target == 'en' or _translator is None: return jsonify({'translated': texts})
    translated = []
    for text in texts:
        try:
            result = _GTranslator(source='auto', target=target).translate(text)
            translated.append(result if result else text)
        except: translated.append(text)
    return jsonify({'translated': translated})

@app.route('/telegram/contacts')
def telegram_contacts():
    if 'user' not in session: return jsonify({'contacts': []})
    try:
        from Telegram.telegram import _run_async, _client, _loop
        if not _loop or not _client: return jsonify({'contacts': []})
        async def _get_contacts():
            contacts = []
            async for dialog in _client.iter_dialogs(limit=20):
                from Telegram.telegram import _get_name
                contacts.append({'name': _get_name(dialog.entity), 'unread': dialog.unread_count, 'last_message': dialog.message.message[:50] if dialog.message and dialog.message.message else '', 'date': dialog.message.date.strftime("%d %b %H:%M") if dialog.message and dialog.message.date else ''})
            return contacts
        return jsonify({'contacts': _run_async(_get_contacts())})
    except: return jsonify({'contacts': []})

@app.route('/update-profile-name', methods=['POST'])
def update_profile_name():
    if 'user' not in session: return jsonify({'status': 'error', 'message': 'Not logged in'})
    new_name = request.get_json().get('name', '').strip()
    ok, msg = database.update_name(session['user']['email'], new_name)
    if ok: session['user']['name'] = new_name
    return jsonify({'status': 'success' if ok else 'error', 'message': msg})

@app.route('/update-profile-password', methods=['POST'])
def update_profile_password():
    if 'user' not in session: return jsonify({'status': 'error', 'message': 'Not logged in'})
    data = request.get_json()
    ok, msg = database.update_password(session['user']['email'], data.get('old_password', ''), data.get('new_password', ''))
    return jsonify({'status': 'success' if ok else 'error', 'message': msg})

@app.route('/update-profile-audio', methods=['POST'])
def update_profile_audio():
    if 'user' not in session: return jsonify({'status': 'error', 'message': 'Not logged in'})
    ok, msg = database.update_audio(session['user']['email'], request.get_json().get('audio_password', '').strip())
    return jsonify({'status': 'success' if ok else 'error', 'message': msg})

@app.route('/delete-profile-account', methods=['POST'])
def delete_profile_account():
    if 'user' not in session: return jsonify({'status': 'error', 'message': 'Not logged in'})
    ok, msg = database.delete_user(session['user']['email'], request.get_json().get('password', ''))
    if ok: session.clear()
    return jsonify({'status': 'success' if ok else 'error', 'message': msg})

def start_server():
    print("Flask server starting...")
    app.run(host='0.0.0.0', port=5000, use_reloader=False)

__all__=['selected_services']
