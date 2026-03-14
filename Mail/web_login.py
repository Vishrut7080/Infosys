from flask import Flask, render_template, jsonify, request, redirect, url_for, session
from authlib.integrations.flask_client import OAuth
import os, asyncio
from Backend import database
from Audio.text_to_speech import speak_text
from dotenv import load_dotenv
import threading
from datetime import datetime

load_dotenv()

# ========================
# GLOBAL VARIABLES
# ========================
selected_services = [] # for email or telegram services
_feed_lock    = threading.Lock()
feed_log      = []          # [{text, time, index}, ...]
_feed_counter = 0
_nav_command  = {'command': None}

# -------------------------------------------------
# Load Credentials from env
# -------------------------------------------------

EMAIL_USER          = os.getenv("EMAIL_USER")
EMAIL_PASS          = os.getenv("EMAIL_PASS")
SECRET_AUD          = os.getenv("SECRET_AUD")           # Audio authentication password
GOOGLE_CLIENT_ID    = os.getenv("GOOGLE_CLIENT_ID")     # From Google Cloud Console
GOOGLE_CLIENT_SECRET= os.getenv("GOOGLE_CLIENT_SECRET") # From Google Cloud Console

app = Flask(__name__,
    template_folder='templates',
    static_folder='static'
)

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

microsoft = oauth.register(
    name='microsoft',
    client_id=os.getenv('MICROSOFT_CLIENT_ID'),
    client_secret=os.getenv('MICROSOFT_CLIENT_SECRET'),
    server_metadata_url='https://login.microsoftonline.com/common/v2.0/.well-known/openid-configuration',
    client_kwargs={
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
    global login_status
    # Reset failed status on page load so polling doesn't immediately trigger overlay
    if login_status == 'failed':
        login_status = 'waiting'
    return render_template('login.html',
        username=EMAIL_USER,
        password_mask="*" * len(EMAIL_PASS))

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
    print('Flask sees:', login_status)
    # For audio login — session isn't set by a form/OAuth
    # so we set a minimal session here so /dashboard doesn't reject it
    if login_status == 'success' and 'user' not in session:
        session['user'] = {
            'name' : 'User',
            'email': app.config.get('current_email', ''),
        }
    status = login_status
    if login_status == 'failed':
        login_status = 'waiting'
    return jsonify({'status': status})

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
            database.log_session(entered_email)
            apply_user_credentials(entered_email)
            return jsonify({'status': 'success', 'message': f'Welcome back, {result}!'})

        # Fallback: check .env credentials (original admin/owner login)
        elif entered_email == EMAIL_USER and (
            entered_password == EMAIL_PASS or
            entered_password == SECRET_AUD
        ):
            login_status = 'success'
            app.config['current_email'] = entered_email
            session['user'] = {'name': 'Admin', 'email': entered_email}
            return jsonify({'status': 'success', 'message': 'Login successful'})

        else:
            login_status = 'failed'
            return jsonify({'status': 'failed', 'message': result})  # result = error msg

    except Exception as e:
        print(f"Login error: {e}")
        login_status = 'failed'
        return jsonify({'status': 'error', 'message': str(e)})

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
    global selected_services
    data = request.get_json()
    selected_services = data.get('services', [])
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
        login_hint=EMAIL_USER,  # pre-selects this account
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

        session['user'] = {
            'name':    user_info.get('name'),
            'email':   user_info.get('email'),
            'picture': user_info.get('picture'),
        }
        database.log_session(session['user']['email'])
        apply_user_credentials(session['user']['email'])
        login_status = 'success'
        app.config['current_email'] = session['user']['email']
        print(f"[OAuth] Login successful: {session['user']['email']}")
        threading.Thread(
            target=speak_text,
            args=(f"[System]: Welcome {session['user']['name']}.",),
            daemon=True
        ).start()
        email = session['user']['email']
        return redirect(url_for('dashboard'))

    except Exception as e:
        # Print the FULL error with type
        print(f"[OAuth] Login failed — Type: {type(e).__name__}")
        print(f"[OAuth] Login failed — Full error: {repr(e)}")  # ← add this line
        login_status = 'failed'
        return redirect(url_for('login_page') + '?error=oauth_failed')

# ========================
# MICROSOFT OAUTH
# ========================

@app.route('/auth/microsoft')
def auth_microsoft():
    redirect_uri = url_for('auth_microsoft_callback', _external=True)
    return microsoft.authorize_redirect(redirect_uri)

@app.route('/auth/microsoft/callback')
def auth_microsoft_callback():
    global login_status
    try:
        token     = microsoft.authorize_access_token()
        user_info = token.get('userinfo')
        if not user_info:
            user_info = microsoft.get(
                'https://graph.microsoft.com/v1.0/me'
            ).json()

        session['user'] = {
            'name':    user_info.get('displayName') or user_info.get('name'),
            'email':   user_info.get('mail') or user_info.get('email') or user_info.get('userPrincipalName'),
            'picture': None,
        }
        database.log_session(session['user']['email'])
        apply_user_credentials(session['user']['email'])
        login_status = 'success'
        app.config['current_email'] = session['user']['email']
        print(f"[OAuth] Microsoft login: {session['user']['email']}")
        threading.Thread(
            target=speak_text,
            args=(f"[System]: Welcome {session['user']['name']}.",),
            daemon=True
        ).start()
        email = session['user']['email']
        return redirect(url_for('dashboard'))

    except Exception as e:
        print(f"[OAuth] Microsoft failed: {repr(e)}")
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
    session.clear()
    login_status = 'waiting'
    return redirect(url_for('login_page'))


# -------------------------------------------------
# SIGNUP - for future
# -------------------------------------------------

# Render the signup page
@app.route('/signup')
def signup_page():
    # Run TTS in background so Flask can return the page immediately
    threading.Thread(target=speak_text, args=('[System]: Opening signup page',), daemon=True).start()
    return render_template('signup.html')

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
            return jsonify({'status': 'success', 'message': 'Registration successful!'})
        else:
            return jsonify({'status': 'error', 'message': message})

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

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
        from Backend.database import USER_DB_PATH
        with sqlite3.connect(USER_DB_PATH) as conn:
            cur = conn.execute('SELECT COUNT(*) FROM sessions WHERE email = ?', (email,))
            sessions_count = cur.fetchone()[0]
    except:
        sessions_count = 0
    return jsonify({'emails': 0, 'commands': commands, 'sessions': sessions_count})

@app.route('/get-inbox')
def get_inbox():
    if 'user' not in session:
        return jsonify({'messages': []})
    
    messages = []
    services = selected_services or []

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

    # ── WhatsApp ───────────────────────────────────
    if 'whatsapp' in services:
        try:
            from Whatsapp.whatsapp import whatsapp_get_messages
            wa_msgs = whatsapp_get_messages(5)
            for m in wa_msgs:
                messages.append({
                    'source':  'whatsapp',
                    'from':    m['name'],
                    'to':      'Me',
                    'text':    m['message'],
                    'dir':     'Incoming',
                    'time':    m['date'],
                })
        except Exception as ex:
            print(f'[Inbox] WhatsApp error: {ex}')

    # Sort newest first — best effort (strings, so sort descending)
    messages.sort(key=lambda x: x.get('time', ''), reverse=True)
    return jsonify({'messages': messages})

# -------------------------------------------------
# START SERVER
# -------------------------------------------------

def start_server():
    print("Flask server starting...")
    app.run(port=5000, use_reloader=False)

__all__=['selected_services']