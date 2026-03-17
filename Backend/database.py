# ----------------------
# BACKEND — database.py
# ----------------------
# Handles all SQLite database operations for the assistant:
#   - init_db()          : Creates the users table if it doesn't exist
#   - create_user()      : Registers a new user (called by /register in web_login.py)
#   - verify_user()      : Checks login credentials (email + password)
#   - verify_audio()     : Checks audio password against stored value
#   - get_user_by_email(): Fetches a user record by email
#   - suggest_audio_word(): Suggests a random pronounceable secret audio word
#
# WHY SQLite?
#   No server setup needed — the entire database is a single .db file
#   stored locally. Perfect for a local voice assistant application.
#
# WHY bcrypt for passwords?
#   Storing plain passwords is a severe security risk. bcrypt hashes
#   passwords with a salt so even if the .db file is stolen, passwords
#   can't be recovered. It also has a built-in cost factor that makes
#   brute-force attacks slow.
#
# Requirements:
#   pip install bcrypt
# ----------------------

import sqlite3,bcrypt,os,random ,secrets,string
from datetime import datetime

# ----------------------
# Database file location
# ----------------------
# Stored in the Backend/ folder next to this file.
# Change USER_DB_PATH if you want it elsewhere.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USER_DB_PATH  = os.path.join(BASE_DIR, 'users.db')
ADMIN_DB_PATH = os.path.join(BASE_DIR, 'admins.db')


# ----------------------
# Secret Audio Word Bank
# ----------------------
# Words chosen to be:
#   ✓ Easy to pronounce clearly (no silent letters, no ambiguous sounds)
#   ✓ Uncommon enough to not be guessed easily
#   ✓ Distinct enough that Whisper transcribes them reliably
#   ✓ 2–3 syllables for natural speech rhythm
#
# Grouped by theme so suggestions feel intentional, not random gibberish.

AUDIO_WORD_BANK = [
    # Nature
    "cobalt", "falcon", "granite", "maple", "cedar", "amber", "canyon",
    "ember", "glacial", "haven", "inlet", "juniper", "kindle", "lumen",
    "mossy", "nimbus", "obsidian", "pebble", "quartz", "russet",

    # Space / Science
    "nebula", "pulsar", "zenith", "solstice", "corona", "vortex",
    "photon", "kelvin", "titan", "cosmos", "lunar", "stellar",

    # Strong / Distinct sounds (good for voice recognition)
    "bastion", "cipher", "delta", "echo", "foxtrot", "vector",
    "kestrel", "phantom", "ridgeback", "summit", "tundra", "ultra",

    # Two-word combos (harder to guess, still pronounceable)
    "blue falcon", "red cedar", "dark ember", "cold zenith",
    "swift maple", "iron cliff", "pale comet", "loud thunder",
]

#Returns a random secret audio password suggestion from the word bank.
#Called by the signup page JS to pre-fill the secret audio field.
#Returns:
#A randomly selected word or phrase string.
def suggest_audio_word() -> str: 
    return random.choice(AUDIO_WORD_BANK)


# ----------------------
# Database Initialization - User
# ----------------------

def init_db():
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

        # ── Migrate existing DB — add columns if they don't exist ──
        existing = [row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()]
        for col, definition in [
            ('gmail_address',  'TEXT'),
            ('gmail_app_pass', 'TEXT'),
            ('tg_api_id',      'TEXT'),
            ('tg_api_hash',    'TEXT'),
            ('tg_phone',       'TEXT'),
            ('role',           "TEXT NOT NULL DEFAULT 'user'"),
            ('gmail_pin',      'TEXT'),
            ('telegram_pin',   'TEXT'),
        ]:
            if col not in existing:
                try:
                    conn.execute(f'ALTER TABLE users ADD COLUMN {col} {definition}')
                    conn.commit()
                except Exception as e:
                    print(f'[DB] Migration warning for {col}: {e}')

    print(f"[DB] Database initialised at: {USER_DB_PATH}")
    init_admin_db()

# # =================================================
# DATABASE - ADMIN
# # =================================================
def init_admin_db():
    """
    Separate admin database — stores:
    - activity_log: every user action
    - admin_users: who has admin access
    """
    with sqlite3.connect(ADMIN_DB_PATH) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS activity_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                email      TEXT    NOT NULL,
                action     TEXT    NOT NULL,
                detail     TEXT,
                logged_at  TEXT    NOT NULL
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS admin_users (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                email      TEXT    NOT NULL UNIQUE,
                created_at TEXT    NOT NULL
            )
        ''')
        conn.commit()
    print(f"[DB] Admin database initialised at: {ADMIN_DB_PATH}")

def generate_pins(tg_included: bool = False) -> dict:
    """
    Generate service PINs for a new user.
    Gmail PIN is always generated.
    Telegram PIN only if user provided Telegram details.
    Returns plain PINs — show once, then store hashed.
    """
    def make_pin(length=4):
        return ''.join(secrets.choice(string.digits) for _ in range(length))

    pins = {'gmail_pin': make_pin()}
    if tg_included:
        pins['telegram_pin'] = make_pin()
    return pins


def store_pins(email: str, gmail_pin: str, telegram_pin: str = None) -> tuple[bool, str]:
    """Store hashed PINs for a user after generation."""
    try:
        hashed_gmail = bcrypt.hashpw(
            gmail_pin.encode('utf-8'), bcrypt.gensalt()
        ).decode('utf-8')

        hashed_tg = None
        if telegram_pin:
            hashed_tg = bcrypt.hashpw(
                telegram_pin.encode('utf-8'), bcrypt.gensalt()
            ).decode('utf-8')

        with sqlite3.connect(USER_DB_PATH) as conn:
            # Add columns if they don't exist
            existing = [row[1] for row in conn.execute(
                "PRAGMA table_info(users)").fetchall()]
            if 'gmail_pin' not in existing:
                conn.execute('ALTER TABLE users ADD COLUMN gmail_pin TEXT')
            if 'telegram_pin' not in existing:
                conn.execute('ALTER TABLE users ADD COLUMN telegram_pin TEXT')
            conn.commit()

            conn.execute(
                'UPDATE users SET gmail_pin = ?, telegram_pin = ? WHERE email = ?',
                (hashed_gmail, hashed_tg, email.strip().lower())
            )
            conn.commit()
        return True, 'PINs stored.'
    except Exception as e:
        print(f'[DB] store_pins error: {e}')
        return False, str(e)


def verify_pin(email: str, service: str, pin: str) -> bool:
    """Verify a service PIN for a user. service = 'gmail' or 'telegram'."""
    try:
        col = f'{service}_pin'
        with sqlite3.connect(USER_DB_PATH) as conn:
            cursor = conn.execute(
                f'SELECT {col} FROM users WHERE email = ?',
                (email.strip().lower(),)
            )
            row = cursor.fetchone()
        if not row or not row[0]:
            return False
        return bcrypt.checkpw(pin.encode('utf-8'), row[0].encode('utf-8'))
    except Exception:
        return False

def log_activity(email: str, action: str, detail: str = ''):
    """Log every user action to the admin DB activity_log."""
    try:
        with sqlite3.connect(ADMIN_DB_PATH) as conn:
            conn.execute(
                'INSERT INTO activity_log (email, action, detail, logged_at) VALUES (?, ?, ?, ?)',
                (email.strip().lower(), action, detail,
                 datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            )
            conn.commit()
    except Exception as e:
        print(f'[DB] log_activity error: {e}')


def is_admin(email: str) -> bool:
    """Check if email has admin access."""
    try:
        with sqlite3.connect(ADMIN_DB_PATH) as conn:
            cur = conn.execute(
                'SELECT id FROM admin_users WHERE email = ?',
                (email.strip().lower(),)
            )
            return cur.fetchone() is not None
    except Exception:
        return False


def add_admin(email: str) -> tuple[bool, str]:
    """Grant admin access to an email."""
    try:
        with sqlite3.connect(ADMIN_DB_PATH) as conn:
            conn.execute(
                'INSERT OR IGNORE INTO admin_users (email, created_at) VALUES (?, ?)',
                (email.strip().lower(), datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            )
            conn.commit()
        return True, f'{email} is now an admin.'
    except Exception as e:
        return False, str(e)


def remove_admin(email: str) -> tuple[bool, str]:
    """Revoke admin access."""
    try:
        with sqlite3.connect(ADMIN_DB_PATH) as conn:
            conn.execute(
                'DELETE FROM admin_users WHERE email = ?',
                (email.strip().lower(),)
            )
            conn.commit()
        return True, f'{email} removed from admins.'
    except Exception as e:
        return False, str(e)


def get_all_users() -> list[dict]:
    """Returns all registered users with session count."""
    try:
        with sqlite3.connect(USER_DB_PATH) as conn:
            cursor = conn.execute(
                'SELECT id, name, email, created_at FROM users ORDER BY created_at DESC'
            )
            rows = cursor.fetchall()
        users = []
        for r in rows:
            # Get session count
            try:
                with sqlite3.connect(ADMIN_DB_PATH) as conn2:
                    cur = conn2.execute(
                        "SELECT COUNT(*) FROM activity_log WHERE email = ? AND action = 'login'",
                        (r[2],)
                    )
                    sessions = cur.fetchone()[0]
            except Exception:
                sessions = 0
            # Check if admin
            admin = is_admin(r[2])
            users.append({
                'id': r[0], 'name': r[1], 'email': r[2],
                'created_at': r[3], 'sessions': sessions, 'is_admin': admin
            })
        return users
    except Exception as e:
        print(f'[DB] get_all_users error: {e}')
        return []


def get_active_users(minutes: int = 30) -> list[dict]:
    """
    Returns users who have logged in within the last N minutes.
    Uses sessions table in user DB.
    """
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


def get_activity_log(email: str = None, action: str = None,
                     limit: int = 100) -> list[dict]:
    """Fetch activity log from admin DB with optional filters."""
    try:
        query  = 'SELECT email, action, detail, logged_at FROM activity_log'
        params = []
        where  = []
        if email:
            where.append('email = ?')
            params.append(email.strip().lower())
        if action:
            where.append('action = ?')
            params.append(action)
        if where:
            query += ' WHERE ' + ' AND '.join(where)
        query += ' ORDER BY logged_at DESC LIMIT ?'
        params.append(limit)

        with sqlite3.connect(ADMIN_DB_PATH) as conn:
            cursor = conn.execute(query, params)
            rows   = cursor.fetchall()
        return [{'email': r[0], 'action': r[1],
                 'detail': r[2], 'logged_at': r[3]} for r in rows]
    except Exception as e:
        print(f'[DB] get_activity_log error: {e}')
        return []


def admin_delete_user(email: str) -> tuple[bool, str]:
    """Admin force-delete a user without password confirmation."""
    try:
        email = email.strip().lower()
        with sqlite3.connect(USER_DB_PATH) as conn:
            conn.execute('DELETE FROM users    WHERE email = ?', (email,))
            conn.execute('DELETE FROM sessions WHERE email = ?', (email,))
            conn.commit()
        with sqlite3.connect(ADMIN_DB_PATH) as conn:
            conn.execute('DELETE FROM admin_users   WHERE email = ?', (email,))
            conn.execute('DELETE FROM activity_log  WHERE email = ?', (email,))
            conn.commit()
        log_activity('admin', 'admin_delete_user', f'deleted: {email}')
        return True, f'User {email} deleted.'
    except Exception as e:
        return False, str(e)

def get_activity_count(email: str, action: str) -> int:
    """Returns the total number of times a specific action was performed by a user."""
    try:
        with sqlite3.connect(ADMIN_DB_PATH) as conn:
            cur = conn.execute(
                "SELECT COUNT(*) FROM activity_log WHERE email = ? AND action = ?",
                (email.strip().lower(), action)
            )
            return cur.fetchone()[0]
    except Exception as e:
        print(f'[DB] get_activity_count error: {e}')
        return 0

def log_session(email: str, force_insert: bool = False):
    """
    On login (force_insert=True): always insert a new session row.
    On heartbeat (force_insert=False): just update the latest row's timestamp.
    """
    try:
        email = email.strip().lower()
        now   = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with sqlite3.connect(USER_DB_PATH) as conn:
            if force_insert:
                conn.execute(
                    'INSERT INTO sessions (email, logged_at) VALUES (?, ?)',
                    (email, now)
                )
            else:
                # Update most recent session row — don't create new ones
                updated = conn.execute(
                    '''UPDATE sessions SET logged_at = ?
                       WHERE id = (
                           SELECT id FROM sessions WHERE email = ?
                           ORDER BY logged_at DESC LIMIT 1
                       )''',
                    (now, email)
                )
                if updated.rowcount == 0:
                    # No existing session — insert one
                    conn.execute(
                        'INSERT INTO sessions (email, logged_at) VALUES (?, ?)',
                        (email, now)
                    )
            conn.commit()
    except Exception as e:
        print(f'[DB] log_session error: {e}')

# ----------------------
# Create User (Registration)
# ----------------------

def create_user(name: str, email: str, password: str, secret_audio: str = '',
                gmail_address: str = '', gmail_app_pass: str = '',
                tg_api_id: str = '', tg_api_hash: str = '', tg_phone: str = '') -> tuple[bool, str]:
    try:
        hashed_password = bcrypt.hashpw(
            password.encode('utf-8'), bcrypt.gensalt()
        ).decode('utf-8')

        hashed_audio = None
        if secret_audio and secret_audio.strip():
            hashed_audio = bcrypt.hashpw(
                secret_audio.strip().lower().encode('utf-8'), bcrypt.gensalt()
            ).decode('utf-8')

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


# ----------------------
# Verify User (Keyboard Login)
# ----------------------

def verify_user(email: str, password: str) -> tuple[bool, str]:
    """
    Checks if the email exists and the password matches the stored hash.
    Used for keyboard login via the /login Flask route.

    Args:
        email:    Email address entered by user
        password: Plain text password entered by user

    Returns:
        (True,  user_name)      if credentials are valid
        (False, error_message)  if invalid
    """
    try:
        with sqlite3.connect(USER_DB_PATH) as conn:
            cursor = conn.execute(
                'SELECT name, password FROM users WHERE email = ?',
                (email.strip().lower(),)
            )
            row = cursor.fetchone()

        if not row:
            return False, 'No account found with this email.'

        name, stored_hash = row

        # bcrypt.checkpw compares the plain password against the stored hash
        if bcrypt.checkpw(password.encode('utf-8'), stored_hash.encode('utf-8')):
            print(f"[DB] Login verified: {email}")
            return True, name
        else:
            return False, 'Incorrect password.'

    except Exception as e:
        print(f"[DB] verify_user error: {e}")
        return False, f'Database error: {str(e)}'


# ----------------------
# Verify Audio Password (Voice Login)
# ----------------------

def verify_audio(spoken_word: str) -> tuple[bool, str, str]:
    """
    Checks the spoken audio password against ALL users' stored audio hashes.
    Since voice login doesn't ask for an email first, we check every user.

    Args:
        spoken_word: The word/phrase transcribed by Faster Whisper

    Returns:
        (True,  user_name)      if a matching audio password is found
        (False, error_message)  if no match
    """
    try:
        with sqlite3.connect(USER_DB_PATH) as conn:
            cursor = conn.execute(
                'SELECT name, email, secret_audio FROM users WHERE secret_audio IS NOT NULL'
            )
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


# ----------------------
# Get User by Email
# ----------------------

def get_user_by_email(email: str) -> dict | None:
    """
    Fetches a user's full record by email.
    Useful for displaying profile info after login.

    Returns:
        Dict with keys: id, name, email, created_at
        None if not found
    """
    try:
        with sqlite3.connect(USER_DB_PATH) as conn:
            cursor = conn.execute(
                'SELECT id, name, email, created_at FROM users WHERE email = ?',
                (email.strip().lower(),)
            )
            row = cursor.fetchone()

        if not row:
            return None

        return {
            'id':         row[0],
            'name':       row[1],
            'email':      row[2],
            'created_at': row[3],
        }

    except Exception as e:
        print(f"[DB] get_user_by_email error: {e}")
        return None

# ========================
# UPDATE
# ========================

# ----------------------
# Update Name
# ----------------------
def update_name(email: str, new_name: str) -> tuple[bool, str]:
    try:
        with sqlite3.connect(USER_DB_PATH) as conn:
            conn.execute(
                'UPDATE users SET name = ? WHERE email = ?',
                (new_name.strip(), email.strip().lower())
            )
            conn.commit()
        return True, f'Name updated to {new_name}.'
    except Exception as e:
        return False, f'Error: {str(e)}'


# ----------------------
# Update Password
# ----------------------
def update_password(email: str, old_password: str, new_password: str) -> tuple[bool, str]:
    try:
        success, _ = verify_user(email, old_password)
        if not success:
            return False, 'Current password is incorrect.'
        hashed = bcrypt.hashpw(
            new_password.encode('utf-8'),
            bcrypt.gensalt()
        ).decode('utf-8')
        with sqlite3.connect(USER_DB_PATH) as conn:
            conn.execute(
                'UPDATE users SET password = ? WHERE email = ?',
                (hashed, email.strip().lower())
            )
            conn.commit()
        return True, 'Password updated successfully.'
    except Exception as e:
        return False, f'Error: {str(e)}'


# ----------------------
# Update Audio Password
# ----------------------
def update_audio(email: str, new_audio: str) -> tuple[bool, str]:
    try:
        hashed = bcrypt.hashpw(
            new_audio.strip().lower().encode('utf-8'),
            bcrypt.gensalt()
        ).decode('utf-8')
        with sqlite3.connect(USER_DB_PATH) as conn:
            conn.execute(
                'UPDATE users SET secret_audio = ? WHERE email = ?',
                (hashed, email.strip().lower())
            )
            conn.commit()
        return True, 'Secret audio password updated.'
    except Exception as e:
        return False, f'Error: {str(e)}'


# ----------------------
# Delete User
# ----------------------
def delete_user(email: str, password: str) -> tuple[bool, str]:
    try:
        success, _ = verify_user(email, password)
        if not success:
            return False, 'Incorrect password. Account not deleted.'
        email = email.strip().lower()
        with sqlite3.connect(USER_DB_PATH) as conn:
            conn.execute('DELETE FROM users    WHERE email = ?', (email,))
            conn.execute('DELETE FROM sessions WHERE email = ?', (email,))
            conn.commit()
        with sqlite3.connect(ADMIN_DB_PATH) as conn:
            conn.execute('DELETE FROM admin_users  WHERE email = ?', (email,))
            conn.execute('DELETE FROM activity_log WHERE email = ?', (email,))
            conn.commit()
        return True, 'Account deleted successfully.'
    except Exception as e:
        return False, f'Error: {str(e)}'
    
    
def get_user_credentials(email: str) -> dict | None:
    """
    Fetches Gmail + Telegram credentials stored during signup.
    Called after login to configure the active session.
    """
    try:
        with sqlite3.connect(USER_DB_PATH) as conn:
            cursor = conn.execute(
                '''SELECT gmail_address, gmail_app_pass,
                          tg_api_id, tg_api_hash, tg_phone
                   FROM users WHERE email = ?''',
                (email.strip().lower(),)
            )
            row = cursor.fetchone()
        if not row:
            return None
        return {
            'gmail_address':  row[0] or '',
            'gmail_app_pass': row[1] or '',
            'tg_api_id':      row[2] or '',
            'tg_api_hash':    row[3] or '',
            'tg_phone':       row[4] or '',
        }
    except Exception as e:
        print(f'[DB] get_user_credentials error: {e}')
        return None


__all__ = [
    'init_db', 'init_admin_db', 'create_user', 'verify_user', 'verify_audio',
    'get_user_by_email', 'get_user_credentials', 'suggest_audio_word',
    'update_name', 'update_password', 'update_audio', 'delete_user',
    'log_session', 'log_activity', 'get_all_users', 'get_active_users',
    'get_activity_log', 'is_admin', 'add_admin', 'remove_admin',
    'admin_delete_user', 'USER_DB_PATH', 'ADMIN_DB_PATH',
    'generate_pins', 'store_pins', 'verify_pin'
]