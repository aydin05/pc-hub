import subprocess
import os
import re
import tempfile
import logging
from flask import Blueprint, render_template, request, jsonify, current_app
from auth_utils import login_required
from sysdetect import get_sys

logger = logging.getLogger(__name__)

system_bp = Blueprint('system', __name__)

CRON_MARKER = '# kiosk-manager-auto-reboot'


@system_bp.route('/')
@login_required
def system_page():
    return render_template('system.html')


@system_bp.route('/api/reboot', methods=['POST'])
@login_required
def reboot():
    data = request.get_json() or {}
    confirm = data.get('confirm', False)
    if not confirm:
        return jsonify({'error': 'Confirmation required'}), 400
    cmd = get_sys().get_reboot_cmd()
    if not cmd:
        return jsonify({'error': 'Reboot command not available on this system'}), 500
    try:
        logger.info('Executing reboot: %s', cmd)
        subprocess.Popen(cmd)
        return jsonify({'success': True, 'message': 'System is rebooting...'})
    except Exception as e:
        logger.error('Reboot failed: %s', e)
        return jsonify({'error': str(e)}), 500


@system_bp.route('/api/shutdown', methods=['POST'])
@login_required
def shutdown():
    data = request.get_json() or {}
    confirm = data.get('confirm', False)
    if not confirm:
        return jsonify({'error': 'Confirmation required'}), 400
    cmd = get_sys().get_shutdown_cmd()
    if not cmd:
        return jsonify({'error': 'Shutdown command not available on this system'}), 500
    try:
        logger.info('Executing shutdown: %s', cmd)
        subprocess.Popen(cmd)
        return jsonify({'success': True, 'message': 'System is shutting down...'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@system_bp.route('/api/info')
@login_required
def info():
    sys = get_sys()
    return jsonify({
        'cpu_cores': sys.get_cpu_cores(),
        'memory': sys.get_memory_info(),
        'disk': sys.get_disk_info(),
        'load': sys.get_load_average(),
    })


# ── Scheduled Reboot ─────────────────────────────────────────

def _get_crontab():
    """Read current root crontab lines."""
    try:
        result = subprocess.run(
            ['sudo', 'crontab', '-l'],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return []
        return result.stdout.strip().split('\n')
    except Exception:
        return []


def _set_crontab(lines):
    """Write root crontab."""
    content = '\n'.join(lines) + '\n'
    proc = subprocess.run(
        ['sudo', 'crontab', '-'],
        input=content, capture_output=True, text=True, timeout=5
    )
    return proc.returncode == 0


@system_bp.route('/api/schedule-reboot')
@login_required
def get_schedule_reboot():
    """Get current auto-reboot schedule from crontab."""
    lines = _get_crontab()
    for line in lines:
        if CRON_MARKER in line:
            # Parse: MM HH * * DOW /sbin/reboot # kiosk-manager-auto-reboot
            match = re.match(r'^(\d+)\s+(\d+)\s+\*\s+\*\s+(\S+)\s+', line)
            if match:
                minute, hour, dow = match.group(1), match.group(2), match.group(3)
                return jsonify({
                    'enabled': True,
                    'hour': int(hour),
                    'minute': int(minute),
                    'days': dow,
                })
    return jsonify({'enabled': False, 'hour': 3, 'minute': 0, 'days': '*'})


@system_bp.route('/api/schedule-reboot', methods=['POST'])
@login_required
def set_schedule_reboot():
    """Set or update auto-reboot schedule in crontab."""
    data = request.get_json()
    enabled = data.get('enabled', False)

    # Remove existing auto-reboot entry
    lines = _get_crontab()
    lines = [l for l in lines if CRON_MARKER not in l and l.strip()]

    if enabled:
        hour = int(data.get('hour', 3))
        minute = int(data.get('minute', 0))
        days = data.get('days', '*').strip() or '*'

        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return jsonify({'error': 'Invalid time'}), 400
        if not re.match(r'^[\d,\*\-]+$', days):
            return jsonify({'error': 'Invalid days format'}), 400

        cron_line = f'{minute} {hour} * * {days} /sbin/reboot {CRON_MARKER}'
        lines.append(cron_line)
        logger.info('Scheduled reboot: %s', cron_line)

    if not _set_crontab(lines):
        return jsonify({'error': 'Failed to update crontab'}), 500

    return jsonify({'success': True, 'enabled': enabled})


# ── Self-signed Certificate Management ───────────────────────

def _get_nssdb_path():
    """Get the Chromium NSS database path."""
    home = os.path.expanduser('~')
    for candidate in [
        os.path.join(home, '.pki/nssdb'),
        os.path.join(home, 'snap/chromium/current/.pki/nssdb'),
    ]:
        if os.path.isdir(candidate):
            return candidate
    # Create default path if it doesn't exist
    default = os.path.join(home, '.pki/nssdb')
    os.makedirs(default, exist_ok=True)
    # Initialize the NSS database
    subprocess.run(
        ['certutil', '-d', f'sql:{default}', '-N', '--empty-password'],
        capture_output=True, timeout=10
    )
    return default


@system_bp.route('/api/certs')
@login_required
def list_certs():
    """List installed certificates in Chromium's NSS database."""
    try:
        nssdb = _get_nssdb_path()
        result = subprocess.run(
            ['certutil', '-d', f'sql:{nssdb}', '-L'],
            capture_output=True, text=True, timeout=10
        )
        certs = []
        for line in result.stdout.strip().split('\n'):
            line = line.strip()
            if not line or line.startswith('Certificate Nickname') or line.startswith('-'):
                continue
            # Format: "nickname    trust_flags"
            parts = line.rsplit(None, 1)
            if len(parts) >= 1:
                certs.append({
                    'name': parts[0].strip(),
                    'trust': parts[1].strip() if len(parts) > 1 else '',
                })
        return jsonify({'success': True, 'certs': certs, 'nssdb': nssdb})
    except FileNotFoundError:
        return jsonify({'success': False, 'error': 'certutil not found. Install libnss3-tools: sudo apt install libnss3-tools', 'certs': []})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e), 'certs': []})


@system_bp.route('/api/certs/upload', methods=['POST'])
@login_required
def upload_cert():
    """Upload and install a self-signed certificate into Chromium's NSS database."""
    if 'cert' not in request.files:
        return jsonify({'error': 'No certificate file provided'}), 400

    f = request.files['cert']
    if not f.filename:
        return jsonify({'error': 'No file selected'}), 400

    name = request.form.get('name', '').strip()
    if not name:
        name = os.path.splitext(f.filename)[0]

    # Save to temp file
    ext = f.filename.rsplit('.', 1)[-1].lower() if '.' in f.filename else 'pem'
    if ext not in ('pem', 'crt', 'cer', 'der'):
        return jsonify({'error': 'Invalid certificate file. Allowed: .pem, .crt, .cer, .der'}), 400

    try:
        with tempfile.NamedTemporaryFile(suffix=f'.{ext}', delete=False) as tmp:
            f.save(tmp)
            tmp_path = tmp.name

        nssdb = _get_nssdb_path()

        # If DER format, convert to PEM first
        cert_path = tmp_path
        if ext == 'der':
            pem_path = tmp_path + '.pem'
            result = subprocess.run(
                ['openssl', 'x509', '-inform', 'DER', '-in', tmp_path, '-out', pem_path],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode != 0:
                os.remove(tmp_path)
                return jsonify({'error': 'Failed to convert DER certificate'}), 500
            cert_path = pem_path

        # Install certificate with CT,C,C trust (trusted for SSL, email, code signing)
        result = subprocess.run(
            ['certutil', '-d', f'sql:{nssdb}', '-A', '-t', 'CT,C,C', '-n', name, '-i', cert_path],
            capture_output=True, text=True, timeout=10
        )

        # Cleanup temp files
        os.remove(tmp_path)
        if cert_path != tmp_path and os.path.exists(cert_path):
            os.remove(cert_path)

        if result.returncode != 0:
            return jsonify({'error': f'certutil failed: {result.stderr.strip()}'}), 500

        logger.info('Installed certificate: %s', name)
        return jsonify({'success': True, 'name': name})
    except FileNotFoundError:
        return jsonify({'error': 'certutil not found. Install: sudo apt install libnss3-tools'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@system_bp.route('/api/certs/delete', methods=['POST'])
@login_required
def delete_cert():
    """Delete a certificate from Chromium's NSS database."""
    data = request.get_json()
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Certificate name required'}), 400

    try:
        nssdb = _get_nssdb_path()
        result = subprocess.run(
            ['certutil', '-d', f'sql:{nssdb}', '-D', '-n', name],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return jsonify({'error': f'Failed to delete: {result.stderr.strip()}'}), 500
        logger.info('Deleted certificate: %s', name)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
