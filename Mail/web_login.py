from flask import Flask, render_template, jsonify, request, redirect, url_for, session
from authlib.integrations.flask_client import OAuth
import os
from Backend import database
from Audio.text_to_speech import speak_text
from dotenv import load_dotenv
import threading

load_dotenv()

# ----------------------
# Load Credentials from env
# ----------------------

EMAIL_USER          = os.getenv("EMAIL_USER")
EMAIL_PASS          = os.getenv("EMAIL_PASS")
SECRET_AUD          = os.getenv("SECRET_AUD")           # Audio authentication password
GOOGLE_CLIENT_ID    = os.getenv("GOOGLE_CLIENT_ID")     # From Google Cloud Console
GOOGLE_CLIENT_SECRET= os.getenv("GOOGLE_CLIENT_SECRET") # From Google Cloud Console

app = Flask(__name__)

# Required for Flask sessions (used by OAuth to store state between redirects)
# Set a strong random value in your .env as FLASK_SECRET_KEY
app.secret_key = os.getenv("FLASK_SECRET_KEY", "change-me-in-production")
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE']   = False

database.init_db()

# ----------------------
# Login Status Flag
# ----------------------

# to tell if you're logged in or not.
login_status = 'waiting'
# login_status = "waiting"    Not logged in
# login_status = "success"    Logged in!
# login_status = "failed"     Login cancelled

# ----------------------
# Google OAuth Setup
# ----------------------
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


# ========================
# ROUTING
# ========================

# ----------------------
# LOGIN
# ----------------------

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
    print('Flask sees:', login_status)  # debug
    return login_status

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


# ----------------------
# GOOGLE OAUTH
# ----------------------

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
        login_status = 'success'
        app.config['current_email'] = session['user']['email']
        print(f"[OAuth] Login successful: {session['user']['email']}")
        threading.Thread(
            target=speak_text,
            args=(f"[System]: Welcome {session['user']['name']}.",),
            daemon=True
        ).start()
        email = session['user']['email']
        return redirect(f"https://mail.google.com/mail/u/{email}/#inbox")

    except Exception as e:
        # Print the FULL error with type
        print(f"[OAuth] Login failed — Type: {type(e).__name__}")
        print(f"[OAuth] Login failed — Full error: {repr(e)}")  # ← add this line
        login_status = 'failed'
        return redirect(url_for('login_page') + '?error=oauth_failed')


# ----------------------
# LOGOUT
# ----------------------

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


# ----------------------
# SIGNUP - for future
# ----------------------

# Render the signup page
@app.route('/signup')
def signup_page():
    # Run TTS in background so Flask can return the page immediately
    threading.Thread(target=speak_text, args=('[System]: Opening signup page',), daemon=True).start()
    return render_template('signup.html')

@app.route('/register', methods=['POST'])
def register():
    try:
        data         = request.get_json()
        name         = data.get('name', '').strip()
        email        = data.get('email', '').strip()
        password     = data.get('password', '')
        secret_audio = data.get('secret_audio', '').lower().strip()

        if not name or not email or not password:
            return jsonify({'status': 'error', 'message': 'All fields required'})

        success, message = database.create_user(name, email, password, secret_audio)

        if success:
            return jsonify({'status': 'success', 'message': 'Registration successful!'})
        else:
            return jsonify({'status': 'error', 'message': message})

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

# ----------------------
# ROUTE TO SERVE RANDOM AUDIO SUGGESTION
# ----------------------    

@app.route('/suggest-audio')
def suggest_audio():
    from Backend import database
    word = database.suggest_audio_word()
    return jsonify({'word': word})

# ----------------------
# START SERVER
# ----------------------

def start_server():
    print("Flask server starting...")
    app.run(port=5000, use_reloader=False)