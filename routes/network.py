import subprocess
import re
from flask import Blueprint, render_template, request, jsonify
from app import login_required
from sysdetect import get_sys

network_bp = Blueprint('network', __name__)

SAFE_HOSTNAME_RE = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9\-]{0,62}$')
SAFE_IP_RE = re.compile(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(/\d{1,2})?$')
SAFE_IFACE_RE = re.compile(r'^[a-zA-Z0-9\-_:\.]+$')


def _run_cmd(cmd, timeout=10):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.stdout.strip(), result.returncode
    except FileNotFoundError:
        return '', 1
    except Exception as e:
        return str(e), 1


def _get_interfaces_linux():
    """Get network interfaces on Linux using ip command."""
    sys = get_sys()
    ip_bin = sys.bin('ip')
    if not ip_bin:
        return []

    interfaces = []
    output, _ = _run_cmd([ip_bin, '-o', 'link', 'show'])
    if not output:
        return interfaces

    for line in output.split('\n'):
        parts = line.split(': ')
        if len(parts) < 2:
            continue
        iface_name = parts[1].split('@')[0].strip()
        if iface_name == 'lo':
            continue

        state = 'DOWN'
        if 'state UP' in line:
            state = 'UP'

        mac = ''
        mac_match = re.search(r'link/ether\s+([\da-f:]+)', line)
        if mac_match:
            mac = mac_match.group(1)

        ip_out, _ = _run_cmd([ip_bin, '-4', 'addr', 'show', iface_name])
        ip_addr = ''
        ip_match = re.search(r'inet\s+([\d./]+)', ip_out)
        if ip_match:
            ip_addr = ip_match.group(1)

        interfaces.append({
            'name': iface_name,
            'state': state,
            'mac': mac,
            'ip': ip_addr,
        })

    return interfaces


def _get_interfaces_macos():
    """Get network interfaces on macOS using ifconfig."""
    sys = get_sys()
    ifconfig_bin = sys.bin('ifconfig')
    if not ifconfig_bin:
        return []

    interfaces = []
    output, _ = _run_cmd([ifconfig_bin])
    if not output:
        return interfaces

    current_iface = None
    for line in output.split('\n'):
        iface_match = re.match(r'^(\w+):\s+flags=', line)
        if iface_match:
            name = iface_match.group(1)
            if name == 'lo0':
                current_iface = None
                continue
            current_iface = {'name': name, 'state': 'DOWN', 'mac': '', 'ip': ''}
            if 'UP' in line:
                current_iface['state'] = 'UP'
            interfaces.append(current_iface)
        elif current_iface:
            mac_match = re.search(r'ether\s+([\da-f:]+)', line)
            if mac_match:
                current_iface['mac'] = mac_match.group(1)
            ip_match = re.search(r'inet\s+([\d.]+)', line)
            if ip_match:
                current_iface['ip'] = ip_match.group(1)

    return interfaces


def _get_interfaces():
    """Get network interfaces, cross-platform."""
    sys = get_sys()
    if sys.is_linux:
        return _get_interfaces_linux()
    if sys.is_macos:
        return _get_interfaces_macos()
    return []


@network_bp.route('/')
@login_required
def network_page():
    return render_template('network.html')


@network_bp.route('/api/interfaces')
@login_required
def interfaces():
    return jsonify({'interfaces': _get_interfaces()})


@network_bp.route('/api/configure', methods=['POST'])
@login_required
def configure():
    sys = get_sys()
    data = request.get_json()
    iface = data.get('interface', '')
    method = data.get('method', 'dhcp')

    if not SAFE_IFACE_RE.match(iface):
        return jsonify({'error': 'Invalid interface name'}), 400

    if sys.net_backend == 'networkmanager':
        nmcli = sys.bin('nmcli')
        if not nmcli:
            return jsonify({'error': 'nmcli not available'}), 500
        return _configure_nmcli(nmcli, iface, method, data)
    elif sys.net_backend == 'macos':
        return jsonify({'error': 'Network configuration via dashboard not supported on macOS. Use System Preferences.'}), 400
    else:
        return jsonify({'error': f'Network backend "{sys.net_backend}" not supported for configuration'}), 400


def _configure_nmcli(nmcli, iface, method, data):
    """Configure network interface using nmcli."""
    if method == 'dhcp':
        output, rc = _run_cmd([
            'sudo', nmcli, 'con', 'mod', iface,
            'ipv4.method', 'auto',
            'ipv4.addresses', '',
            'ipv4.gateway', '',
            'ipv4.dns', '',
        ])
        if rc != 0:
            return jsonify({'error': f'Failed to set DHCP: {output}'}), 500

    elif method == 'static':
        ip_addr = data.get('ip', '')
        gateway = data.get('gateway', '')
        dns = data.get('dns', '')

        if not SAFE_IP_RE.match(ip_addr):
            return jsonify({'error': 'Invalid IP address'}), 400
        if gateway and not SAFE_IP_RE.match(gateway):
            return jsonify({'error': 'Invalid gateway'}), 400

        cmd = [
            'sudo', nmcli, 'con', 'mod', iface,
            'ipv4.method', 'manual',
            'ipv4.addresses', ip_addr,
        ]
        if gateway:
            cmd.extend(['ipv4.gateway', gateway])
        if dns:
            dns_servers = [d.strip() for d in dns.split(',') if SAFE_IP_RE.match(d.strip())]
            if dns_servers:
                cmd.extend(['ipv4.dns', ' '.join(dns_servers)])

        output, rc = _run_cmd(cmd)
        if rc != 0:
            return jsonify({'error': f'Failed to set static IP: {output}'}), 500
    else:
        return jsonify({'error': 'Invalid method'}), 400

    _run_cmd(['sudo', nmcli, 'con', 'down', iface])
    _run_cmd(['sudo', nmcli, 'con', 'up', iface])

    return jsonify({'success': True})


@network_bp.route('/api/hostname', methods=['POST'])
@login_required
def set_hostname():
    sys = get_sys()
    data = request.get_json()
    hostname = data.get('hostname', '').strip()

    if not SAFE_HOSTNAME_RE.match(hostname):
        return jsonify({'error': 'Invalid hostname'}), 400

    if sys.has('hostnamectl'):
        output, rc = _run_cmd(['sudo', sys.bin('hostnamectl'), 'set-hostname', hostname])
    elif sys.is_macos:
        output, rc = _run_cmd(['sudo', 'scutil', '--set', 'HostName', hostname])
    else:
        return jsonify({'error': 'No hostname tool available'}), 500

    if rc != 0:
        return jsonify({'error': f'Failed to set hostname: {output}'}), 500

    return jsonify({'success': True, 'hostname': hostname})
