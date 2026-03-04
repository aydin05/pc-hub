import os
from flask import Blueprint, render_template, jsonify
from auth_utils import login_required
from config import VERSION_FILE
from sysdetect import get_sys

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')


@dashboard_bp.route('/api/system-info')
@login_required
def system_info():
    sys = get_sys()
    version = '0.0.0'
    if os.path.exists(VERSION_FILE):
        with open(VERSION_FILE) as f:
            version = f.read().strip()

    info = {
        'hostname': sys.get_hostname(),
        'os': sys.get_os_string(),
        'kernel': sys.get_kernel(),
        'uptime': sys.get_uptime(),
        'ip': sys.get_primary_ip(),
        'version': version,
    }
    return jsonify(info)
