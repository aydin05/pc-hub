"""Authentication utilities — shared across routes."""

from functools import wraps
from flask import session, redirect, url_for
from database import get_setting


def login_required(f):
    """Decorator to require authentication if auth is enabled."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_enabled = get_setting('auth_enabled', '0')
        if auth_enabled == '1' and not session.get('authenticated'):
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function
