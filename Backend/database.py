import sqlite3
import hashlib
import os
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(__file__), 'users.db')

@contextmanager
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def init_db():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                secret_audio TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
    print("Database initialized")

def create_user(name, email, password, secret_audio=None):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            hashed_password = hash_password(password)
            hashed_audio = hash_password(secret_audio) if secret_audio else None
            
            cursor.execute('''
                INSERT INTO users (name, email, password, secret_audio)
                VALUES (?, ?, ?, ?)
            ''', (name, email, hashed_password, hashed_audio))
            
            conn.commit()
            return True, "User created successfully"
    except sqlite3.IntegrityError:
        return False, "Email already exists"
    except Exception as e:
        return False, f"Error: {str(e)}"

def verify_user(email, password=None, audio_password=None):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
            user = cursor.fetchone()
            
            if not user:
                return False, None, "User not found"
            
            if password:
                hashed_input = hash_password(password)
                if hashed_input == user['password']:
                    return True, dict(user), "Login successful"
            
            if audio_password and user['secret_audio']:
                hashed_audio = hash_password(audio_password)
                if hashed_audio == user['secret_audio']:
                    return True, dict(user), "Audio login successful"
            
            return False, None, "Invalid credentials"
    except Exception as e:
        return False, None, f"Error: {str(e)}"

if __name__ == '__main__':
    init_db()