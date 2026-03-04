from flask import Blueprint, render_template, request, jsonify
from app import login_required
from database import get_setting, set_setting, get_all_settings

settings_bp = Blueprint('settings', __name__)


@settings_bp.route('/')
@login_required
def settings_page():
    return render_template('settings.html')


@settings_bp.route('/api/all')
@login_required
def all_settings():
    return jsonify(get_all_settings())


@settings_bp.route('/api/update', methods=['POST'])
@login_required
def update():
    data = request.get_json()
    allowed_keys = [
        'auth_enabled', 'auth_pin', 'keyboard_enabled',
        'kiosk_url', 'kiosk_devtools', 'kiosk_watchdog',
        'screenshot_interval',
    ]

    updated = []
    for key, value in data.items():
        if key in allowed_keys:
            set_setting(key, str(value))
            updated.append(key)

    return jsonify({'success': True, 'updated': updated})
