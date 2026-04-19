from flask import Blueprint, render_template, request, jsonify, redirect, url_for, session
from app.database import database
from app.web import oauth
from app.core.logging import logger
import json
import secrets
import time

auth_bp = Blueprint('auth', __name__)

def apply_user_credentials(email: str):
    try:
        from app.core.config import settings
        creds = database.get_user_credentials(email)
        if creds and creds.get('tg_api_id'):
            if settings.mock_telegram:
                from app.services.mocks.mock_telegram import start_telegram_in_thread, telegram_is_authorized
            else:
                from app.services.telegram import start_telegram_in_thread, telegram_is_authorized
            start_telegram_in_thread(email)
            logger.info(f"Started Telegram integration for {email}")
            
            # Check if user needs to authorize
            import time
            time.sleep(0.5)  # Give thread a moment to initialize
            try:
                is_authorized = telegram_is_authorized(email)
                if is_authorized:
                    message = '✅ Telegram integration started and authorized'
                else:
                    message = '✅ Telegram integration started. Please authorize via <a href="/telegram-auth">Telegram Authorization</a>'
            except Exception:
                message = '✅ Telegram integration started'
                is_authorized = False
            
            # Notify user via toast
            try:
                from app.web import socketio
                socketio.emit('toast', {
                    'message': message,
                    'type': 'success' if is_authorized else 'warning',
                    'duration': 5000
                }, room=email)
            except Exception:
                pass
        else:
            logger.debug(f"No Telegram credentials configured for {email}")
    except Exception as e:
        logger.error(f"Error applying credentials for {email}: {e}")
        # Optionally notify user via toast
        try:
            from app.web import socketio
            socketio.emit('toast', {
                'message': f'⚠️ Failed to initialize Telegram integration: {str(e)[:100]}',
                'type': 'warning',
                'duration': 5000
            }, room=email)
        except Exception:
            pass

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
        
        # Clear Gmail verification status
        try:
            from app.tools.email_tools import _gmail_verified, _gmail_lock
            with _gmail_lock:
                _gmail_verified.discard(email)
        except Exception:
            pass
        
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
                'tg_phone': data.get('tg_phone', '').strip(),
                'password': password,
                'audio_password': data.get('secret_audio', '').lower().strip()
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
            logger.info(f'Gmail linking flow initiated. Session user: {session.get("user")}')
            session.pop('linking_gmail', None)
            current_user_email = session.get('user', {}).get('email')
            if current_user_email:
                # Ensure user exists in database (they should, but safety check)
                logger.debug(f'Checking if user exists: {current_user_email}')
                user_record = database.get_user_by_email(current_user_email)
                if not user_record:
                    # Create user record if missing (shouldn't happen but safety net)
                    name = session.get('user', {}).get('name', current_user_email.split('@')[0])
                    password = secrets.token_urlsafe(16)
                    audio_pass = database.suggest_audio_word()
                    try:
                        success_create, msg = database.create_user(name, current_user_email, password, secret_audio=audio_pass, created_via_oauth=False)
                        if success_create:
                            logger.info(f'Created missing user record for {current_user_email} during Gmail linking')
                        else:
                            logger.error(f'Failed to create user record for {current_user_email}: {msg}')
                            # Still proceed - maybe user exists now due to race condition
                    except Exception as e:
                        logger.error(f'Exception creating user record for {current_user_email}: {e}')
                        # Continue anyway - maybe user exists now
                
                token_json = json.dumps(token)
                success, message = database.store_gmail_token(current_user_email, token_json)
                if success:
                    logger.info(f'Gmail token linked successfully for {current_user_email}')
                    
                    # Ensure pins are set for this user
                    existing_pins = database.get_user_pins(current_user_email)
                    gmail_pin = existing_pins.get('gmail_pin') if existing_pins else None
                    telegram_pin = existing_pins.get('telegram_pin') if existing_pins else None
                    
                    # If no Gmail PIN exists, generate one
                    if not gmail_pin:
                        new_pins = database.generate_pins(tg_included=False)
                        gmail_pin = new_pins['gmail_pin']
                        # Update database with new Gmail PIN (keep existing Telegram PIN if any)
                        database.store_pins(current_user_email, gmail_pin, telegram_pin)
                        logger.info(f'Generated new Gmail PIN for {current_user_email}')
                    
                    # Ensure pending_pins session variable includes both pins
                    pending_pins = session.get('pending_pins', {})
                    if not pending_pins.get('email'):
                        pending_pins['email'] = current_user_email
                    if not pending_pins.get('name'):
                        pending_pins['name'] = session.get('user', {}).get('name', current_user_email.split('@')[0])
                    pending_pins['gmail_pin'] = gmail_pin
                    if telegram_pin:
                        pending_pins['telegram_pin'] = telegram_pin
                    # Generate password and audio_password for users linking Gmail to existing account
                    if not pending_pins.get('password'):
                        pending_pins['password'] = secrets.token_urlsafe(16)
                    if not pending_pins.get('audio_password'):
                        pending_pins['audio_password'] = database.suggest_audio_word()
                    session['pending_pins'] = pending_pins
                    session.modified = True
                    logger.debug(f'[Gmail linking] Updated pending_pins with keys: {list(pending_pins.keys())}, has_password: {bool(pending_pins.get("password"))}')
                    
                    # Show success toast
                    try:
                        from app.web import socketio
                        socketio.emit('toast', {
                            'message': '✅ Gmail linked successfully',
                            'type': 'success',
                            'duration': 3000
                        }, room=current_user_email)
                    except Exception:
                        pass
                else:
                    logger.error(f'Failed to link Gmail token for {current_user_email}: {message}')
                database.log_activity(current_user_email, 'link_gmail', 'google_oauth')
                return redirect('/setup-integrations?oauth=success')

        # Case 2: Standard Login/Register flow
        user_record = database.get_user_by_email(email)
        is_new_user = False

        if not user_record:
            is_new_user = True
            audio_pass = database.suggest_audio_word()
            random_pass = secrets.token_urlsafe(16)
            
            database.create_user(name, email, random_pass, secret_audio=audio_pass, created_via_oauth=True)
            
            pins = database.generate_pins(tg_included=True)
            pins.update({
                'email': email,
                'name': name,
                'password': random_pass,
                'audio_password': audio_pass,
                'is_oauth_signup': True
            })
            gmail_pin = str(pins.get('gmail_pin', '0000'))
            telegram_pin = str(pins.get('telegram_pin') or '')
            database.store_pins(email, gmail_pin, telegram_pin)
            
            session['pending_pins'] = pins
            session.modified = True
            logger.debug(f'[OAuth new user] Set pending_pins with keys: {list(pins.keys())}, has_password: {bool(pins.get("password"))}')
            user_record = database.get_user_by_email(email)

        # Store Gmail API token
        token_json = json.dumps(token)
        success, message = database.store_gmail_token(email, token_json)
        if success:
            logger.info(f'Gmail token stored successfully for {email}')
            # Verify token can be retrieved
            creds = database.get_user_credentials(email)
            if creds and creds.get('gmail_token'):
                logger.info(f'Gmail token verified for {email}, length: {len(creds["gmail_token"])}')
                # Show success toast
                try:
                    from app.web import socketio
                    socketio.emit('toast', {
                        'message': '✅ Gmail connected successfully',
                        'type': 'success',
                        'duration': 3000
                    }, room=email)
                except Exception:
                    pass
            else:
                logger.error(f'Gmail token verification failed for {email} - token not retrievable')
                # Show warning toast
                try:
                    from app.web import socketio
                    socketio.emit('toast', {
                        'message': '⚠️ Gmail token stored but verification failed',
                        'type': 'warning',
                        'duration': 5000
                    }, room=email)
                except Exception:
                    pass
        else:
            logger.error(f'Failed to store Gmail token for {email}: {message}')
            # Show error toast
            try:
                from app.web import socketio
                socketio.emit('toast', {
                    'message': f'⚠️ Failed to store Gmail token: {message[:100]}',
                    'type': 'error',
                    'duration': 5000
                }, room=email)
            except Exception:
                pass

        # Log in the user
        session['user'] = {'name': user_record['name'], 'email': email, 'picture': user_info.get('picture')}
        session['voice_auth'] = True
        database.log_session(email, force_insert=True)
        apply_user_credentials(email)
        database.log_activity(email, 'register' if is_new_user else 'login', 'google_oauth')

        # Only redirect to setup-integrations for genuinely new users created in this OAuth callback
        if is_new_user:
            return redirect(url_for('auth.setup_integrations') + '?oauth=success')

        return redirect(('/admin' if database.is_admin(email) else '/dashboard') + '?oauth=success')
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
    logger.debug(f'[pin-reveal] pending_pins keys: {list(pins.keys()) if pins else None}, has_password: {bool(pins and pins.get("password"))}')
    if pins and pins.get('email') and pins.get('email') != current_email:
        session.pop('pending_pins', None)
        return redirect('/setup-integrations')
    if not pins: return redirect('/setup-integrations')

    # For Google OAuth users: regenerate temp password / audio password if missing
    if not pins.get('password') and current_email:
        # Only regenerate a temp password for accounts created via OAuth
        if database.is_created_via_oauth(current_email):
            creds = database.get_user_credentials(current_email)
            if creds and creds.get('gmail_token'):
                new_pass = secrets.token_urlsafe(16)
                database.force_reset_password(current_email, new_pass)
                pins['password'] = new_pass
                logger.info(f'[pin-reveal] Regenerated temp password for OAuth user {current_email}')

    if not pins.get('audio_password') and current_email:
        # Only regenerate audio password for accounts created via OAuth
        if database.is_created_via_oauth(current_email):
            creds = database.get_user_credentials(current_email)
            if creds and creds.get('gmail_token'):
                from app.database.utils import suggest_audio_word
                audio_pass = suggest_audio_word()
                database.force_reset_audio(current_email, audio_pass)
                pins['audio_password'] = audio_pass
                logger.info(f'[pin-reveal] Regenerated audio password for OAuth user {current_email}')

    if pins.get('password') or pins.get('audio_password'):
        session['pending_pins'] = pins
        session.modified = True

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
    logger.debug(f'[api-has-pending-pins] email={email}, pins_keys={list(pins.keys()) if pins else None}, has_pins={has_pins}')
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
        pending = dict(session.get('pending_pins') or {})
        pending['telegram_pin'] = tg_pin
        pending['email'] = email
        if not pending.get('name'):
            pending['name'] = session.get('user', {}).get('name', email.split('@')[0])
        if not pending.get('gmail_pin'):
            pending['gmail_pin'] = gmail_pin
        session['pending_pins'] = pending
        session.modified = True
        logger.debug(f'[save-telegram-creds] Updated pending_pins with keys: {list(session["pending_pins"].keys())}, has_password: {bool(session["pending_pins"].get("password"))}')
        
        # Start Telegram thread now that credentials are saved
        try:
            apply_user_credentials(email)
            # Notify user via toast
            from app.web import socketio
            socketio.emit('toast', {
                'message': '✅ Telegram credentials saved. Starting integration...',
                'type': 'success',
                'duration': 3000
            }, room=email)
            logger.info(f"Started Telegram integration after credential save for {email}")
        except Exception as e:
            logger.error(f"Failed to start Telegram after credential save: {e}")
            # Notify user of failure
            try:
                from app.web import socketio
                socketio.emit('toast', {
                    'message': f'⚠️ Failed to start Telegram: {str(e)[:100]}',
                    'type': 'warning',
                    'duration': 5000
                }, room=email)
            except:
                pass
    
    return jsonify({'status': 'ok' if ok else 'error'})


@auth_bp.route('/debug/credentials')
def debug_credentials():
    """Debug endpoint for admins to check credential status."""
    from flask import jsonify
    from app.database import database
    from app.core.config import settings
    
    # Only allow in development
    if settings.FLASK_ENV == 'production':
        return jsonify({'error': 'Not available in production'}), 403
    
    email = request.args.get('email')
    if not email:
        return jsonify({'error': 'Email parameter required'}), 400
    
    creds = database.get_user_credentials(email)
    if not creds:
        return jsonify({'error': 'User not found'}), 404
    
    # Mask sensitive data
    masked_creds = {}
    for key, value in creds.items():
        if value and isinstance(value, str):
            if key in ('gmail_token', 'tg_api_hash'):
                masked_creds[key] = f'{value[:10]}...' if len(value) > 10 else value
            else:
                masked_creds[key] = value
        else:
            masked_creds[key] = value
    
    return jsonify({
        'email': email,
        'has_gmail_token': bool(creds.get('gmail_token')),
        'has_telegram': bool(creds.get('tg_api_id') and creds.get('tg_api_hash')),
        'credentials': masked_creds
    })
