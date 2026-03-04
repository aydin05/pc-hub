import subprocess
import re
import logging
from flask import Blueprint, render_template, request, jsonify
from auth_utils import login_required
from database import get_setting, set_setting
from sysdetect import get_sys

logger = logging.getLogger(__name__)

display_bp = Blueprint('display', __name__)

SAFE_RES_RE = re.compile(r'^\d{3,5}x\d{3,5}$')
SAFE_OUTPUT_RE = re.compile(r'^[a-zA-Z0-9\-]+$')


def _run_cmd(cmd, timeout=10):
    try:
        env = get_sys().get_env_with_display()
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
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


def _get_displays():
    """Parse display tool output for connected displays and their modes."""
    sys = get_sys()
    display_bin, display_type = sys.get_display_cmd()
    if not display_bin:
        return []

    output, rc = _run_cmd([display_bin])
    if rc != 0:
        return []

    displays = []
    current_display = None

    if display_type == 'xrandr':
        for line in output.split('\n'):
            if ' connected' in line:
                parts = line.split()
                name = parts[0]
                current_res = ''
                for part in parts:
                    if re.match(r'\d+x\d+\+\d+\+\d+', part):
                        current_res = part.split('+')[0]
                        break
                current_display = {
                    'name': name,
                    'current': current_res,
                    'modes': [],
                }
                displays.append(current_display)
            elif current_display and line.startswith('   '):
                mode_match = re.match(r'\s+(\d+x\d+)', line)
                if mode_match:
                    mode = mode_match.group(1)
                    if mode not in current_display['modes']:
                        current_display['modes'].append(mode)
            elif ' disconnected' in line:
                current_display = None

    elif display_type == 'wlr-randr':
        for line in output.split('\n'):
            if not line.startswith(' ') and line.strip():
                parts = line.split()
                name = parts[0]
                current_display = {'name': name, 'current': '', 'modes': []}
                displays.append(current_display)
            elif current_display and 'current' in line.lower():
                mode_match = re.search(r'(\d+x\d+)', line)
                if mode_match:
                    current_display['current'] = mode_match.group(1)
            elif current_display:
                mode_match = re.search(r'(\d+x\d+)', line)
                if mode_match:
                    mode = mode_match.group(1)
                    if mode not in current_display['modes']:
                        current_display['modes'].append(mode)

    return displays


@display_bp.route('/')
@login_required
def display_page():
    return render_template('display.html')


@display_bp.route('/api/info')
@login_required
def info():
    return jsonify({'displays': _get_displays()})


@display_bp.route('/api/set', methods=['POST'])
@login_required
def set_resolution():
    data = request.get_json()
    output_name = data.get('output', '')
    mode = data.get('mode', '')

    if not SAFE_OUTPUT_RE.match(output_name):
        return jsonify({'error': 'Invalid output name'}), 400
    if not SAFE_RES_RE.match(mode):
        return jsonify({'error': 'Invalid resolution'}), 400

    sys = get_sys()
    display_bin, display_type = sys.get_display_cmd()
    if not display_bin:
        return jsonify({'error': 'No display tool available'}), 500

    if display_type == 'xrandr':
        result, rc = _run_cmd([display_bin, '--output', output_name, '--mode', mode])
    elif display_type == 'wlr-randr':
        result, rc = _run_cmd([display_bin, '--output', output_name, '--mode', mode])
    else:
        return jsonify({'error': f'Unsupported display tool: {display_type}'}), 500

    if rc != 0:
        return jsonify({'error': f'Failed to set resolution: {result}'}), 500

    set_setting('display_resolution', f'{output_name}:{mode}')
    return jsonify({'success': True, 'output': output_name, 'mode': mode})
