from flask import Blueprint, render_template, request, jsonify, redirect, url_for, session
from app.database import database
from app.web import oauth
import json
import secrets

auth_bp = Blueprint('auth', __name__)

def apply_user_credentials(email: str):
    try:
        from app.core.config import settings
        creds = database.get_user_credentials(email)
        if creds and creds.get('tg_api_id'):
            if settings.mock_telegram:
                from app.services.mocks.mock_telegram import start_telegram_in_thread
            else:
                from app.services.telegram import start_telegram_in_thread
            start_telegram_in_thread(email)
    except Exception as e:
        print(f"Error applying credentials for {email}: {e}")

@auth_bp.route('/')
def login_page():
    from_signup = request.args.get('from') == 'signup'
    error = request.args.get('error', '')
    return render_template('login.html', from_signup=from_signup, error=error)

@auth_bp.route('/', methods=['POST'])
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
            return jsonify({
                'status': 'success',
                'name': name,
                'redirect': '/admin' if database.is_admin(email) else '/dashboard'
            })
        return jsonify({'status': 'failed', 'message': 'Audio password not recognised. Please try again.'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

def logout_user(email):
    """Clean up user session and integrations."""
    if email:
        database.log_activity(email, 'logout', '')
        # Stop Telegram background logic
        try:
            from app.core.config import settings
            if settings.mock_telegram:
                from app.services.mocks.mock_telegram import stop_telegram_in_thread
            else:
                from app.services.telegram import stop_telegram_in_thread
            stop_telegram_in_thread(email)
        except Exception as e:
            print(f"Error stopping credentials for {email}: {e}")
    session.clear()

@auth_bp.route('/logout', methods=['GET', 'POST'])
def logout():
    email = session.get('user', {}).get('email')
    logout_user(email)
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
            '', '',  # gmail_address, gmail_app_pass (now set via integrations page)
            data.get('tg_api_id', '').strip(), 
            data.get('tg_api_hash', '').strip(), 
            data.get('tg_phone', '').strip()
        )
        if success:
            pins = database.generate_pins(tg_included=bool(data.get('tg_api_id') and data.get('tg_api_hash')))
            gmail_pin = str(pins.get('gmail_pin', '0000'))
            telegram_pin = str(pins.get('telegram_pin') or '')
            database.store_pins(email, gmail_pin, telegram_pin)
            
            pending_pins = {
                'email': email, 'name': name, 
                'gmail_pin': gmail_pin, 
                'telegram_pin': telegram_pin,
                'tg_phone': data.get('tg_phone', '').strip()
            }
            if data.get('is_admin') and data.get('admin_password', '').strip() == 'infosys':
                database.add_admin(email)
                pending_pins['is_admin'] = True
            
            session['pending_pins'] = pending_pins
            
            # Auto-login after registration so they can access setup-integrations
            session['user'] = {'name': name, 'email': email}
            session['voice_auth'] = True
            database.log_session(email, force_insert=True)
            apply_user_credentials(email)
            database.log_activity(email, 'register', 'keyboard')
            
            return jsonify({'status': 'success', 'message': 'Registration successful!', 'redirect': '/setup-integrations'})
        return jsonify({'status': 'error', 'message': message})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@auth_bp.route('/auth/google')
def auth_google():
    if 'user' in session:
        session['linking_gmail'] = True
    return oauth.google.authorize_redirect(
        url_for('auth.auth_google_callback', _external=True),
        prompt='consent',
        access_type='offline'
    )

@auth_bp.route('/auth/google/callback')
def auth_google_callback():
    try:
        token = oauth.google.authorize_access_token()
        user_info = token.get('userinfo') or oauth.google.get('https://openidconnect.googleapis.com/v1/userinfo').json()
        
        email = user_info.get('email')
        name = user_info.get('name') or email.split('@')[0]
        
        # Case 1: User is already logged in and linking their Gmail
        if session.get('linking_gmail'):
            session.pop('linking_gmail', None)
            current_user_email = session.get('user', {}).get('email')
            if current_user_email:
                token_json = json.dumps(token)
                database.store_gmail_token(current_user_email, token_json)
                database.log_activity(current_user_email, 'link_gmail', 'google_oauth')
                return redirect('/setup-integrations')

        # Case 2: Standard Login/Register flow
        user_record = database.get_user_by_email(email)
        is_new_user = False

        if not user_record:
            is_new_user = True
            audio_pass = database.suggest_audio_word()
            random_pass = secrets.token_urlsafe(16)
            
            database.create_user(name, email, random_pass, secret_audio=audio_pass)
            
            pins = database.generate_pins(tg_included=True)
            pins.update({
                'email': email,
                'name': name,
                'password': random_pass,
                'audio_password': audio_pass
            })
            gmail_pin = str(pins.get('gmail_pin', '0000'))
            telegram_pin = str(pins.get('telegram_pin') or '')
            database.store_pins(email, gmail_pin, telegram_pin)
            
            session['pending_pins'] = pins
            user_record = database.get_user_by_email(email)

        # Store Gmail API token
        token_json = json.dumps(token)
        database.store_gmail_token(email, token_json)

        # Log in the user
        session['user'] = {'name': user_record['name'], 'email': email, 'picture': user_info.get('picture')}
        session['voice_auth'] = True
        database.log_session(email, force_insert=True)
        apply_user_credentials(email)
        database.log_activity(email, 'register' if is_new_user else 'login', 'google_oauth')

        # Only redirect to setup-integrations for genuinely new users created in this OAuth callback
        if is_new_user:
            return redirect(url_for('auth.setup_integrations'))

        return redirect('/admin' if database.is_admin(email) else '/dashboard')
    except Exception as e:
        import traceback
        print(f"OAuth Error: {e}")
        traceback.print_exc()
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
    current_email = session.get('user', {}).get('email')
    if pins and pins.get('email') and pins.get('email') != current_email:
        session.pop('pending_pins', None)
        return redirect('/setup-integrations')
    if not pins: return redirect('/setup-integrations')
    return render_template('pin_reveal.html', pins=pins)

@auth_bp.route('/setup-integrations')
def setup_integrations():
    email = session.get('user', {}).get('email')
    if not email:
        return redirect('/')
    
    creds = database.get_user_credentials(email)
    has_gmail = bool(creds and creds.get('gmail_token'))
    tg_phone = creds.get('tg_phone') if creds else None
    
    return render_template('setup_integrations.html', 
                           email=email, 
                           has_gmail=has_gmail, 
                           tg_phone=tg_phone)

@auth_bp.route('/finish-signup', methods=['POST'])
def finish_signup():
    return jsonify({'status': 'ok'})


@auth_bp.route('/api/has-pending-pins')
def api_has_pending_pins():
    email = session.get('user', {}).get('email')
    pins = session.get('pending_pins', {})
    has_pins = bool(pins and pins.get('email') == email and (pins.get('gmail_pin') or pins.get('telegram_pin')))
    return jsonify({'has_pending_pins': has_pins})


@auth_bp.route('/api/clear-pending-pins', methods=['POST'])
def api_clear_pending_pins():
    session.pop('pending_pins', None)
    return jsonify({'status': 'ok'})


@auth_bp.route('/save-telegram-creds', methods=['POST'])
def save_telegram_creds():
    email = session.get('user', {}).get('email')
    if not email:
        return jsonify({'status': 'error', 'message': 'Not logged in'})
    data = request.get_json()
    api_id = data.get('tg_api_id', '')
    api_hash = data.get('tg_api_hash', '')
    phone = data.get('tg_phone', '')
    ok = database.save_telegram_creds(email, api_id, api_hash, phone)
    if ok:
        pins = database.generate_pins(tg_included=True)
        tg_pin = pins['telegram_pin']
        
        existing_pins = database.get_user_pins(email)
        gmail_pin = existing_pins.get('gmail_pin', '0000') if existing_pins else '0000'
        
        database.store_pins(email, gmail_pin, tg_pin)
        session['pending_pins'] = session.get('pending_pins', {})
        session['pending_pins']['telegram_pin'] = tg_pin
        session['pending_pins']['email'] = email
    return jsonify({'status': 'ok' if ok else 'error'})
