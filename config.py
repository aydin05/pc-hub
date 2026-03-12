import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

SECRET_KEY = os.environ.get('KIOSK_SECRET_KEY', 'change-me-in-production-k1osk-m4n4ger')
DATABASE = os.path.join(BASE_DIR, 'data', 'kiosk.db')
SCREENSHOTS_DIR = os.path.join(BASE_DIR, 'data', 'screenshots')
BIND_HOST = os.environ.get('KIOSK_BIND_HOST', '0.0.0.0')
BIND_PORT = int(os.environ.get('KIOSK_BIND_PORT', 80))
LAN_ONLY = os.environ.get('KIOSK_LAN_ONLY', 'false').lower() == 'true'
VERSION_FILE = os.path.join(BASE_DIR, 'version.txt')

ALLOWED_SUDO_COMMANDS = [
    'reboot',
    'poweroff',
    'xrandr',
    'nmcli',
    'timedatectl',
    'scrot',
    'systemctl restart kiosk-manager',
]
