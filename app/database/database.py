"""Compatibility wrapper for the original database module.

This module re-exports the previous public API while the
implementation has been split into smaller modules:
 - app.database.utils
 - app.database.users
 - app.database.admin
 - app.database.tasks

Keep this file as a thin shim to avoid import regressions elsewhere
in the codebase while improving internal organization.
"""

from .utils import USER_DB_PATH, ADMIN_DB_PATH, suggest_audio_word
from .users import (
    init_db, create_user, verify_user, verify_audio, get_user_by_email,
    get_user_credentials, generate_pins, store_pins, store_gmail_token, verify_pin,
    get_all_users, get_active_users, log_session, update_name,
    update_password, update_audio, delete_user
)
from .admin import (
    init_admin_db, log_activity, is_admin, add_admin, remove_admin,
    get_activity_log, admin_delete_user, get_activity_count, get_activity_count_global
)
from .tasks import (
    init_tasks_db, add_task, list_tasks, complete_task, delete_task, get_task
)

__all__ = [
    'init_db', 'init_admin_db', 'init_tasks_db',
    'create_user', 'verify_user', 'verify_audio',
    'get_user_by_email', 'get_user_credentials', 'suggest_audio_word',
    'update_name', 'update_password', 'update_audio', 'delete_user',
    'log_session', 'log_activity', 'get_all_users', 'get_active_users',
    'get_activity_log', 'is_admin', 'add_admin', 'remove_admin',
    'admin_delete_user', 'USER_DB_PATH', 'ADMIN_DB_PATH',
    'generate_pins', 'store_pins', 'store_gmail_token', 'verify_pin', 'get_activity_count',
    'get_activity_count_global',
    'add_task', 'list_tasks', 'complete_task', 'delete_task', 'get_task',
]
