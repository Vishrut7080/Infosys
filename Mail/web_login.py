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
selected_services = [] # for email or telegram services
_feed_lock    = threading.Lock()
feed_log      = []          # [{text, time, index}, ...]
_feed_counter = 0
_nav_command  = {'command': None}
signup_open = False
login_from_signup = False
services_just_selected = False

# -------------------------------------------------
# Load Credentials from env
# -------------------------------------------------
SECRET_AUD          = os.getenv("SECRET_AUD")           # Audio authentication password
GOOGLE_CLIENT_ID    = os.getenv("GOOGLE_CLIENT_ID")     # From Google Cloud Console
GOOGLE_CLIENT_SECRET= os.getenv("GOOGLE_CLIENT_SECRET") # From Google Cloud Console

app = Flask(__name__,
    template_folder='templates',
    static_folder='static'
)

app.config['verified_services'] = []

# Required for Flask sessions (used by OAuth to store state between redirects)
# Set a strong random value in your .env as FLASK_SECRET_KEY
app.secret_key = os.getenv("FLASK_SECRET_KEY", "change-me-in-production")
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE']   = False

database.init_db()

# ========================
# GLOBAL FLAGS
# ========================
telegram_ready = False
# -------------------------------------------------
# Login Status Flag
# -------------------------------------------------

# to tell if you're logged in or not.
login_status = 'waiting'
# login_status = "waiting"    Not logged in
# login_status = "success"    Logged in!
# login_status = "failed"     Login cancelled

# -------------------------------------------------
# Google OAuth Setup
# -------------------------------------------------
# Uses Authlib to handle the OAuth 2.0 flow with Google.
# server_metadata_url is Google's OpenID Connect discovery document —
# it tells Authlib where Google's auth/token endpoints are automatically,
# so we don't need to hardcode them.

oauth = OAuth(app)

google = oauth.register(
    name='google',
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        # openid = identity, email = address, profile = name + picture
        'scope': 'openid email profile'
    }
)

# Where all successful logins redirect to
GMAIL_URL = "https://mail.google.com/mail/u/0/#inbox"

def apply_user_credentials(email: str):
    """Load user's Gmail + Telegram credentials from DB into os.environ."""
    creds = database.get_user_credentials(email)
    if not creds:
        return
    if creds['gmail_address']:
        os.environ['EMAIL_USER'] = creds['gmail_address']
    if creds['gmail_app_pass']:
        os.environ['EMAIL_PASS'] = creds['gmail_app_pass']
    if creds['tg_api_id']:
        os.environ['TELEGRAM_API_ID'] = creds['tg_api_id']
    if creds['tg_api_hash']:
        os.environ['TELEGRAM_API_HASH'] = creds['tg_api_hash']
    if creds['tg_phone']:
        os.environ['TELEGRAM_PHONE'] = creds['tg_phone']
    print(f'[Auth] Credentials loaded for {email}')

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login_page'))
        if not database.is_admin(session['user'].get('email', '')):
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated

def push_to_feed(text: str):
    """Append a spoken/heard line to the live dashboard feed."""
    global _feed_counter
    with _feed_lock:
        feed_log.append({
            'text':  text,
            'time':  datetime.now().strftime('%H:%M:%S'),
            'index': _feed_counter,
        })
        _feed_counter += 1
        if len(feed_log) > 300:   # keep last 300 entries
            feed_log.pop(0)
 
 
def push_nav_command(command: str):
    """
    Push an audio navigation / service-select command so
    the dashboard JS can pick it up at /api/nav_command.
    """
    _nav_command['command'] = command

# ========================
# ROUTING
# ========================

# -------------------------------------------------
# LOGIN
# -------------------------------------------------

# Render the login page
@app.route('/')
def login_page():
    global login_status, login_from_signup
    if login_status == 'failed':
        login_status = 'waiting'
    # ONLY reset to waiting if not already in a success state set by audio login
    # Don't clobber a success that main.py just set before session was populated
    if 'user' not in session and login_status != 'success':
        login_status = 'waiting'
    from_signup = request.args.get('from') == 'signup'
    error       = request.args.get('error', '')
    return render_template('login.html', from_signup=from_signup, error=error)

# Flag to pause audio listening when user is active in browser
user_typing = False

@app.route('/typing', methods=['POST'])
def set_typing():
    global user_typing
    data = request.get_json()
    if data.get('typing', False):  # only on keydown, ignore blur
        user_typing = True
    return '', 204

# Check every second for audio login status
@app.route('/check')
def check_login():
    global login_status
    if login_status == 'success':
        email = app.config.get('current_email', '')
        name = 'User'
        if email:
            user_record = database.get_user_by_email(email)
            if user_record:
                name = user_record['name']
        # Always overwrite session — clears any stale previous user data
        session.clear()
        session['user'] = {'name': name, 'email': email}
        if email:
            database.log_session(email, force_insert=True)
    status = login_status
    if login_status == 'failed':
        login_status = 'waiting'
    redirect_url = '/dashboard'
    if status == 'success':
        email = app.config.get('current_email', '')
        if email and database.is_admin(email):
            redirect_url = '/admin'
    return jsonify({'status': status, 'redirect': redirect_url})

@app.route('/check-session')
def check_session():
    return jsonify({'logged_in': 'user' in session})

@app.route('/login-cancelled')
def login_cancelled():
    """Redirects to login page after showing cancellation message."""
    return '''<!DOCTYPE html>
<html>
<head><title>Cancelled</title></head>
<body style="margin:0;background:#0f0f0f;display:flex;align-items:center;justify-content:center;height:100vh;">
<div style="text-align:center;font-family:sans-serif;">
    <p style="color:#888;font-size:18px;">Login cancelled.</p>
    <p style="color:#555;font-size:14px;">Returning to login page...</p>
    <div style="margin-top:16px;width:200px;height:3px;background:#222;border-radius:2px;overflow:hidden;margin-left:auto;margin-right:auto;">
        <div id="bar" style="height:100%;width:0%;background:#6366f1;transition:width 3s linear;"></div>
    </div>
</div>
<script>
  setTimeout(() => document.getElementById('bar').style.width = '100%', 50);
  setTimeout(() => window.location.href = '/', 3200);
</script>
</body>
</html>'''

@app.route('/voice-logout', methods=['POST'])
def voice_logout():
    """Called by main.py when voice logout command is detected."""
    global login_status
    if 'user' in session:
        database.log_activity(session['user'].get('email', ''), 'logout', 'voice')
    session.clear()
    login_status = 'waiting'
    return '', 204

# Handle Keyboard Login
@app.route('/login', methods=['POST'])
def login():
    global login_status
    try:
        data             = request.get_json()
        entered_email    = data.get('email', '')
        entered_password = data.get('password', '')

        # First check against database (registered users)
        success, result = database.verify_user(entered_email, entered_password)

        if success:
            login_status = 'success'
            app.config['current_email'] = entered_email
            session['user'] = {'name': result, 'email': entered_email}
            database.log_session(entered_email, force_insert=True)
            apply_user_credentials(entered_email)
            database.log_activity(entered_email, 'login', 'keyboard')
            is_admin_user = database.is_admin(entered_email)
            return jsonify({
                'status':    'success',
                'message':   f'Welcome back, {result}!',
                'redirect':  '/admin' if is_admin_user else '/dashboard'
            })

        else:
            login_status = 'failed'
            return jsonify({'status': 'failed', 'message': result})  # result = error msg

    except Exception as e:
        print(f"Login error: {e}")
        login_status = 'failed'
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/start-audio-login', methods=['POST'])
def start_audio_login():
    """Called by login page when arriving from signup — signals main.py to start listening."""
    global login_from_signup
    login_from_signup = True
    return '', 204

# -------------------------------------------------
# DASHBOARD
# -------------------------------------------------

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login_page'))
    return render_template('dashboard.html', user=session['user'])

@app.route('/select-services', methods=['POST'])
def select_services():
    global selected_services, services_just_selected
    data = request.get_json()
    selected_services = data.get('services', [])
    services_just_selected = True
    print(f"[Dashboard] Services selected: {selected_services}")
    # Acknowledgement
    if selected_services:
       names = ' and '.join(s.capitalize() for s in selected_services)
       push_to_feed(f'[System]: {names} selected. Say "save services" or wait for confirmation.')
    return jsonify({'status': 'ok'})

@app.route('/get-services')
def get_services():
    return jsonify({
        'voice_confirmed': login_status == 'success',
        'services':        selected_services if selected_services else [],
    })

@app.route('/get-user-info')
def get_user_info():
    if 'user' not in session:
        return jsonify({'name': '', 'email': ''})
    email = session['user'].get('email', '')
    # Always fetch fresh from DB so audio login gets real name
    record = database.get_user_by_email(email)
    name   = record['name'] if record else session['user'].get('name', 'User')
    # Also update the session so future page loads are correct
    session['user']['name'] = name
    return jsonify({'name': name, 'email': email, 'is_admin': database.is_admin(email)})

# -------------------------------------------------
# NAVIGATION IN DASHBOARD
# -------------------------------------------------

@app.route('/api/feed')
def api_feed():
    """Return new feed entries since the given index."""
    since = int(request.args.get('since', 0))
    with _feed_lock:
        new_entries = [e for e in feed_log if e['index'] >= since]
        next_index  = feed_log[-1]['index'] + 1 if feed_log else 0
    return jsonify({'entries': new_entries, 'next_index': next_index})
 
 
@app.route('/api/feed/clear', methods=['POST'])
def api_feed_clear():
    global _feed_counter
    with _feed_lock:
        feed_log.clear()
        _feed_counter = 0
    return jsonify({'ok': True})
 
 
@app.route('/api/nav_command')
def api_nav_command():
    """Return latest nav command and immediately clear it."""
    cmd = _nav_command.get('command')
    _nav_command['command'] = None
    return jsonify({'command': cmd})
 

# -------------------------------------------------
# GOOGLE OAUTH
# -------------------------------------------------

# Step 1: Redirect user to Google's consent screen
@app.route('/auth/google')
def auth_google():
    """
    Starts the Google OAuth flow.
    The redirect_uri must exactly match what you registered in Google Cloud Console:
      http://localhost:5000/auth/google/callback
    """
    redirect_uri = url_for('auth_google_callback', _external=True)
    print(f"[OAuth] Redirect URI being sent to Google: {redirect_uri}")
    return google.authorize_redirect(
        redirect_uri,
        prompt='select_account'            # forces account chooser every time
    )


# Step 2: Google redirects back here with an auth code
@app.route('/auth/google/callback')
def auth_google_callback():
    global login_status
    try:
        token = google.authorize_access_token()
        user_info = token.get('userinfo')
        if not user_info:
            user_info = google.get(
                'https://openidconnect.googleapis.com/v1/userinfo'
            ).json()

        oauth_email = user_info.get('email')
        oauth_name  = user_info.get('name')

        # Check if this email is registered in the database
        user_record = database.get_user_by_email(oauth_email)
        if not user_record:
            login_status = 'failed'
            return redirect(url_for('login_page') + '?error=not_registered')

        session['user'] = {
            'name':    user_record['name'],
            'email':   oauth_email,
            'picture': user_info.get('picture'),
        }
        database.log_session(session['user']['email'], force_insert=True)
        apply_user_credentials(oauth_email)
        database.log_activity(oauth_email, 'login', 'google_oauth')
        login_status = 'success'
        app.config['current_email'] = oauth_email
        print(f"[OAuth] Login successful: {oauth_email}")
        threading.Thread(
            target=speak_text,
            args=(f"[System]: Welcome {user_record['name']}.",),
            daemon=True
        ).start()
        redirect_url = '/admin' if database.is_admin(oauth_email) else '/dashboard'
        return redirect(redirect_url)

    except Exception as e:
        # Print the FULL error with type
        print(f"[OAuth] Login failed — Type: {type(e).__name__}")
        print(f"[OAuth] Login failed — Full error: {repr(e)}")  # ← add this line
        login_status = 'failed'
        return redirect(url_for('login_page') + '?error=oauth_failed')

# -------------------------------------------------
# LOGOUT
# -------------------------------------------------

@app.route('/logout')
def logout():
    """
    Clears the Flask session and resets login_status.
    Note: this logs the user out of the assistant, not their Google account.
    """
    global login_status
    if 'user' in session:
        database.log_activity(session['user'].get('email', ''), 'logout', '')
    session.clear()
    login_status = 'waiting'
    return redirect(url_for('login_page'))


# -------------------------------------------------
# SIGNUP - for future
# -------------------------------------------------

# Render the signup page
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
        time.sleep(3)   # wait for redirect + login page to fully load
        global signup_open
        signup_open = False
    threading.Thread(target=_clear, daemon=True).start()
    return '', 204

@app.route('/register', methods=['POST'])
def register():
    try:
        data           = request.get_json()
        name           = data.get('name', '').strip()
        email          = data.get('email', '').strip()
        password       = data.get('password', '')
        secret_audio   = data.get('secret_audio', '').lower().strip()
        gmail_address  = data.get('gmail_address', '').strip()
        gmail_app_pass = data.get('gmail_app_pass', '').strip()
        tg_api_id      = data.get('tg_api_id', '').strip()
        tg_api_hash    = data.get('tg_api_hash', '').strip()
        tg_phone       = data.get('tg_phone', '').strip()

        if not name or not email or not password:
            return jsonify({'status': 'error', 'message': 'All fields required'})

        success, message = database.create_user(
            name, email, password, secret_audio,
            gmail_address, gmail_app_pass,
            tg_api_id, tg_api_hash, tg_phone
        )

        if success:
            # ── Generate PINs ──
            tg_included = bool(tg_api_id and tg_api_hash)
            pins = database.generate_pins(tg_included=tg_included)
            database.store_pins(
                email,
                pins['gmail_pin'],
                pins.get('telegram_pin')
            )
            session['pending_pins'] = {
                'email':        email,
                'name':         name,
                'gmail_pin':    pins['gmail_pin'],
                'telegram_pin': pins.get('telegram_pin'),
            }
            # ── Admin account creation ──
            is_admin    = data.get('is_admin', False)
            admin_pass  = data.get('admin_password', '').strip()
            if is_admin:
                if admin_pass == 'infosys':                # ← hardcoded admin password
                    database.add_admin(email)
                    session['pending_pins']['is_admin'] = True
                else:
                    # Registration succeeded but admin grant failed — still redirect to pins
                    session['pending_pins']['admin_failed'] = True
            return jsonify({'status': 'success', 'message': 'Registration successful!'})
        else:
            return jsonify({'status': 'error', 'message': message})

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

# -------------------------------------------------
# PIN ROUTE
# -------------------------------------------------
@app.route('/pin-reveal')
def pin_reveal():
    pins = session.get('pending_pins')
    if not pins:
        return redirect(url_for('login_page'))
    # Clear from session after reading — shown only once
    session.pop('pending_pins', None)
    return render_template('pin_reveal.html', pins=pins)

# -------------------------------------------------
# TELEGRAM
# -------------------------------------------------
@app.route('/telegram-auth')
def telegram_auth_page():
    if 'user' not in session:
        return redirect(url_for('login_page'))
    return render_template('telegram_auth.html')

@app.route('/telegram/send-code', methods=['POST'])
def telegram_send_code():
    from Telegram.telegram import _client, _loop
    data  = request.get_json()
    phone = data.get('phone', '').strip()
    try:
        future = asyncio.run_coroutine_threadsafe(
            _client.send_code_request(phone), _loop
        )
        future.result(timeout=15)
        app.config['telegram_phone'] = phone
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/telegram/verify-otp', methods=['POST'])
def telegram_verify_otp():
    global telegram_ready
    from Telegram.telegram import _client, _loop
    data  = request.get_json()
    phone = data.get('phone', app.config.get('telegram_phone', ''))
    otp   = data.get('otp', '').strip()
    try:
        future = asyncio.run_coroutine_threadsafe(
            _client.sign_in(phone, otp), _loop
        )
        future.result(timeout=15)
        telegram_ready = True
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/telegram/status')
def telegram_status():
    return jsonify({'ready': telegram_ready})
# -------------------------------------------------
# AUDIO QUEUE ROUTES
# -------------------------------------------------
@app.route('/api/stt', methods=['POST'])
def api_stt():
    """Receives text recognized by the frontend and passes it to main.py loop."""
    data = request.get_json()
    text = data.get('text', '')
    lang = data.get('lang', 'en')
    from Audio.io_queues import stt_queue
    stt_queue.put({"text": text, "lang": lang})
    return jsonify({'status': 'ok'})

@app.route('/api/tts')
def api_tts():
    """Returns text that needs to be spoken by the frontend."""
    from Audio.io_queues import tts_queue
    import queue
    messages = []
    try:
        # Get all pending messages without blocking
        while True:
            messages.append(tts_queue.get_nowait())
    except queue.Empty:
        pass
    return jsonify({'messages': messages})

# -------------------------------------------------
# ROUTE TO SERVE RANDOM AUDIO SUGGESTION
# -------------------------------------------------    

@app.route('/suggest-audio')
def suggest_audio():
    from Backend import database
    word = database.suggest_audio_word()
    return jsonify({'word': word})

@app.route('/get-stats')
def get_stats():
    if 'user' not in session:
        return jsonify({'emails': 0, 'commands': 0, 'sessions': 0})
    email = session['user'].get('email', '')
    try:
        with open('Audio/Transcribe.txt', 'r', encoding='utf-8') as f:
            commands = len([l for l in f.readlines() if l.strip()])
    except:
        commands = 0
    try:
        import sqlite3
        from Backend.database import ADMIN_DB_PATH
        with sqlite3.connect(ADMIN_DB_PATH) as conn:
            sessions_count = conn.execute(
                "SELECT COUNT(*) FROM activity_log WHERE email = ? AND action = 'login'",
                (email,)
            ).fetchone()[0]
    except Exception as e:
        print(f'[Stats] sessions error: {e}')
        sessions_count = 0
    try:
        import sqlite3
        from Backend.database import ADMIN_DB_PATH
        with sqlite3.connect(ADMIN_DB_PATH) as conn:
            emails_count = conn.execute(
                "SELECT COUNT(*) FROM activity_log WHERE email = ? AND action = 'email_read'",
                (email,)
            ).fetchone()[0]
    except Exception as e:
        print(f'[Stats] emails error: {e}')
        emails_count = 0
    return jsonify({'emails': emails_count, 'commands': commands, 'sessions': sessions_count})

@app.route('/get-inbox')
def get_inbox():
    if 'user' not in session:
        return jsonify({'messages': []})
    
    messages = []
    services = app.config.get('verified_services', []) or selected_services or []
    
    # Ensure credentials are loaded
    email = session['user'].get('email', '')
    if email:
        apply_user_credentials(email)
        
    # ── Gmail ──────────────────────────────────────
    if 'gmail' in services:
        try:
            from Mail.email_handler import get_top_senders
            emails = get_top_senders(count=5)
            for e in emails:
                if 'error' not in e:
                    messages.append({
                        'source':  'gmail',
                        'from':    e['sender'],
                        'to':      'Me',
                        'text':    e['subject'] + ' — ' + e['summary'],
                        'dir':     'Incoming',
                        'time':    e['date'],
                    })
        except Exception as ex:
            print(f'[Inbox] Gmail error: {ex}')

    # ── Telegram ───────────────────────────────────
    if 'telegram' in services:
        try:
            from Telegram.telegram import telegram_get_messages
            tg_msgs = telegram_get_messages(5)
            for m in tg_msgs:
                messages.append({
                    'source':  'telegram',
                    'from':    m['name'],
                    'to':      'Me',
                    'text':    m['message'],
                    'dir':     f"{m['unread']} unread" if m.get('unread') else 'Incoming',
                    'time':    m['date'],
                })
        except Exception as ex:
            print(f'[Inbox] Telegram error: {ex}')

    # Sort newest first — best effort (strings, so sort descending)
    messages.sort(key=lambda x: x.get('time', ''), reverse=True)
    return jsonify({'messages': messages})

# -------------------------------------------------
# ADMIN
# -------------------------------------------------

@app.route('/admin')
def admin_page():
    if 'user' not in session:
        return redirect(url_for('login_page'))
    if not database.is_admin(session['user'].get('email', '')):
        return redirect(url_for('dashboard'))
    return render_template('admin.html', user=session['user'])

@app.route('/is-admin')
def is_admin_check():
    """Lightweight endpoint — tells the dashboard if current user is admin."""
    if 'user' not in session:
        return jsonify({'is_admin': False})
    email = session['user'].get('email', '')
    return jsonify({'is_admin': database.is_admin(email)})

@app.route('/admin/users')
@admin_required
def admin_get_users():
    users = database.get_all_users()
    return jsonify({'users': users})


@app.route('/admin/active-users')
@admin_required
def admin_active_users():
    users  = database.get_all_users()
    active = database.get_active_users(minutes=30)
    return jsonify({
        'total_users':    len(users),
        'active_users':   len(active),
        'total_admins':   sum(1 for u in users if u['is_admin']),
        'total_commands': len(database.get_activity_log(action='voice_command', limit=10000)),
        'total_logins':   len(database.get_activity_log(action='login', limit=10000)),
        'emails_sent':    len(database.get_activity_log(action='email_sent', limit=10000)),
        'tg_sent':        len(database.get_activity_log(action='telegram_sent', limit=10000)),
        'wa_sent':        len(database.get_activity_log(action='whatsapp_sent', limit=10000)),
    })


@app.route('/admin/activity')
@admin_required
def admin_get_activity():
    email  = request.args.get('email', None)
    action = request.args.get('action', None)
    limit  = int(request.args.get('limit', 100))
    log    = database.get_activity_log(email=email, action=action, limit=limit)
    return jsonify({'log': log})


@app.route('/admin/delete-user', methods=['POST'])
@admin_required
def admin_delete_user_route():
    data  = request.get_json()
    email = data.get('email', '')
    if email == session['user'].get('email', ''):
        return jsonify({'status': 'error',
                        'message': "You can't delete your own account from admin panel."})
    success, msg = database.admin_delete_user(email)
    return jsonify({'status': 'success' if success else 'error', 'message': msg})


@app.route('/admin/add-admin', methods=['POST'])
@admin_required
def admin_add_admin():
    data  = request.get_json()
    email = data.get('email', '')
    success, msg = database.add_admin(email)
    return jsonify({'status': 'success' if success else 'error', 'message': msg})


@app.route('/admin/remove-admin', methods=['POST'])
@admin_required
def admin_remove_admin():
    data  = request.get_json()
    email = data.get('email', '')
    if email == session['user'].get('email', ''):
        return jsonify({'status': 'error',
                        'message': "You can't remove your own admin access."})
    success, msg = database.remove_admin(email)
    return jsonify({'status': 'success' if success else 'error', 'message': msg})

@app.route('/admin/api-usage')
@admin_required
def admin_api_usage():
    log   = database.get_activity_log(limit=10000)
    usage = {}
    for entry in log:
        usage[entry['action']] = usage.get(entry['action'], 0) + 1
    return jsonify({'usage': usage})


@app.route('/admin/error-logs')
@admin_required
def admin_error_logs():
    log    = database.get_activity_log(limit=500)
    errors = [l for l in log if
              'fail'      in l['action'].lower() or
              'error'     in (l['detail'] or '').lower() or
              'incorrect' in (l['detail'] or '').lower()]
    return jsonify({'errors': errors[:50]})

@app.route('/admin/stats')
@admin_required
def admin_stats():
    users  = database.get_all_users()
    active = database.get_active_users(minutes=30)
    return jsonify({
        'total_users':    len(users),
        'active_users':   len(active),
        'total_admins':   sum(1 for u in users if u['is_admin']),
        'total_commands': len(database.get_activity_log(action='voice_command', limit=10000)),
        'total_logins':   len(database.get_activity_log(action='login', limit=10000)),
        'emails_sent':    len(database.get_activity_log(action='email_sent', limit=10000)),
        'tg_sent':        len(database.get_activity_log(action='telegram_sent', limit=10000)),
        'wa_sent':        len(database.get_activity_log(action='whatsapp_sent', limit=10000)),
        'pin_fails':      len(database.get_activity_log(action='pin_failed', limit=10000)),
    })


# -------------------------------------------------
# ACTIVITY LOGGING (called from dashboard JS)
# -------------------------------------------------

@app.route('/log-activity', methods=['POST'])
def log_activity_route():
    if 'user' not in session:
        return '', 204
    data   = request.get_json()
    action = data.get('action', '')
    detail = data.get('detail', '')
    email  = session['user'].get('email', '')
    if email and action:
        database.log_activity(email, action, detail)
    return '', 204

# -------------------------------------------------
# LANGUAGE CONVERSION
# -------------------------------------------------
@app.route('/translate', methods=['POST'])
def translate_text():
    data   = request.get_json()
    texts  = data.get('texts', [])
    target = data.get('target', 'en')
    if target == 'en' or _translator is None:
        return jsonify({'translated': texts})
    translated = []
    for text in texts:
        try:
            result = _GTranslator(source='auto', target=target).translate(text)
            translated.append(result if result else text)
        except Exception:
            translated.append(text)
    return jsonify({'translated': translated})

@app.route('/telegram/contacts')
def telegram_contacts():
    if 'user' not in session:
        return jsonify({'contacts': []})
    try:
        from Telegram.telegram import _run_async, _client, _loop
        if _loop is None or _client is None:
            return jsonify({'contacts': []})
        
        async def _get_contacts():
            contacts = []
            async for dialog in _client.iter_dialogs(limit=20):
                from Telegram.telegram import _get_name
                contacts.append({
                    'name': _get_name(dialog.entity),
                    'unread': dialog.unread_count,
                    'last_message': dialog.message.message[:50] if dialog.message and dialog.message.message else '',
                    'date': dialog.message.date.strftime("%d %b %H:%M") if dialog.message and dialog.message.date else '',
                })
            return contacts
        
        contacts = _run_async(_get_contacts())
        return jsonify({'contacts': contacts})
    except Exception as e:
        print(f'[Contacts] Error: {e}')
        return jsonify({'contacts': []})

# -------------------------------------------------
# START SERVER
# -------------------------------------------------

def start_server():
    print("Flask server starting...")
    app.run(host='0.0.0.0', port=5000, use_reloader=False)

__all__=['selected_services']