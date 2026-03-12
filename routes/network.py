import subprocess
import re
import logging
from flask import Blueprint, render_template, request, jsonify
from auth_utils import login_required
from sysdetect import get_sys

logger = logging.getLogger(__name__)

network_bp = Blueprint('network', __name__)

SAFE_HOSTNAME_RE = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9\-]{0,62}$')
SAFE_IP_RE = re.compile(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(/\d{1,2})?$')
SAFE_IFACE_RE = re.compile(r'^[a-zA-Z0-9\-_:\.]+$')


def _subnet_mask_to_cidr(mask):
    """Convert subnet mask (e.g. 255.255.255.0) to CIDR prefix (e.g. 24)."""
    try:
        octets = [int(o) for o in mask.split('.')]
        if len(octets) != 4 or any(o < 0 or o > 255 for o in octets):
            return None
        binary = ''.join(format(o, '08b') for o in octets)
        # Count consecutive 1s from the left
        cidr = len(binary) - len(binary.lstrip('1'))
        # Verify it's a valid mask (all 1s followed by all 0s)
        if binary != ('1' * cidr + '0' * (32 - cidr)):
            return None
        return cidr
    except (ValueError, AttributeError):
        return None


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


def _get_connection_name(nmcli, iface):
    """Return the NetworkManager connection profile name for a network device.

    NetworkManager separates device names (e.g. 'enp3s0') from connection
    profile names (e.g. 'Wired connection 1').  'nmcli con mod/down/up'
    requires the profile name, not the device name.

    Strategy:
      1. Ask nmcli for the active connection on the device.
      2. Fall back to any connection associated with the device (including inactive).
      3. Create a new connection profile for the device.
    """
    # Step 1: active connection
    output, rc = _run_cmd([nmcli, '-g', 'GENERAL.CONNECTION', 'device', 'show', iface])
    if rc == 0 and output.strip() and output.strip() != '--':
        logger.info('Found active connection "%s" for device %s', output.strip(), iface)
        return output.strip()

    # Step 2: any connection (active or inactive) with a matching device/interface field
    output, rc = _run_cmd([nmcli, '-t', '-f', 'NAME,DEVICE', 'con', 'show'])
    if rc == 0:
        for line in output.split('\n'):
            parts = line.rsplit(':', 1)
            if len(parts) == 2 and parts[1].strip() == iface:
                name = parts[0].replace('\\:', ':')
                logger.info('Found connection "%s" for device %s', name, iface)
                return name

    # Step 2b: also check the connection.interface-name field for inactive profiles
    output, rc = _run_cmd([nmcli, '-t', '-f', 'NAME,connection.interface-name', 'con', 'show'])
    if rc == 0:
        for line in output.split('\n'):
            parts = line.rsplit(':', 1)
            if len(parts) == 2 and parts[1].strip() == iface:
                name = parts[0].replace('\\:', ':')
                logger.info('Found connection "%s" for interface %s (via connection.interface-name)', name, iface)
                return name

    # Step 3: create a new connection profile for this device
    logger.info('No connection profile found for %s, creating one', iface)
    conn_name = iface
    _run_cmd(['sudo', nmcli, 'con', 'add', 'type', 'ethernet',
              'con-name', conn_name, 'ifname', iface])
    return conn_name


def _configure_nmcli(nmcli, iface, method, data):
    """Configure network interface using nmcli."""
    conn_name = _get_connection_name(nmcli, iface)

    if method == 'dhcp':
        output, rc = _run_cmd([
            'sudo', nmcli, 'con', 'mod', conn_name,
            'ipv4.method', 'auto',
            'ipv4.addresses', '',
            'ipv4.gateway', '',
            'ipv4.dns', '',
        ])
        if rc != 0:
            return jsonify({'error': f'Failed to set DHCP: {output[:200]}'}), 500

    elif method == 'static':
        ip_addr = data.get('ip', '')
        gateway = data.get('gateway', '')
        dns = data.get('dns', '')
        subnet_mask = data.get('subnet', '255.255.255.0')

        if not SAFE_IP_RE.match(ip_addr):
            return jsonify({'error': 'Invalid IP address'}), 400
        if gateway and not SAFE_IP_RE.match(gateway):
            return jsonify({'error': 'Invalid gateway'}), 400

        # Convert subnet mask to CIDR prefix
        cidr = _subnet_mask_to_cidr(subnet_mask)
        if cidr is None:
            return jsonify({'error': 'Invalid subnet mask'}), 400

        # nmcli requires CIDR notation
        if '/' not in ip_addr:
            ip_addr = f'{ip_addr}/{cidr}'

        cmd = [
            'sudo', nmcli, 'con', 'mod', conn_name,
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
            return jsonify({'error': f'Failed to set static IP: {output[:200]}'}), 500
    else:
        return jsonify({'error': 'Invalid method'}), 400

    _run_cmd(['sudo', nmcli, 'con', 'down', conn_name])
    out, rc = _run_cmd(['sudo', nmcli, 'con', 'up', conn_name])
    if rc != 0:
        return jsonify({'error': f'Settings saved but failed to bring connection up: {out[:200]}'}), 500

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
