import os
from flask import Blueprint, render_template, request, jsonify, send_file, current_app
from auth_utils import login_required
from database import get_setting, set_setting, get_all_settings

settings_bp = Blueprint('settings', __name__)

LOGO_FILENAME = 'logo.png'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'svg', 'webp', 'ico'}


def _logo_path():
    return os.path.join(current_app.root_path, 'data', LOGO_FILENAME)


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


@settings_bp.route('/api/logo', methods=['GET'])
def get_logo():
    """Serve the uploaded logo — no auth so loading page can use it."""
    path = _logo_path()
    if os.path.isfile(path):
        return send_file(path, mimetype='image/png')
    return jsonify({'error': 'No logo uploaded'}), 404


@settings_bp.route('/api/logo', methods=['POST'])
@login_required
def upload_logo():
    """Upload a custom logo image."""
    if 'logo' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    f = request.files['logo']
    if not f.filename:
        return jsonify({'error': 'No file selected'}), 400
    ext = f.filename.rsplit('.', 1)[-1].lower() if '.' in f.filename else ''
    if ext not in ALLOWED_EXTENSIONS:
        allowed = ', '.join(sorted(ALLOWED_EXTENSIONS))
        return jsonify({'error': f'Invalid file type. Allowed: {allowed}'}), 400
    path = _logo_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    f.save(path)
    return jsonify({'success': True})


@settings_bp.route('/api/logo', methods=['DELETE'])
@login_required
def delete_logo():
    """Delete the custom logo, reverting to default."""
    path = _logo_path()
    if os.path.isfile(path):
        os.remove(path)
    return jsonify({'success': True})
