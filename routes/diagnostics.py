import subprocess
import re
import socket
from flask import Blueprint, render_template, request, jsonify, Response
from app import login_required
from sysdetect import get_sys

diagnostics_bp = Blueprint('diagnostics', __name__)

SAFE_HOST_RE = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9.\-]+$')


def _validate_host(host):
    return bool(SAFE_HOST_RE.match(host)) and len(host) <= 253


def _validate_port(port):
    try:
        p = int(port)
        return 1 <= p <= 65535
    except (ValueError, TypeError):
        return False


@diagnostics_bp.route('/')
@login_required
def diagnostics_page():
    return render_template('diagnostics.html')


@diagnostics_bp.route('/api/ping')
@login_required
def ping():
    host = request.args.get('host', '').strip()
    count = request.args.get('count', '4')

    if not _validate_host(host):
        return jsonify({'error': 'Invalid host'}), 400

    try:
        count = min(int(count), 20)
    except ValueError:
        count = 4

    def generate():
        try:
            ping_cmd = get_sys().get_ping_cmd(host, count)
            proc = subprocess.Popen(
                ping_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True
            )
            for line in iter(proc.stdout.readline, ''):
                yield f"data: {line.rstrip()}\n\n"
            proc.wait()
            yield f"data: [DONE] Exit code: {proc.returncode}\n\n"
        except Exception as e:
            yield f"data: [ERROR] {str(e)}\n\n"

    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@diagnostics_bp.route('/api/tcpcheck', methods=['POST'])
@login_required
def tcp_check():
    data = request.get_json()
    host = data.get('host', '').strip()
    port = data.get('port', '')

    if not _validate_host(host):
        return jsonify({'error': 'Invalid host'}), 400
    if not _validate_port(port):
        return jsonify({'error': 'Invalid port'}), 400

    port = int(port)
    timeout = min(int(data.get('timeout', 5)), 30)

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()

        if result == 0:
            status = 'open'
        else:
            status = 'closed'
    except socket.timeout:
        status = 'timeout'
    except socket.gaierror:
        return jsonify({'error': f'Cannot resolve host: {host}'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    return jsonify({'host': host, 'port': port, 'status': status})


@diagnostics_bp.route('/api/portscan')
@login_required
def port_scan():
    host = request.args.get('host', '').strip()
    start_port = request.args.get('start', '1')
    end_port = request.args.get('end', '1024')

    if not _validate_host(host):
        return jsonify({'error': 'Invalid host'}), 400

    try:
        start = max(1, int(start_port))
        end = min(65535, int(end_port))
        if end - start > 1024:
            end = start + 1024
    except ValueError:
        return jsonify({'error': 'Invalid port range'}), 400

    def generate():
        yield f"data: {{'type':'start','host':'{host}','range':'{start}-{end}'}}\n\n"
        for port in range(start, end + 1):
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(0.5)
                result = sock.connect_ex((host, port))
                sock.close()
                if result == 0:
                    try:
                        service = socket.getservbyport(port)
                    except OSError:
                        service = ''
                    yield f"data: {{\"type\":\"result\",\"port\":{port},\"status\":\"open\",\"service\":\"{service}\"}}\n\n"
            except Exception:
                pass

            if port % 50 == 0:
                pct = int(((port - start + 1) / (end - start + 1)) * 100)
                yield f"data: {{\"type\":\"progress\",\"percent\":{pct},\"current\":{port}}}\n\n"

        yield f"data: {{\"type\":\"done\"}}\n\n"

    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})
