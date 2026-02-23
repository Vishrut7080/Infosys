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

# database.init_db() - for next milestone

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
    return render_template('login.html',
        username=EMAIL_USER,
        password_mask="*" * len(EMAIL_PASS))

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
        data = request.get_json()
        entered_email    = data.get('email', '')
        entered_password = data.get('password', '')

        # Accept either the main password or the audio secret password
        if entered_email == EMAIL_USER and (entered_password == EMAIL_PASS or entered_password == SECRET_AUD):
            login_status = 'success'
            return jsonify({'status': 'success', 'message': 'Login successful'})
        else:
            login_status = 'failed'
            return jsonify({'status': 'failed', 'message': 'Invalid credentials'})

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
    return google.authorize_redirect(redirect_uri)


# Step 2: Google redirects back here with an auth code
@app.route('/auth/google/callback')
def auth_google_callback():
    """
    Google calls this URL after the user approves (or denies) access.

    On success:
      - Exchanges the auth code for an access token
      - Fetches the user's profile (name, email, picture)
      - Sets login_status to 'success'
      - Stores user info in the Flask session
      - Redirects to Gmail

    On failure:
      - Resets login_status to 'failed'
      - Redirects back to the login page
    """
    global login_status
    try:
        # Exchange the temporary auth code for an access token
        token = google.authorize_access_token()

        # Get user profile from the ID token
        user_info = token.get('userinfo')
        if not user_info:
            # Fallback: fetch directly from Google's userinfo endpoint
            user_info = google.get(
                'https://openidconnect.googleapis.com/v1/userinfo'
            ).json()

        # Store profile in session so other routes can read it if needed
        session['user'] = {
            'name':    user_info.get('name'),
            'email':   user_info.get('email'),
            'picture': user_info.get('picture'),
        }

        # Mark as logged in — main.py polling loop will pick this up
        login_status = 'success'

        print(f"[OAuth] Google login successful: {session['user']['email']}")
        speak_text(f"[System]: Google login successful. Welcome {session['user']['name']}.")

        return redirect(GMAIL_URL)

    except Exception as e:
        print(f"[OAuth] Google login failed: {e}")
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
# START SERVER
# ----------------------

def start_server():
    print("Flask server starting...")
    app.run(port=5000, use_reloader=False)