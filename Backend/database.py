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
# Change DB_PATH if you want it elsewhere.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, 'users.db')


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


def suggest_audio_word() -> str:
    """
    Returns a random secret audio password suggestion from the word bank.
    Called by the signup page JS to pre-fill the secret audio field.

    Returns:
        A randomly selected word or phrase string.
    """
    return random.choice(AUDIO_WORD_BANK)


# ----------------------
# Database Initialization
# ----------------------

def init_db():
    """
    Creates the 'users' table if it doesn't already exist.
    Safe to call multiple times — uses IF NOT EXISTS.
    Should be called once when the Flask server starts.

    Table schema:
        id          : Auto-incrementing primary key
        name        : User's full name
        email       : Unique email address (used as login identifier)
        password    : bcrypt-hashed password (never stored plain)
        secret_audio: bcrypt-hashed audio password for voice login
        created_at  : Timestamp of account creation
    """
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                name         TEXT    NOT NULL,
                email        TEXT    NOT NULL UNIQUE,
                password     TEXT    NOT NULL,
                secret_audio TEXT,
                created_at   TEXT    NOT NULL
            )
        ''')
        conn.commit()
    print(f"[DB] Database initialised at: {DB_PATH}")


# ----------------------
# Create User (Registration)
# ----------------------

def create_user(name: str, email: str, password: str, secret_audio: str = '') -> tuple[bool, str]:
    """
    Registers a new user in the database.
    Hashes both the password and secret_audio before storing.

    Args:
        name:         Full name
        email:        Email address (must be unique)
        password:     Plain text password (will be hashed)
        secret_audio: Plain text audio password (will be hashed, optional)

    Returns:
        (True,  'Registration successful!')  on success
        (False, error_message)               on failure
    """
    try:
        # Hash the password with bcrypt
        # bcrypt.gensalt() generates a random salt — each hash is unique
        # even if two users have the same password
        hashed_password = bcrypt.hashpw(
            password.encode('utf-8'),
            bcrypt.gensalt()
        ).decode('utf-8')

        # Hash secret audio if provided, otherwise store None
        hashed_audio = None
        if secret_audio and secret_audio.strip():
            hashed_audio = bcrypt.hashpw(
                secret_audio.strip().lower().encode('utf-8'),
                bcrypt.gensalt()
            ).decode('utf-8')

        created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                '''INSERT INTO users (name, email, password, secret_audio, created_at)
                   VALUES (?, ?, ?, ?, ?)''',
                (name, email.strip().lower(), hashed_password, hashed_audio, created_at)
            )
            conn.commit()

        print(f"[DB] New user registered: {email}")
        return True, 'Registration successful!'

    except sqlite3.IntegrityError:
        # UNIQUE constraint on email failed — account already exists
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
        with sqlite3.connect(DB_PATH) as conn:
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
        with sqlite3.connect(DB_PATH) as conn:
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
        with sqlite3.connect(DB_PATH) as conn:
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


__all__ = [
    'init_db',
    'create_user',
    'verify_user',
    'verify_audio',
    'get_user_by_email',
    'suggest_audio_word',
]