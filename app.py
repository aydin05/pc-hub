#!/usr/bin/env python3
"""Linux Kiosk Management Dashboard - Main Application"""

import os
import logging
from flask import Flask, redirect, url_for, session, request, jsonify
from flask_sock import Sock

from config import SECRET_KEY, BIND_HOST, BIND_PORT, SCREENSHOTS_DIR, LAN_ONLY
from database import init_db, get_setting

# Re-export for backward compatibility (avoid circular imports via auth_utils)
from auth_utils import login_required  # noqa: F401


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
    from routes.kiosk import kiosk_bp, init_kiosk_ws
    from routes.network import network_bp
    from routes.diagnostics import diagnostics_bp
    from routes.display import display_bp
    from routes.screenshots import screenshots_bp
    from routes.system import system_bp, start_reboot_scheduler
    from routes.datetime_tz import datetime_bp
    from routes.update import update_bp
    from routes.settings import settings_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    sock = Sock(app)
    init_kiosk_ws(sock)
    app.register_blueprint(kiosk_bp, url_prefix='/kiosk')
    app.register_blueprint(network_bp, url_prefix='/network')
    app.register_blueprint(diagnostics_bp, url_prefix='/diagnostics')
    app.register_blueprint(display_bp, url_prefix='/display')
    app.register_blueprint(screenshots_bp, url_prefix='/screenshots')
    app.register_blueprint(system_bp, url_prefix='/system')
    app.register_blueprint(datetime_bp, url_prefix='/datetime')
    app.register_blueprint(update_bp, url_prefix='/update')
    app.register_blueprint(settings_bp, url_prefix='/settings')

    start_reboot_scheduler()

    @app.route('/')
    def index():
        return redirect(url_for('dashboard.dashboard'))

    # Read version once at startup for cache-busting static assets
    _version_file = os.path.join(app.root_path, 'version.txt')
    _app_version = open(_version_file).read().strip() if os.path.exists(_version_file) else '0'

    @app.context_processor
    def inject_globals():
        from sysdetect import get_sys
        # Only show virtual keyboard when accessed via localhost
        is_local = request.remote_addr in ('127.0.0.1', '::1')
        kb_setting = get_setting('keyboard_enabled', '0') == '1'
        return {
            'keyboard_enabled': kb_setting and is_local,
            'auth_enabled': get_setting('auth_enabled', '0') == '1',
            'has_display': get_sys().has_display,
            'app_version': _app_version,
        }

    return app


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s')
    app = create_app()
    debug = os.environ.get('FLASK_DEBUG', '0') == '1'
    app.run(host=BIND_HOST, port=BIND_PORT, debug=debug, threaded=True)
