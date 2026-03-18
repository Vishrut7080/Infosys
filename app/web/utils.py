from functools import wraps
from flask import session, redirect, url_for
from app.database import database

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('auth.login_page'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('auth.login_page'))
        email = session['user'].get('email', '')
        if not database.is_admin(email):
            return redirect(url_for('assistant.dashboard'))
        return f(*args, **kwargs)
    return decorated
