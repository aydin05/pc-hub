import subprocess
from flask import Blueprint, render_template, request, jsonify
from app import login_required
from sysdetect import get_sys

system_bp = Blueprint('system', __name__)


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
        subprocess.Popen(cmd)
        return jsonify({'success': True, 'message': 'System is rebooting...'})
    except Exception as e:
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
