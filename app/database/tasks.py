"""Task / To-do management — persisted in the main users.db SQLite database."""

import sqlite3
from datetime import datetime, timezone
from .utils import USER_DB_PATH


def init_tasks_db():
    """Create the tasks table if it does not already exist."""
    con = sqlite3.connect(USER_DB_PATH)
    con.execute('PRAGMA journal_mode=WAL')
    con.execute('PRAGMA busy_timeout = 5000')
    con.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            email       TEXT    NOT NULL,
            title       TEXT    NOT NULL,
            description TEXT    DEFAULT '',
            priority    TEXT    DEFAULT 'normal',
            status      TEXT    DEFAULT 'pending',
            source      TEXT    DEFAULT 'manual',
            created_at  TEXT    NOT NULL,
            completed_at TEXT   DEFAULT NULL
        )
    """)
    con.commit()
    con.close()


def add_task(email: str, title: str, description: str = '', priority: str = 'normal', source: str = 'manual') -> dict:
    """Insert a new task and return it."""
    if priority not in ('normal', 'high', 'urgent'):
        priority = 'normal'
    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    con = sqlite3.connect(USER_DB_PATH)
    cur = con.execute(
        "INSERT INTO tasks (email, title, description, priority, status, source, created_at) VALUES (?,?,?,?,?,?,?)",
        (email, title, description, priority, 'pending', source, now)
    )
    task_id = cur.lastrowid
    con.commit()
    con.close()
    return {'id': task_id, 'title': title, 'description': description,
            'priority': priority, 'status': 'pending', 'source': source, 'created_at': now}


def list_tasks(email: str, status: str = 'pending') -> list[dict]:
    """Return tasks for a user, optionally filtered by status."""
    con = sqlite3.connect(USER_DB_PATH)
    con.row_factory = sqlite3.Row
    if status == 'all':
        rows = con.execute(
            "SELECT * FROM tasks WHERE email=? ORDER BY created_at DESC", (email,)
        ).fetchall()
    else:
        rows = con.execute(
            "SELECT * FROM tasks WHERE email=? AND status=? ORDER BY created_at DESC",
            (email, status)
        ).fetchall()
    con.close()
    return [dict(r) for r in rows]


def complete_task(email: str, task_id: int) -> bool:
    """Mark a task as done. Returns True if a row was updated."""
    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    con = sqlite3.connect(USER_DB_PATH)
    cur = con.execute(
        "UPDATE tasks SET status='done', completed_at=? WHERE id=? AND email=?",
        (now, task_id, email)
    )
    updated = cur.rowcount > 0
    con.commit()
    con.close()
    return updated


def delete_task(email: str, task_id: int) -> bool:
    """Delete a task. Returns True if a row was deleted."""
    con = sqlite3.connect(USER_DB_PATH)
    cur = con.execute("DELETE FROM tasks WHERE id=? AND email=?", (task_id, email))
    deleted = cur.rowcount > 0
    con.commit()
    con.close()
    return deleted


def get_task(email: str, task_id: int) -> dict | None:
    """Fetch a single task by id."""
    con = sqlite3.connect(USER_DB_PATH)
    con.row_factory = sqlite3.Row
    row = con.execute("SELECT * FROM tasks WHERE id=? AND email=?", (task_id, email)).fetchone()
    con.close()
    return dict(row) if row else None
