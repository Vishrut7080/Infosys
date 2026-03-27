import sqlite3
import bcrypt
import secrets
import string
import time
from datetime import datetime
from typing import Optional, List, Dict, Tuple

from .utils import USER_DB_PATH, ADMIN_DB_PATH, suggest_audio_word
from .admin import init_admin_db, log_activity, is_admin
from app.core.logging import logger


def init_db() -> None:
    """Create users and sessions tables and run lightweight migrations."""
    with sqlite3.connect(USER_DB_PATH) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                name            TEXT    NOT NULL,
                email           TEXT    NOT NULL UNIQUE,
                password        TEXT    NOT NULL,
                secret_audio    TEXT,
                gmail_address   TEXT,
                gmail_app_pass  TEXT,
                tg_api_id       TEXT,
                tg_api_hash     TEXT,
                tg_phone        TEXT,
                role            TEXT    NOT NULL DEFAULT 'user',
                created_at      TEXT    NOT NULL
            )
        ''')
        conn.commit()
        conn.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                email      TEXT NOT NULL,
                logged_at  TEXT NOT NULL
            )
        ''')
        conn.commit()

        existing = [row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()]
        for col, definition in [
            ('gmail_address',  'TEXT'),
            ('gmail_app_pass', 'TEXT'),
            ('gmail_token',    'TEXT'),
            ('tg_api_id',      'TEXT'),
            ('tg_api_hash',    'TEXT'),
            ('tg_phone',       'TEXT'),
            ('role',           "TEXT NOT NULL DEFAULT 'user'"),
            ('gmail_pin',      'TEXT'),
            ('telegram_pin',   'TEXT'),
            ('gmail_pin_plain', 'TEXT'),
            ('telegram_pin_plain', 'TEXT'),
        ]:
            if col not in existing:
                try:
                    conn.execute(f'ALTER TABLE users ADD COLUMN {col} {definition}')
                    conn.commit()
                except Exception as e:
                    print(f'[DB] Migration warning for {col}: {e}')

    print(f"[DB] Database initialised at: {USER_DB_PATH}")
    init_admin_db()
    from .tasks import init_tasks_db
    init_tasks_db()


def generate_pins(tg_included: bool = False) -> dict:
    def make_pin(length=4):
        return ''.join(secrets.choice(string.digits) for _ in range(length))

    pins = {'gmail_pin': make_pin()}
    if tg_included:
        pins['telegram_pin'] = make_pin()
    return pins


def store_pins(email: str, gmail_pin: str, telegram_pin: str = None) -> Tuple[bool, str]:
    try:
        hashed_gmail = bcrypt.hashpw(gmail_pin.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        hashed_tg = None
        if telegram_pin:
            hashed_tg = bcrypt.hashpw(telegram_pin.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        with sqlite3.connect(USER_DB_PATH) as conn:
            existing = [row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()]
            if 'gmail_pin' not in existing:
                conn.execute('ALTER TABLE users ADD COLUMN gmail_pin TEXT')
            if 'telegram_pin' not in existing:
                conn.execute('ALTER TABLE users ADD COLUMN telegram_pin TEXT')
            if 'gmail_pin_plain' not in existing:
                conn.execute('ALTER TABLE users ADD COLUMN gmail_pin_plain TEXT')
            if 'telegram_pin_plain' not in existing:
                conn.execute('ALTER TABLE users ADD COLUMN telegram_pin_plain TEXT')
            conn.commit()

            conn.execute(
                'UPDATE users SET gmail_pin = ?, telegram_pin = ?, gmail_pin_plain = ?, telegram_pin_plain = ? WHERE email = ?',
                (hashed_gmail, hashed_tg, gmail_pin, telegram_pin, email.strip().lower())
            )
            conn.commit()
        return True, 'PINs stored.'
    except Exception as e:
        print(f'[DB] store_pins error: {e}')
        return False, str(e)


def store_gmail_token(email: str, token_json: str) -> Tuple[bool, str]:
    try:
        email_lower = email.strip().lower()
        token_length = len(token_json) if token_json else 0
        logger.info(f'[DB] Storing Gmail token for {email_lower}, token length: {token_length}')
        
        with sqlite3.connect(USER_DB_PATH) as conn:
            # Check if column exists
            existing = [row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()]
            if 'gmail_token' not in existing:
                logger.info('[DB] Adding gmail_token column to users table')
                conn.execute('ALTER TABLE users ADD COLUMN gmail_token TEXT')
                conn.commit()
            
            # Check if user exists
            cursor = conn.execute('SELECT email FROM users WHERE email = ?', (email_lower,))
            user_exists = cursor.fetchone() is not None
            if not user_exists:
                logger.error(f'[DB] User {email_lower} does not exist in users table')
                return False, f'User {email_lower} not found'
            
            # Perform update and get row count
            cursor = conn.execute('UPDATE users SET gmail_token = ? WHERE email = ?', (token_json, email_lower))
            rows_affected = cursor.rowcount
            conn.commit()
            logger.info(f'[DB] UPDATE affected {rows_affected} rows for {email_lower}')
            
            if rows_affected == 0:
                logger.error(f'[DB] UPDATE affected 0 rows for {email_lower}')
                return False, 'No user found with that email'
            
            # Add small delay to ensure commit is visible
            time.sleep(0.1)
            
            # Verify the token was stored
            cursor = conn.execute('SELECT gmail_token FROM users WHERE email = ?', (email_lower,))
            row = cursor.fetchone()
            if row and row[0]:
                stored_length = len(row[0])
                logger.info(f'[DB] Gmail token stored successfully for {email_lower}, verified length: {stored_length}')
                return True, 'Gmail token stored.'
            else:
                logger.error(f'[DB] Gmail token storage verification failed for {email_lower}')
                # Try to see what's actually in the column
                cursor2 = conn.execute('SELECT gmail_token IS NULL as is_null, length(gmail_token) as len FROM users WHERE email = ?', (email_lower,))
                row2 = cursor2.fetchone()
                if row2:
                    logger.error(f'[DB] Column details: is_null={row2[0]}, length={row2[1]}')
                return False, 'Token storage verification failed'
    except Exception as e:
        logger.error(f'[DB] store_gmail_token error for {email}: {e}')
        import traceback
        logger.error(traceback.format_exc())
        return False, str(e)


def verify_pin(email: str, service: str, pin: str) -> bool:
    try:
        col = f'{service}_pin'
        with sqlite3.connect(USER_DB_PATH) as conn:
            cursor = conn.execute(f'SELECT {col} FROM users WHERE email = ?', (email.strip().lower(),))
            row = cursor.fetchone()
        if not row or not row[0]:
            return False
        return bcrypt.checkpw(pin.encode('utf-8'), row[0].encode('utf-8'))
    except Exception:
        return False


def get_all_users() -> List[Dict]:
    try:
        with sqlite3.connect(USER_DB_PATH) as conn:
            cursor = conn.execute('SELECT id, name, email, created_at FROM users ORDER BY created_at DESC')
            rows = cursor.fetchall()
        users = []
        for r in rows:
            try:
                with sqlite3.connect(ADMIN_DB_PATH) as conn2:
                    cur = conn2.execute("SELECT COUNT(*) FROM activity_log WHERE email = ? AND action = 'login'", (r[2],))
                    sessions = cur.fetchone()[0]
            except Exception:
                sessions = 0
            admin = is_admin(r[2])
            users.append({'id': r[0], 'name': r[1], 'email': r[2], 'created_at': r[3], 'sessions': sessions, 'is_admin': admin})
        return users
    except Exception as e:
        print(f'[DB] get_all_users error: {e}')
        return []


def get_active_users(minutes: int = 30) -> List[Dict]:
    try:
        from datetime import timedelta
        cutoff = (datetime.now() - timedelta(minutes=minutes)).strftime('%Y-%m-%d %H:%M:%S')
        with sqlite3.connect(USER_DB_PATH) as conn:
            cursor = conn.execute(
                '''SELECT DISTINCT s.email, u.name, MAX(s.logged_at) as last_seen
                   FROM sessions s
                   LEFT JOIN users u ON u.email = s.email
                   WHERE s.logged_at >= ?
                   GROUP BY s.email''',
                (cutoff,)
            )
            rows = cursor.fetchall()
        return [{'email': r[0], 'name': r[1] or r[0], 'last_seen': r[2]} for r in rows]
    except Exception as e:
        print(f'[DB] get_active_users error: {e}')
        return []


def log_session(email: str, force_insert: bool = False) -> None:
    try:
        email = email.strip().lower()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with sqlite3.connect(USER_DB_PATH) as conn:
            if force_insert:
                conn.execute('INSERT INTO sessions (email, logged_at) VALUES (?, ?)', (email, now))
            else:
                updated = conn.execute(
                    '''UPDATE sessions SET logged_at = ?
                       WHERE id = (
                           SELECT id FROM sessions WHERE email = ?
                           ORDER BY logged_at DESC LIMIT 1
                       )''',
                    (now, email)
                )
                if updated.rowcount == 0:
                    conn.execute('INSERT INTO sessions (email, logged_at) VALUES (?, ?)', (email, now))
            conn.commit()
    except Exception as e:
        print(f'[DB] log_session error: {e}')


def create_user(name: str, email: str, password: str, secret_audio: str = '',
                gmail_address: str = '', gmail_app_pass: str = '',
                tg_api_id: str = '', tg_api_hash: str = '', tg_phone: str = '') -> Tuple[bool, str]:
    try:
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        hashed_audio = None
        if secret_audio and secret_audio.strip():
            hashed_audio = bcrypt.hashpw(secret_audio.strip().lower().encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        with sqlite3.connect(USER_DB_PATH) as conn:
            conn.execute(
                '''INSERT INTO users
                   (name, email, password, secret_audio,
                    gmail_address, gmail_app_pass,
                    tg_api_id, tg_api_hash, tg_phone, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (name, email.strip().lower(), hashed_password, hashed_audio,
                 gmail_address.strip(), gmail_app_pass.strip(),
                 tg_api_id.strip(), tg_api_hash.strip(), tg_phone.strip(),
                 created_at)
            )
            conn.commit()

        print(f"[DB] New user registered: {email}")
        return True, 'Registration successful!'

    except sqlite3.IntegrityError:
        return False, 'An account with this email already exists.'
    except Exception as e:
        print(f"[DB] create_user error: {e}")
        return False, f'Database error: {str(e)}'


def verify_user(email: str, password: str) -> Tuple[bool, str]:
    try:
        with sqlite3.connect(USER_DB_PATH) as conn:
            cursor = conn.execute('SELECT name, password FROM users WHERE email = ?', (email.strip().lower(),))
            row = cursor.fetchone()

        if not row:
            return False, 'No account found with this email.'

        name, stored_hash = row
        if bcrypt.checkpw(password.encode('utf-8'), stored_hash.encode('utf-8')):
            print(f"[DB] Login verified: {email}")
            return True, name
        else:
            return False, 'Incorrect password.'

    except Exception as e:
        print(f"[DB] verify_user error: {e}")
        return False, f'Database error: {str(e)}'


def verify_audio(spoken_word: str) -> Tuple[bool, str, str]:
    try:
        with sqlite3.connect(USER_DB_PATH) as conn:
            cursor = conn.execute('SELECT name, email, secret_audio FROM users WHERE secret_audio IS NOT NULL')
            rows = cursor.fetchall()

        if not rows:
            return False, 'No users with audio passwords found.', ''

        spoken_clean = spoken_word.strip().lower().encode('utf-8')

        for name, email, stored_hash in rows:
            if bcrypt.checkpw(spoken_clean, stored_hash.encode('utf-8')):
                print(f"[DB] Audio login verified for: {email}")
                return True, name, email

        return False, 'Audio password not recognised.', ''

    except Exception as e:
        print(f"[DB] verify_audio error: {e}")
        return False, f'Database error: {str(e)}', ''


def get_user_by_email(email: str) -> Optional[Dict]:
    try:
        with sqlite3.connect(USER_DB_PATH) as conn:
            cursor = conn.execute('SELECT id, name, email, created_at FROM users WHERE email = ?', (email.strip().lower(),))
            row = cursor.fetchone()

        if not row:
            return None

        return {'id': row[0], 'name': row[1], 'email': row[2], 'created_at': row[3]}

    except Exception as e:
        print(f"[DB] get_user_by_email error: {e}")
        return None


def update_name(email: str, new_name: str) -> Tuple[bool, str]:
    try:
        with sqlite3.connect(USER_DB_PATH) as conn:
            conn.execute('UPDATE users SET name = ? WHERE email = ?', (new_name.strip(), email.strip().lower()))
            conn.commit()
        return True, f'Name updated to {new_name}.'
    except Exception as e:
        return False, f'Error: {str(e)}'


def update_password(email: str, old_password: str, new_password: str) -> Tuple[bool, str]:
    try:
        success, _ = verify_user(email, old_password)
        if not success:
            return False, 'Current password is incorrect.'
        hashed = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        with sqlite3.connect(USER_DB_PATH) as conn:
            conn.execute('UPDATE users SET password = ? WHERE email = ?', (hashed, email.strip().lower()))
            conn.commit()
        return True, 'Password updated successfully.'
    except Exception as e:
        return False, f'Error: {str(e)}'


def update_audio(email: str, new_audio: str) -> Tuple[bool, str]:
    try:
        hashed = bcrypt.hashpw(new_audio.strip().lower().encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        with sqlite3.connect(USER_DB_PATH) as conn:
            conn.execute('UPDATE users SET secret_audio = ? WHERE email = ?', (hashed, email.strip().lower()))
            conn.commit()
        return True, 'Secret audio password updated.'
    except Exception as e:
        return False, f'Error: {str(e)}'


def delete_user(email: str, password: str) -> Tuple[bool, str]:
    try:
        success, _ = verify_user(email, password)
        if not success:
            return False, 'Incorrect password. Account not deleted.'
        email = email.strip().lower()
        with sqlite3.connect(USER_DB_PATH) as conn:
            conn.execute('DELETE FROM users WHERE email = ?', (email,))
            conn.execute('DELETE FROM sessions WHERE email = ?', (email,))
            conn.commit()
        with sqlite3.connect(ADMIN_DB_PATH) as conn:
            conn.execute('DELETE FROM admin_users WHERE email = ?', (email,))
            conn.execute('DELETE FROM activity_log WHERE email = ?', (email,))
            conn.commit()
        return True, 'Account deleted successfully.'
    except Exception as e:
        return False, f'Error: {str(e)}'


def save_telegram_creds(email: str, api_id: str, api_hash: str, phone: str) -> bool:
    try:
        email_lower = email.strip().lower()
        logger.info(f'[DB] Saving Telegram credentials for {email_lower}')
        with sqlite3.connect(USER_DB_PATH) as conn:
            conn.execute(
                'UPDATE users SET tg_api_id = ?, tg_api_hash = ?, tg_phone = ? WHERE email = ?',
                (api_id.strip(), api_hash.strip(), phone.strip(), email_lower)
            )
            conn.commit()
            
            # Verify the credentials were stored
            cursor = conn.execute(
                'SELECT tg_api_id, tg_api_hash, tg_phone FROM users WHERE email = ?',
                (email_lower,)
            )
            row = cursor.fetchone()
            if row and row[0] and row[1]:
                logger.info(f'[DB] Telegram credentials saved and verified for {email_lower}')
                return True
            else:
                logger.error(f'[DB] Telegram credentials verification failed for {email_lower}')
                return False
    except Exception as e:
        logger.error(f'[DB] save_telegram_creds error for {email}: {e}')
        return False


def get_user_credentials(email: str) -> Optional[Dict]:
    try:
        email_lower = email.strip().lower()
        with sqlite3.connect(USER_DB_PATH) as conn:
            cursor = conn.execute(
                '''SELECT gmail_address, gmail_app_pass, tg_api_id, tg_api_hash, tg_phone, gmail_token
                   FROM users WHERE email = ?''',
                (email_lower,)
            )
            row = cursor.fetchone()
        if not row:
            logger.debug(f'[DB] No credentials found for {email_lower}')
            return None
        
        creds = {
            'gmail_address': row[0] or '',
            'gmail_app_pass': row[1] or '',
            'tg_api_id': row[2] or '',
            'tg_api_hash': row[3] or '',
            'tg_phone': row[4] or '',
            'gmail_token': row[5] or None,
        }
        
        # Log token presence
        has_gmail_token = bool(row[5])
        has_tg_api = bool(row[2] and row[3])
        logger.debug(f'[DB] Credentials for {email_lower}: gmail_token={has_gmail_token}, telegram={has_tg_api}')
        return creds
    except Exception as e:
        logger.error(f'[DB] get_user_credentials error for {email}: {e}')
        return None


def get_user_pins(email: str) -> Optional[Dict]:
    try:
        with sqlite3.connect(USER_DB_PATH) as conn:
            cursor = conn.execute(
                'SELECT gmail_pin_plain, telegram_pin_plain FROM users WHERE email = ?',
                (email.strip().lower(),)
            )
            row = cursor.fetchone()
        if not row:
            return None
        return {
            'gmail_pin': row[0] or '',
            'telegram_pin': row[1] or '',
        }
    except Exception as e:
        print(f'[DB] get_user_pins error: {e}')
        return None
