import subprocess
import os
import time
import logging
from flask import Blueprint, render_template, request, jsonify, send_from_directory
from auth_utils import login_required
from config import SCREENSHOTS_DIR

logger = logging.getLogger(__name__)
from database import get_db
from sysdetect import get_sys

screenshots_bp = Blueprint('screenshots', __name__)


def _capture_screenshot():
    """Capture a screenshot using the best available tool."""
    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
    filename = f'screenshot_{int(time.time())}.png'
    filepath = os.path.join(SCREENSHOTS_DIR, filename)

    cmd, env = get_sys().get_screenshot_cmd(filepath)
    if not cmd:
        return None

    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=10, env=env)

        if os.path.exists(filepath):
            conn = get_db()
            conn.execute(
                'INSERT INTO screenshots (filename) VALUES (?)', (filename,)
            )
            conn.commit()
            conn.close()
            return filename
    except Exception:
        pass
    return None


@screenshots_bp.route('/')
@login_required
def screenshots_page():
    if get_sys().is_headless:
        return render_template('headless.html',
                               feature='Screenshots',
                               reason='No display server detected (headless mode).')
    return render_template('screenshots.html')


@screenshots_bp.route('/api/capture', methods=['POST'])
@login_required
def capture():
    if get_sys().is_headless:
        return jsonify({'error': 'Cannot capture screenshots in headless mode (no display server)'}), 400
    filename = _capture_screenshot()
    if filename:
        return jsonify({'success': True, 'filename': filename})
    return jsonify({'error': 'Failed to capture screenshot'}), 500


@screenshots_bp.route('/api/list')
@login_required
def list_screenshots():
    conn = get_db()
    rows = conn.execute(
        'SELECT id, filename, created_at FROM screenshots ORDER BY created_at DESC LIMIT 50'
    ).fetchall()
    conn.close()
    return jsonify({
        'screenshots': [
            {'id': r['id'], 'filename': r['filename'], 'created_at': r['created_at']}
            for r in rows
        ]
    })


@screenshots_bp.route('/api/download/<filename>')
@login_required
def download(filename):
    if '/' in filename or '..' in filename:
        return jsonify({'error': 'Invalid filename'}), 400
    return send_from_directory(SCREENSHOTS_DIR, filename, as_attachment=True)


@screenshots_bp.route('/api/view/<filename>')
@login_required
def view(filename):
    if '/' in filename or '..' in filename:
        return jsonify({'error': 'Invalid filename'}), 400
    return send_from_directory(SCREENSHOTS_DIR, filename)


@screenshots_bp.route('/api/delete/<int:screenshot_id>', methods=['DELETE'])
@login_required
def delete(screenshot_id):
    conn = get_db()
    row = conn.execute('SELECT filename FROM screenshots WHERE id = ?', (screenshot_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'Screenshot not found'}), 404

    filepath = os.path.join(SCREENSHOTS_DIR, row['filename'])
    if os.path.exists(filepath):
        os.remove(filepath)

    conn.execute('DELETE FROM screenshots WHERE id = ?', (screenshot_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})
