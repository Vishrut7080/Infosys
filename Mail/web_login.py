from flask import Flask, render_template, jsonify, request
import os
from dotenv import load_dotenv

load_dotenv()

# ----------------------
# Load Credentials from env
# ----------------------

EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")
SECRET_AUD = os.getenv("SECRET_AUD")  # Audio authentication password

app = Flask(__name__)

# to tell if you're logged in or not.
login_status = 'waiting'
# login_status = "waiting"    Not logged in
# login_status = "success"    Logged in!
# login_status = "failed"     Login cancelled

# ----------------------
# ROUTING
# ----------------------

# Login Form
@app.route('/')
def login_page():
    return render_template('login.html',
        username=EMAIL_USER,
        password_mask="*" * len(EMAIL_PASS))

# Check every seconf for audio
@app.route('/check')
def check_login():
    global login_status
    print('Flask sees:', login_status)  # debug
    return login_status

# Keyboard Login
@app.route('/login', methods=['POST'])
def login():
    global login_status
    try:
        data = request.get_json()
        entered_username = data.get('username', '')
        entered_password = data.get('password', '')
        
        # Check if credentials match either EMAIL_PASS or SECRET_AUD
        if entered_username == EMAIL_USER and (entered_password == EMAIL_PASS or entered_password == SECRET_AUD):
            login_status = 'success'
            return jsonify({'status': 'success', 'message': 'Login successful'})
        else:
            login_status = 'failed'
            return jsonify({'status': 'failed', 'message': 'Invalid credentials'})
    except Exception as e:
        print(f"Login error: {e}")
        login_status = 'failed'
        return jsonify({'status': 'error', 'message': str(e)})

# Start Server
def start_server():
    print("Flask server starting...")
    app.run(port=5000, use_reloader=False)