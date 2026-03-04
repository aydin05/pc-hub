import subprocess
import signal
import os
import threading
import time
import logging
import urllib.request
import urllib.error
from flask import Blueprint, render_template, request, jsonify
from auth_utils import login_required
from database import get_setting, set_setting

logger = logging.getLogger(__name__)
from sysdetect import get_sys

kiosk_bp = Blueprint('kiosk', __name__)

_chromium_process = None
_watchdog_thread = None
_watchdog_running = False


def _find_chromium():
    """Find chromium binary via sysdetect."""
    return get_sys().get_browser() or 'chromium-browser'


def _is_url_reachable(url, timeout=5):
    """Check if a URL is reachable."""
    try:
        urllib.request.urlopen(url, timeout=timeout)
        return True
    except Exception:
        return False


def _get_kiosk_pid():
    """Get the PID of the running Chromium kiosk process."""
    global _chromium_process
    if _chromium_process and _chromium_process.poll() is None:
        return _chromium_process.pid
    try:
        result = subprocess.run(
            ['pgrep', '-f', 'chromium.*--kiosk'],
            capture_output=True, text=True
        )
        pids = result.stdout.strip().split('\n')
        if pids and pids[0]:
            return int(pids[0])
    except Exception:
        pass
    return None


def _launch_chromium(url=None):
    """Launch Chromium in kiosk mode."""
    global _chromium_process

    if url is None:
        url = get_setting('kiosk_url', 'https://www.google.com')

    devtools = get_setting('kiosk_devtools', '0') == '1'

    if not _is_url_reachable(url):
        url = 'http://127.0.0.1:5000/kiosk/error-page'

    chromium = _find_chromium()
    cmd = [
        chromium,
        '--kiosk',
        '--noerrdialogs',
        '--disable-infobars',
        '--no-first-run',
        '--disable-session-crashed-bubble',
        '--disable-features=TranslateUI',
    ]

    if devtools:
        cmd.append('--remote-debugging-port=9222')

    # Use sysdetect env which includes DISPLAY, XAUTHORITY, etc.
    env = get_sys().get_env_with_display()

    cmd.append(url)

    logger.info('Launching kiosk: %s', ' '.join(cmd))
    _chromium_process = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return _chromium_process.pid


def _watchdog_loop():
    """Watchdog: restart Chromium if it crashes."""
    global _watchdog_running, _chromium_process
    while _watchdog_running:
        time.sleep(10)
        if not _watchdog_running:
            break
        pid = _get_kiosk_pid()
        if pid is None and _watchdog_running:
            _launch_chromium()

        url = get_setting('kiosk_url', 'https://www.google.com')
        if not _is_url_reachable(url):
            _kill_chromium()
            time.sleep(1)
            _launch_chromium('http://127.0.0.1:5000/kiosk/error-page')


def _kill_chromium():
    """Kill Chromium process."""
    global _chromium_process
    if _chromium_process and _chromium_process.poll() is None:
        _chromium_process.terminate()
        try:
            _chromium_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _chromium_process.kill()
        _chromium_process = None
    else:
        try:
            subprocess.run(['pkill', '-f', 'chromium.*--kiosk'], timeout=5)
        except Exception:
            pass


@kiosk_bp.route('/')
@login_required
def kiosk_page():
    sys = get_sys()
    if sys.is_headless:
        return render_template('headless.html',
                               feature='Chrome Kiosk',
                               reason='No display server detected (headless mode).')
    settings = {
        'url': get_setting('kiosk_url', 'https://www.google.com'),
        'devtools': get_setting('kiosk_devtools', '0'),
        'watchdog': get_setting('kiosk_watchdog', '1'),
    }
    return render_template('kiosk.html', settings=settings)


@kiosk_bp.route('/error-page')
def error_page():
    return render_template('kiosk_error.html')


@kiosk_bp.route('/api/status')
@login_required
def status():
    if get_sys().is_headless:
        return jsonify({'running': False, 'pid': None, 'headless': True, 'error': 'No display server available'})
    pid = _get_kiosk_pid()
    return jsonify({
        'running': pid is not None,
        'pid': pid,
        'url': get_setting('kiosk_url', 'https://www.google.com'),
        'watchdog': _watchdog_running,
    })


@kiosk_bp.route('/api/launch', methods=['POST'])
@login_required
def launch():
    if get_sys().is_headless:
        return jsonify({'error': 'Cannot launch kiosk in headless mode (no display server)'}), 400
    pid = _get_kiosk_pid()
    if pid:
        return jsonify({'error': 'Chromium is already running', 'pid': pid}), 400
    new_pid = _launch_chromium()
    return jsonify({'success': True, 'pid': new_pid})


@kiosk_bp.route('/api/restart', methods=['POST'])
@login_required
def restart():
    if get_sys().is_headless:
        return jsonify({'error': 'Cannot restart kiosk in headless mode (no display server)'}), 400
    _kill_chromium()
    time.sleep(1)
    new_pid = _launch_chromium()
    return jsonify({'success': True, 'pid': new_pid})


@kiosk_bp.route('/api/kill', methods=['POST'])
@login_required
def kill():
    _kill_chromium()
    return jsonify({'success': True})


@kiosk_bp.route('/api/settings', methods=['POST'])
@login_required
def update_settings():
    data = request.get_json()
    if 'url' in data:
        url = data['url'].strip()
        if not url.startswith(('http://', 'https://')):
            return jsonify({'error': 'URL must start with http:// or https://'}), 400
        set_setting('kiosk_url', url)
    if 'devtools' in data:
        set_setting('kiosk_devtools', '1' if data['devtools'] else '0')
    if 'watchdog' in data:
        global _watchdog_running, _watchdog_thread
        enabled = bool(data['watchdog'])
        set_setting('kiosk_watchdog', '1' if enabled else '0')
        if enabled and not _watchdog_running:
            _watchdog_running = True
            _watchdog_thread = threading.Thread(target=_watchdog_loop, daemon=True)
            _watchdog_thread.start()
        elif not enabled:
            _watchdog_running = False
    return jsonify({'success': True})
