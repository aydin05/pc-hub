import subprocess
import os
import re
import tempfile
import time as _time
import logging
from flask import Blueprint, render_template, request, jsonify
from auth_utils import login_required
from sysdetect import get_sys

logger = logging.getLogger(__name__)

datetime_bp = Blueprint('datetime_tz', __name__)

SAFE_TZ_RE = re.compile(r'^[a-zA-Z0-9_/\-\+]+$')


def _run_cmd(cmd, timeout=10):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        output = result.stdout.strip()
        if result.returncode != 0:
            err = result.stderr.strip()
            if err:
                output = f"{output}\n{err}".strip() if output else err
            logger.warning('Command %s failed (rc=%d): %s', cmd, result.returncode, output)
        return output, result.returncode
    except FileNotFoundError:
        logger.error('Command not found: %s', cmd[0] if cmd else '')
        return f'Command not found: {cmd[0] if cmd else ""}', 1
    except subprocess.TimeoutExpired:
        logger.error('Command timed out: %s', cmd)
        return 'Command timed out', 1
    except Exception as e:
        logger.error('Command error: %s', e)
        return str(e), 1


@datetime_bp.route('/')
@login_required
def datetime_page():
    return render_template('datetime.html')


@datetime_bp.route('/api/info')
@login_required
def info():
    sys = get_sys()

    if sys.has('timedatectl'):
        output, _ = _run_cmd([sys.bin('timedatectl'), 'status'])
        info_dict = {}
        for line in output.split('\n'):
            if ':' in line:
                key, val = line.split(':', 1)
                info_dict[key.strip()] = val.strip()
        return jsonify(info_dict)

    # Fallback for macOS / systems without timedatectl
    import datetime
    now = datetime.datetime.now()
    tz_name = _time.tzname[0] if _time.tzname else 'Unknown'
    return jsonify({
        'Local time': now.strftime('%a %Y-%m-%d %H:%M:%S %Z'),
        'Time zone': tz_name,
        'NTP enabled': 'N/A',
        'NTP synchronized': 'N/A',
    })


@datetime_bp.route('/api/timezones')
@login_required
def timezones():
    sys = get_sys()

    if sys.has('timedatectl'):
        output, _ = _run_cmd([sys.bin('timedatectl'), 'list-timezones'])
        zones = [z.strip() for z in output.split('\n') if z.strip()]
        return jsonify({'timezones': zones})

    # Fallback: use pytz-style common zones or read from system
    try:
        import zoneinfo
        zones = sorted(zoneinfo.available_timezones())
        return jsonify({'timezones': zones})
    except ImportError:
        pass

    # Last resort: read from system zoneinfo
    try:
        import os
        zones = []
        zoneinfo_dir = '/usr/share/zoneinfo'
        if sys.is_macos:
            zoneinfo_dir = '/var/db/timezone/zoneinfo'
        for root, dirs, files in os.walk(zoneinfo_dir):
            dirs[:] = [d for d in dirs if d not in ('posix', 'right', '+VERSION')]
            for f in files:
                full = os.path.join(root, f)
                rel = os.path.relpath(full, zoneinfo_dir)
                if '/' in rel and not rel.startswith('.'):
                    zones.append(rel)
        return jsonify({'timezones': sorted(zones)})
    except Exception:
        return jsonify({'timezones': []})


@datetime_bp.route('/api/set-timezone', methods=['POST'])
@login_required
def set_timezone():
    sys = get_sys()
    data = request.get_json()
    tz = data.get('timezone', '').strip()

    if not SAFE_TZ_RE.match(tz):
        return jsonify({'error': 'Invalid timezone'}), 400

    if sys.has('timedatectl'):
        output, rc = _run_cmd(['sudo', sys.bin('timedatectl'), 'set-timezone', tz])
    elif sys.is_macos:
        output, rc = _run_cmd(['sudo', 'systemsetup', '-settimezone', tz])
    else:
        return jsonify({'error': 'No timezone tool available'}), 500

    if rc != 0:
        return jsonify({'error': f'Failed to set timezone: {output}'}), 500

    return jsonify({'success': True, 'timezone': tz})


@datetime_bp.route('/api/set-ntp', methods=['POST'])
@login_required
def set_ntp():
    sys = get_sys()
    data = request.get_json()
    enabled = bool(data.get('enabled', True))
    val = 'true' if enabled else 'false'

    if sys.has('timedatectl'):
        output, rc = _run_cmd(['sudo', sys.bin('timedatectl'), 'set-ntp', val])
    elif sys.is_macos:
        mac_val = 'on' if enabled else 'off'
        output, rc = _run_cmd(['sudo', 'systemsetup', '-setusingnetworktime', mac_val])
    else:
        return jsonify({'error': 'No NTP tool available'}), 500

    if rc != 0:
        return jsonify({'error': f'Failed to set NTP: {output}'}), 500

    return jsonify({'success': True, 'ntp': enabled})


@datetime_bp.route('/api/ntp-server')
@login_required
def get_ntp_server():
    """Read current NTP server from systemd-timesyncd config."""
    ntp_server = ''
    try:
        with open('/etc/systemd/timesyncd.conf', 'r') as f:
            for line in f:
                line = line.strip()
                if line.startswith('NTP='):
                    ntp_server = line.split('=', 1)[1].strip()
                    break
                elif line.startswith('FallbackNTP=') and not ntp_server:
                    ntp_server = line.split('=', 1)[1].strip()
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning('Could not read timesyncd.conf: %s', e)
    return jsonify({'ntp_server': ntp_server})


@datetime_bp.route('/api/ntp-server', methods=['POST'])
@login_required
def set_ntp_server():
    """Set custom NTP server in systemd-timesyncd config."""
    data = request.get_json()
    server = data.get('server', '').strip()

    if not server:
        return jsonify({'error': 'NTP server address is required'}), 400

    # Validate: basic hostname/IP check
    if not re.match(r'^[a-zA-Z0-9._\-:]+$', server):
        return jsonify({'error': 'Invalid NTP server address'}), 400

    try:
        conf_content = '[Time]\nNTP={}\n'.format(server)
        # Write to a temp file then move (needs sudo)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False) as tmp:
            tmp.write(conf_content)
            tmp_path = tmp.name

        output, rc = _run_cmd(['sudo', 'cp', tmp_path, '/etc/systemd/timesyncd.conf'])
        os.remove(tmp_path)

        if rc != 0:
            return jsonify({'error': f'Failed to write config: {output}'}), 500

        # Restart timesyncd to apply
        _run_cmd(['sudo', 'systemctl', 'restart', 'systemd-timesyncd'])
        # Enable NTP
        sys = get_sys()
        if sys.has('timedatectl'):
            _run_cmd(['sudo', sys.bin('timedatectl'), 'set-ntp', 'true'])

        logger.info('NTP server set to: %s', server)
        return jsonify({'success': True, 'ntp_server': server})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@datetime_bp.route('/api/set-time', methods=['POST'])
@login_required
def set_time():
    sys = get_sys()
    data = request.get_json()
    datetime_str = data.get('datetime', '').strip()

    if not re.match(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$', datetime_str):
        return jsonify({'error': 'Invalid datetime format. Use: YYYY-MM-DD HH:MM:SS'}), 400

    if sys.has('timedatectl'):
        _run_cmd(['sudo', sys.bin('timedatectl'), 'set-ntp', 'false'])
        output, rc = _run_cmd(['sudo', sys.bin('timedatectl'), 'set-time', datetime_str])
    elif sys.has('date'):
        output, rc = _run_cmd(['sudo', sys.bin('date'), '-s', datetime_str])
    else:
        return jsonify({'error': 'No time-setting tool available'}), 500

    if rc != 0:
        return jsonify({'error': f'Failed to set time: {output}'}), 500

    return jsonify({'success': True})
