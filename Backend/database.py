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

import sqlite3
import bcrypt
import os
import random
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

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
# Database Initialization
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
        ]:
            if col not in existing:
                try:
                    conn.execute(f'ALTER TABLE users ADD COLUMN {col} {definition}')
                    conn.commit()
                except Exception as e:
                    print(f'[DB] Migration warning for {col}: {e}')

    print(f"[DB] Database initialised at: {USER_DB_PATH}")

def log_session(email: str):
    try:
        with sqlite3.connect(USER_DB_PATH) as conn:
            conn.execute(
                'INSERT INTO sessions (email, logged_at) VALUES (?, ?)',
                (email.strip().lower(), datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
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

def verify_audio(spoken_word: str) -> tuple[bool, str]:
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
            return False, 'No users with audio passwords found.'

        spoken_clean = spoken_word.strip().lower().encode('utf-8')

        for name, email, stored_hash in rows:
            if bcrypt.checkpw(spoken_clean, stored_hash.encode('utf-8')):
                print(f"[DB] Audio login verified for: {email}")
                return True, name

        return False, 'Audio password not recognised.'

    except Exception as e:
        print(f"[DB] verify_audio error: {e}")
        return False, f'Database error: {str(e)}'


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
        with sqlite3.connect(USER_DB_PATH) as conn:
            conn.execute(
                'DELETE FROM users WHERE email = ?',
                (email.strip().lower(),)
            )
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
    'init_db', 'create_user', 'verify_user', 'verify_audio',
    'get_user_by_email', 'suggest_audio_word','get_user_credentials',
    'update_name', 'update_password', 'update_audio', 'delete_user', 'log_session'
]