import subprocess
import os
import logging
from flask import Blueprint, render_template, request, jsonify, Response
from auth_utils import login_required
from config import BASE_DIR, VERSION_FILE
from sysdetect import get_sys

logger = logging.getLogger(__name__)

update_bp = Blueprint('update', __name__)


def _get_version():
    if os.path.exists(VERSION_FILE):
        with open(VERSION_FILE) as f:
            return f.read().strip()
    return 'unknown'


def _get_git_info():
    try:
        branch = subprocess.run(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            capture_output=True, text=True, cwd=BASE_DIR, timeout=5
        ).stdout.strip()
        commit = subprocess.run(
            ['git', 'log', '-1', '--format=%h %s'],
            capture_output=True, text=True, cwd=BASE_DIR, timeout=5
        ).stdout.strip()
        return {'branch': branch, 'commit': commit}
    except Exception:
        return {'branch': 'N/A', 'commit': 'N/A'}


@update_bp.route('/')
@login_required
def update_page():
    return render_template('update.html')


@update_bp.route('/api/info')
@login_required
def info():
    return jsonify({
        'version': _get_version(),
        'git': _get_git_info(),
    })


@update_bp.route('/api/check', methods=['POST'])
@login_required
def check_updates():
    try:
        subprocess.run(
            ['git', 'fetch'], capture_output=True, text=True,
            cwd=BASE_DIR, timeout=30
        )
        result = subprocess.run(
            ['git', 'log', 'HEAD..origin/main', '--oneline'],
            capture_output=True, text=True, cwd=BASE_DIR, timeout=10
        )
        commits = result.stdout.strip()
        if not commits:
            result = subprocess.run(
                ['git', 'log', 'HEAD..origin/master', '--oneline'],
                capture_output=True, text=True, cwd=BASE_DIR, timeout=10
            )
            commits = result.stdout.strip()

        if commits:
            return jsonify({'updates_available': True, 'commits': commits})
        return jsonify({'updates_available': False})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@update_bp.route('/api/pull')
@login_required
def pull():
    def generate():
        try:
            proc = subprocess.Popen(
                ['git', 'pull', '--ff-only'],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, cwd=BASE_DIR
            )
            for line in iter(proc.stdout.readline, ''):
                yield f"data: {line.rstrip()}\n\n"
            proc.wait()

            if proc.returncode == 0:
                yield f"data: [SUCCESS] Update complete. Version: {_get_version()}\n\n"
                yield "data: [RESTARTING] Restarting service...\n\n"
                try:
                    sys = get_sys()
                    systemctl_bin = sys.bin('systemctl') or 'systemctl'
                    subprocess.Popen(
                        ['sudo', systemctl_bin, 'restart', 'kiosk-manager'],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
                except Exception:
                    yield "data: [INFO] Auto-restart not available. Please restart manually.\n\n"
            else:
                yield f"data: [ERROR] Update failed with exit code {proc.returncode}\n\n"

            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: [ERROR] {str(e)}\n\n"

    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})
