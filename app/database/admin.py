import sqlite3
from datetime import datetime
from typing import List, Dict, Optional

from .utils import ADMIN_DB_PATH


def init_admin_db() -> None:
    """Initialize admin DB with activity_log and admin_users tables."""
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


def log_activity(email: str, action: str, detail: str = '') -> None:
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
    try:
        with sqlite3.connect(ADMIN_DB_PATH) as conn:
            cur = conn.execute('SELECT id FROM admin_users WHERE email = ?', (email.strip().lower(),))
            return cur.fetchone() is not None
    except Exception:
        return False


def add_admin(email: str) -> tuple[bool, str]:
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
    try:
        with sqlite3.connect(ADMIN_DB_PATH) as conn:
            conn.execute('DELETE FROM admin_users WHERE email = ?', (email.strip().lower(),))
            conn.commit()
        return True, f'{email} removed from admins.'
    except Exception as e:
        return False, str(e)


def get_activity_log(email: Optional[str] = None, action: Optional[str] = None,
                     limit: int = 100) -> List[Dict]:
    try:
        query = 'SELECT email, action, detail, logged_at FROM activity_log'
        params = []
        where = []
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
            rows = cursor.fetchall()
        return [{'email': r[0], 'action': r[1], 'detail': r[2], 'logged_at': r[3]} for r in rows]
    except Exception as e:
        print(f'[DB] get_activity_log error: {e}')
        return []


def admin_delete_user(email: str) -> tuple[bool, str]:
    """Force-delete a user and related admin records."""
    try:
        email = email.strip().lower()
        # Delete from user DB (users table & sessions)
        from .utils import USER_DB_PATH
        with sqlite3.connect(USER_DB_PATH) as conn:
            conn.execute('DELETE FROM users WHERE email = ?', (email,))
            conn.execute('DELETE FROM sessions WHERE email = ?', (email,))
            conn.commit()
        with sqlite3.connect(ADMIN_DB_PATH) as conn:
            conn.execute('DELETE FROM admin_users WHERE email = ?', (email,))
            conn.execute('DELETE FROM activity_log WHERE email = ?', (email,))
            conn.commit()
        log_activity('admin', 'admin_delete_user', f'deleted: {email}')
        return True, f'User {email} deleted.'
    except Exception as e:
        return False, str(e)


def get_activity_count(email: str, action: str) -> int:
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


def get_activity_count_global(action: str) -> int:
    try:
        with sqlite3.connect(ADMIN_DB_PATH) as conn:
            cur = conn.execute(
                "SELECT COUNT(*) FROM activity_log WHERE action = ?",
                (action,)
            )
            return cur.fetchone()[0]
    except Exception as e:
        print(f'[DB] get_activity_count_global error: {e}')
        return 0
