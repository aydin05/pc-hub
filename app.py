#!/usr/bin/env python3
"""Linux Kiosk Management Dashboard - Main Application"""

import os
from flask import Flask, redirect, url_for, session, request, jsonify
from functools import wraps

from config import SECRET_KEY, BIND_HOST, BIND_PORT, SCREENSHOTS_DIR, LAN_ONLY
from database import init_db, get_setting


def create_app():
    app = Flask(__name__)
    app.secret_key = SECRET_KEY

    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
    os.makedirs(os.path.join(app.root_path, 'data'), exist_ok=True)

    with app.app_context():
        init_db()

    if LAN_ONLY:
        @app.before_request
        def restrict_lan():
            remote = request.remote_addr
            allowed_prefixes = ('127.', '10.', '192.168.', '172.16.', '172.17.',
                                '172.18.', '172.19.', '172.20.', '172.21.',
                                '172.22.', '172.23.', '172.24.', '172.25.',
                                '172.26.', '172.27.', '172.28.', '172.29.',
                                '172.30.', '172.31.')
            if not remote.startswith(allowed_prefixes) and remote != '::1':
                return jsonify({'error': 'Access denied'}), 403

    from routes.auth import auth_bp
    from routes.dashboard import dashboard_bp
    from routes.kiosk import kiosk_bp
    from routes.network import network_bp
    from routes.diagnostics import diagnostics_bp
    from routes.display import display_bp
    from routes.screenshots import screenshots_bp
    from routes.system import system_bp
    from routes.datetime_tz import datetime_bp
    from routes.update import update_bp
    from routes.settings import settings_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(kiosk_bp, url_prefix='/kiosk')
    app.register_blueprint(network_bp, url_prefix='/network')
    app.register_blueprint(diagnostics_bp, url_prefix='/diagnostics')
    app.register_blueprint(display_bp, url_prefix='/display')
    app.register_blueprint(screenshots_bp, url_prefix='/screenshots')
    app.register_blueprint(system_bp, url_prefix='/system')
    app.register_blueprint(datetime_bp, url_prefix='/datetime')
    app.register_blueprint(update_bp, url_prefix='/update')
    app.register_blueprint(settings_bp, url_prefix='/settings')

    @app.route('/')
    def index():
        return redirect(url_for('dashboard.dashboard'))

    @app.context_processor
    def inject_globals():
        return {
            'keyboard_enabled': get_setting('keyboard_enabled', '0') == '1',
            'auth_enabled': get_setting('auth_enabled', '0') == '1',
        }

    return app


def login_required(f):
    """Decorator to require authentication if auth is enabled."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_enabled = get_setting('auth_enabled', '0')
        if auth_enabled == '1' and not session.get('authenticated'):
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


if __name__ == '__main__':
    app = create_app()
    debug = os.environ.get('FLASK_DEBUG', '0') == '1'
    app.run(host=BIND_HOST, port=BIND_PORT, debug=debug, threaded=True)
