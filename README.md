# Kiosk Manager Dashboard

A full-featured Linux kiosk management panel built with Python Flask. Designed for Linux-based digital signage or kiosk deployments.

## Features

- **Chrome Kiosk Controller** — Launch, restart, kill Chromium in kiosk mode with watchdog auto-recovery and connection error fallback
- **Network Configuration** — View interfaces, configure static/DHCP IP, set DNS and hostname via NetworkManager
- **Network Diagnostics** — Ping, TCP port check, and port scanner with live-streamed output (SSE)
- **Display & Resolution** — List and apply resolutions via xrandr, persist across reboots
- **Screenshot Capture** — Capture, preview, download, and delete screen captures
- **System Controls** — Reboot and shutdown with confirmation modals
- **Date, Time & Timezone** — Live clock, timezone picker, NTP toggle, manual time set
- **Update / Upgrade** — Pull updates from Git with live log output, auto-restart service
- **Virtual On-Screen Keyboard** — Built-in HTML/CSS/JS keyboard for touchscreen deployments
- **Settings** — PIN authentication, keyboard toggle, kiosk defaults

## Tech Stack

- **Backend:** Python 3 + Flask
- **Frontend:** Vanilla JS, HTML5, CSS3 (no frameworks, no CDN)
- **Database:** SQLite
- **Target OS:** Ubuntu / Debian Linux

## Quick Start

```bash
# Clone the repository
git clone <repo-url> /opt/kiosk-manager
cd /opt/kiosk-manager

# Install dependencies
pip3 install -r requirements.txt

# Run the app
python3 app.py
```

Open `http://localhost` in your browser.

## Production Deployment

### 1. Install as a systemd service

```bash
sudo cp deploy/kiosk-manager.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable kiosk-manager
sudo systemctl start kiosk-manager
```

### 2. Configure sudoers

Edit the sudoers file to match your username (replace `kiosk` with your user):

```bash
sudo cp deploy/kiosk-manager.sudoers /etc/sudoers.d/kiosk-manager
sudo chmod 440 /etc/sudoers.d/kiosk-manager
```

### 3. Persist display resolution on boot

```bash
sudo chmod +x deploy/apply-resolution.sh
sudo cp deploy/kiosk-resolution.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable kiosk-resolution
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `KIOSK_SECRET_KEY` | (built-in) | Flask session secret key |
| `KIOSK_BIND_HOST` | `0.0.0.0` | Bind address |
| `KIOSK_BIND_PORT` | `80` | Bind port |
| `KIOSK_LAN_ONLY` | `false` | Restrict access to LAN IPs only |

## Security

- Optional PIN-based authentication (configure in Settings)
- All shell commands use whitelist validation — no raw user input passed to `shell=True`
- Sudoers config grants only the minimum required commands
- Set `KIOSK_LAN_ONLY=true` to restrict access to local network

## Project Structure

```
├── app.py                  # Flask application entry point
├── config.py               # Configuration constants
├── database.py             # SQLite database helpers
├── requirements.txt        # Python dependencies
├── version.txt             # Application version
├── routes/                 # Flask blueprints
│   ├── auth.py             # PIN authentication
│   ├── dashboard.py        # Dashboard / system info
│   ├── kiosk.py            # Chrome kiosk controller
│   ├── network.py          # Network configuration
│   ├── diagnostics.py      # Ping, TCP check, port scanner
│   ├── display.py          # Display resolution
│   ├── screenshots.py      # Screenshot capture
│   ├── system.py           # Reboot / shutdown
│   ├── datetime_tz.py      # Date, time, timezone
│   ├── update.py           # Git update manager
│   └── settings.py         # App settings
├── templates/              # Jinja2 HTML templates
├── static/
│   ├── css/style.css       # Dark theme UI
│   └── js/
│       ├── app.js          # Toast, Modal, SSE, utilities
│       └── keyboard.js     # Virtual on-screen keyboard
├── deploy/
│   ├── kiosk-manager.service       # systemd unit
│   ├── kiosk-manager.sudoers       # sudoers config
│   ├── kiosk-resolution.service    # resolution persistence
│   └── apply-resolution.sh         # resolution boot script
└── data/                   # SQLite DB + screenshots (created at runtime)
```
