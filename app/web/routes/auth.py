from flask import Blueprint, render_template, request, jsonify, redirect, url_for, session
from app.database import database
from app.web import oauth

auth_bp = Blueprint('auth', __name__)

def apply_user_credentials(email: str):
    # Deprecated: previously set process-wide environment variables
    # for per-user credentials. This is unsafe in multi-user setups.
    # Tools and services should fetch per-user credentials from the
    # database when needed (see services/telegram.py changes).
    return

@auth_bp.route('/')
def login_page():
    from_signup = request.args.get('from') == 'signup'
    error = request.args.get('error', '')
    return render_template('login.html', from_signup=from_signup, error=error)

@auth_bp.route('/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        email, password = data.get('email', ''), data.get('password', '')
        success, result = database.verify_user(email, password)
        if success:
            session['user'] = {'name': result, 'email': email}
            session['voice_auth'] = True
            database.log_session(email, force_insert=True)
            apply_user_credentials(email)
            database.log_activity(email, 'login', 'keyboard')
            return jsonify({
                'status': 'success', 
                'redirect': '/admin' if database.is_admin(email) else '/dashboard'
            })
        return jsonify({'status': 'failed', 'message': result})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@auth_bp.route('/voice-login', methods=['POST'])
def voice_login():
    """Authenticate via spoken audio password (Web Speech API → POST here)."""
    try:
        data = request.get_json()
        spoken = (data.get('text') or '').lower().strip()
        if not spoken:
            return jsonify({'status': 'failed', 'message': 'No audio received.'})
        matched, name, email = database.verify_audio(spoken)
        if matched:
            session['user'] = {'name': name, 'email': email}
            session['voice_auth'] = True
            database.log_session(email, force_insert=True)
            apply_user_credentials(email)
            database.log_activity(email, 'login', 'voice_audio_password')
            from app.core.config import settings
            creds = database.get_user_credentials(email)
            if creds and creds.get('tg_api_id'):
                if settings.mock_telegram:
                    from app.services.mocks.mock_telegram import start_telegram_in_thread
                else:
                    from app.services.telegram import start_telegram_in_thread
                start_telegram_in_thread(email)
            return jsonify({
                'status': 'success',
                'name': name,
                'redirect': '/admin' if database.is_admin(email) else '/dashboard'
            })
        return jsonify({'status': 'failed', 'message': 'Audio password not recognised. Please try again.'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@auth_bp.route('/logout')
def logout():
    email = session.get('user', {}).get('email')
    if email: 
        database.log_activity(email, 'logout', '')
    session.clear()
    return redirect(url_for('auth.login_page'))

@auth_bp.route('/register', methods=['POST'])
def register():
    try:
        data = request.get_json()
        name, email, password = data.get('name', '').strip(), data.get('email', '').strip(), data.get('password', '')
        if not name or not email or not password: 
            return jsonify({'status': 'error', 'message': 'All fields required'})
        
        success, message = database.create_user(
            name, email, password, 
            data.get('secret_audio', '').lower().strip(), 
            data.get('gmail_address', '').strip(), 
            data.get('gmail_app_pass', '').strip(), 
            data.get('tg_api_id', '').strip(), 
            data.get('tg_api_hash', '').strip(), 
            data.get('tg_phone', '').strip()
        )
        if success:
            pins = database.generate_pins(tg_included=bool(data.get('tg_api_id') and data.get('tg_api_hash')))
            gmail_pin = str(pins.get('gmail_pin', '0000'))
            telegram_pin = str(pins.get('telegram_pin') or '')
            database.store_pins(email, gmail_pin, telegram_pin)
            session['pending_pins'] = {
                'email': email, 'name': name, 
                'gmail_pin': gmail_pin, 
                'telegram_pin': telegram_pin
            }
            if data.get('is_admin') and data.get('admin_password', '').strip() == 'infosys':
                database.add_admin(email)
                session['pending_pins']['is_admin'] = True
            return jsonify({'status': 'success', 'message': 'Registration successful!'})
        return jsonify({'status': 'error', 'message': message})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@auth_bp.route('/auth/google')
def auth_google():
    return oauth.google.authorize_redirect(url_for('auth.auth_google_callback', _external=True), prompt='select_account')

@auth_bp.route('/auth/google/callback')
def auth_google_callback():
    try:
        token = oauth.google.authorize_access_token()
        user_info = token.get('userinfo') or oauth.google.get('https://openidconnect.googleapis.com/v1/userinfo').json()
        email = user_info.get('email')
        user_record = database.get_user_by_email(email)
        if not user_record:
            return redirect(url_for('auth.login_page') + '?error=not_registered')
        
        session['user'] = {'name': user_record['name'], 'email': email, 'picture': user_info.get('picture')}
        session['voice_auth'] = True
        database.log_session(email, force_insert=True)
        apply_user_credentials(email)
        database.log_activity(email, 'login', 'google_oauth')
        return redirect('/admin' if database.is_admin(email) else '/dashboard')
    except Exception:
        return redirect(url_for('auth.login_page') + '?error=oauth_failed')

@auth_bp.route('/signup')
def signup_page():
    return render_template('signup.html')

@auth_bp.route('/check-session')
def check_session():
    return jsonify({'logged_in': 'user' in session})

@auth_bp.route('/pin-reveal')
def pin_reveal():
    pins = session.get('pending_pins')
    if not pins: return redirect(url_for('auth.login_page'))
    session.pop('pending_pins', None)
    return render_template('pin_reveal.html', pins=pins)
