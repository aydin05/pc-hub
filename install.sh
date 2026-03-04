#!/bin/bash
# ============================================================
#  Kiosk Manager - Auto-Detecting Setup Script
#  Supports: Ubuntu/Debian, Fedora/RHEL/CentOS, Arch Linux
#  Run as root or with sudo: sudo bash install.sh
# ============================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

log()    { echo -e "${GREEN}[+]${NC} $1"; }
warn()   { echo -e "${YELLOW}[!]${NC} $1"; }
error()  { echo -e "${RED}[✗]${NC} $1"; exit 1; }
info()   { echo -e "${CYAN}[i]${NC} $1"; }
header() { echo -e "\n${BLUE}══════════════════════════════════════${NC}"; echo -e "${BLUE}  $1${NC}"; echo -e "${BLUE}══════════════════════════════════════${NC}"; }

# ── Must run as root ─────────────────────────────────────────
if [ "$EUID" -ne 0 ]; then
    error "Please run as root: sudo bash install.sh"
fi

# ── Detect the real user (the one who called sudo) ───────────
REAL_USER="${SUDO_USER:-$(whoami)}"
REAL_HOME=$(eval echo "~$REAL_USER")

# ── Config ───────────────────────────────────────────────────
INSTALL_DIR="/opt/kiosk-manager"
SERVICE_USER="$REAL_USER"
PORT=5000

# ══════════════════════════════════════════════════════════════
#  STEP 0: Detect system
# ══════════════════════════════════════════════════════════════
header "Detecting system"

DISTRO="unknown"
PKG_MGR="none"
DISPLAY_SERVER="none"

# Detect distro
if [ -f /etc/os-release ]; then
    . /etc/os-release
    DISTRO=$(echo "$ID" | tr '[:upper:]' '[:lower:]')
fi

# Detect package manager
if command -v apt-get &>/dev/null; then
    PKG_MGR="apt"
elif command -v dnf &>/dev/null; then
    PKG_MGR="dnf"
elif command -v yum &>/dev/null; then
    PKG_MGR="yum"
elif command -v pacman &>/dev/null; then
    PKG_MGR="pacman"
fi

# Detect display server
HEADLESS=true
if [ -n "$WAYLAND_DISPLAY" ] || [ "$XDG_SESSION_TYPE" = "wayland" ]; then
    DISPLAY_SERVER="wayland"
    HEADLESS=false
elif [ -n "$DISPLAY" ] || [ "$XDG_SESSION_TYPE" = "x11" ]; then
    DISPLAY_SERVER="x11"
    HEADLESS=false
else
    # Check if any display manager is installed even if not currently in a session
    if command -v Xorg &>/dev/null || command -v Xwayland &>/dev/null || \
       systemctl is-active display-manager &>/dev/null 2>&1 || \
       [ -d /usr/share/xsessions ] || [ -d /usr/share/wayland-sessions ]; then
        HEADLESS=false
        # Guess x11 as default when display manager exists but session type unknown
        DISPLAY_SERVER="x11"
    fi
fi

log "Distro:          $DISTRO (${PRETTY_NAME:-$DISTRO})"
log "Package manager: $PKG_MGR"
if [ "$HEADLESS" = true ]; then
    log "Display server:  ${YELLOW}none (headless mode)${NC}"
    warn "Headless mode: Kiosk, Display, and Screenshot features will be disabled"
else
    log "Display server:  $DISPLAY_SERVER"
fi
log "Installing as:   $SERVICE_USER"
log "Install dir:     $INSTALL_DIR"
log "Port:            $PORT"
echo ""

[ "$PKG_MGR" = "none" ] && error "No supported package manager found (apt/dnf/yum/pacman)"

# ══════════════════════════════════════════════════════════════
#  STEP 1: Install system packages
# ══════════════════════════════════════════════════════════════
header "Step 1/7 — Installing system packages"

# Common packages mapped per package manager
install_packages() {
    case "$PKG_MGR" in
        apt)
            apt-get update -qq
            apt-get install -y python3 python3-pip python3-venv git sqlite3 curl
            # Network
            apt-get install -y network-manager 2>/dev/null || true
            # Display-dependent packages (skip in headless mode)
            if [ "$HEADLESS" = false ]; then
                # Screenshot tool
                if [ "$DISPLAY_SERVER" = "wayland" ]; then
                    apt-get install -y grim 2>/dev/null || apt-get install -y gnome-screenshot 2>/dev/null || true
                else
                    apt-get install -y scrot 2>/dev/null || apt-get install -y gnome-screenshot 2>/dev/null || true
                fi
                # Display tool
                if [ "$DISPLAY_SERVER" = "wayland" ]; then
                    apt-get install -y wlr-randr 2>/dev/null || true
                else
                    apt-get install -y x11-xserver-utils 2>/dev/null || true  # provides xrandr
                fi
                # Browser
                apt-get install -y chromium-browser 2>/dev/null || apt-get install -y chromium 2>/dev/null || true
            else
                info "Skipping display packages (headless mode)"
            fi
            ;;
        dnf|yum)
            $PKG_MGR install -y python3 python3-pip git sqlite curl
            $PKG_MGR install -y NetworkManager 2>/dev/null || true
            if [ "$HEADLESS" = false ]; then
                if [ "$DISPLAY_SERVER" = "wayland" ]; then
                    $PKG_MGR install -y grim 2>/dev/null || $PKG_MGR install -y gnome-screenshot 2>/dev/null || true
                    $PKG_MGR install -y wlr-randr 2>/dev/null || true
                else
                    $PKG_MGR install -y scrot 2>/dev/null || $PKG_MGR install -y gnome-screenshot 2>/dev/null || true
                    $PKG_MGR install -y xrandr 2>/dev/null || $PKG_MGR install -y xorg-x11-server-utils 2>/dev/null || true
                fi
                $PKG_MGR install -y chromium 2>/dev/null || $PKG_MGR install -y chromium-browser 2>/dev/null || true
            else
                info "Skipping display packages (headless mode)"
            fi
            ;;
        pacman)
            pacman -Sy --noconfirm python python-pip git sqlite curl
            pacman -S --noconfirm networkmanager 2>/dev/null || true
            if [ "$HEADLESS" = false ]; then
                if [ "$DISPLAY_SERVER" = "wayland" ]; then
                    pacman -S --noconfirm grim 2>/dev/null || true
                    pacman -S --noconfirm wlr-randr 2>/dev/null || true
                else
                    pacman -S --noconfirm scrot 2>/dev/null || true
                    pacman -S --noconfirm xorg-xrandr 2>/dev/null || true
                fi
                pacman -S --noconfirm chromium 2>/dev/null || true
            else
                info "Skipping display packages (headless mode)"
            fi
            ;;
    esac
}

install_packages

# Verify critical tools
command -v python3 &>/dev/null || error "python3 not found after install"
command -v git &>/dev/null || error "git not found after install"

# Check for a browser (only relevant with a display)
if [ "$HEADLESS" = false ]; then
    if command -v chromium-browser &>/dev/null; then
        log "Browser: chromium-browser"
    elif command -v chromium &>/dev/null; then
        log "Browser: chromium"
    elif command -v google-chrome &>/dev/null; then
        log "Browser: google-chrome"
    else
        warn "No Chromium/Chrome browser found — install manually for kiosk mode"
    fi
fi

log "System packages installed"

# ══════════════════════════════════════════════════════════════
#  STEP 2: Copy project files
# ══════════════════════════════════════════════════════════════
header "Step 2/7 — Copying project files"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ "$SCRIPT_DIR" = "$INSTALL_DIR" ]; then
    log "Already running from $INSTALL_DIR — skipping copy"
else
    if [ -d "$INSTALL_DIR" ]; then
        warn "Directory $INSTALL_DIR exists — backing up to ${INSTALL_DIR}.bak"
        mv "$INSTALL_DIR" "${INSTALL_DIR}.bak.$(date +%Y%m%d%H%M%S)"
    fi
    cp -r "$SCRIPT_DIR" "$INSTALL_DIR"
    log "Files copied to $INSTALL_DIR"
fi

chown -R "$SERVICE_USER":"$SERVICE_USER" "$INSTALL_DIR"

# ══════════════════════════════════════════════════════════════
#  STEP 3: Python virtualenv + dependencies
# ══════════════════════════════════════════════════════════════
header "Step 3/7 — Setting up Python virtualenv"

sudo -u "$SERVICE_USER" python3 -m venv "$INSTALL_DIR/venv"
sudo -u "$SERVICE_USER" "$INSTALL_DIR/venv/bin/pip" install --quiet --upgrade pip
sudo -u "$SERVICE_USER" "$INSTALL_DIR/venv/bin/pip" install --quiet -r "$INSTALL_DIR/requirements.txt"
sudo -u "$SERVICE_USER" "$INSTALL_DIR/venv/bin/pip" install --quiet gunicorn
log "Python dependencies installed (including gunicorn)"

# ══════════════════════════════════════════════════════════════
#  STEP 4: Create data directory
# ══════════════════════════════════════════════════════════════
header "Step 4/7 — Creating data directory"
mkdir -p "$INSTALL_DIR/data/screenshots"
chown -R "$SERVICE_USER":"$SERVICE_USER" "$INSTALL_DIR/data"
log "Data directory ready"

# ══════════════════════════════════════════════════════════════
#  STEP 5: Auto-detect sudoers (dynamic binary paths)
# ══════════════════════════════════════════════════════════════
header "Step 5/7 — Configuring sudoers"

SUDOERS_FILE="/etc/sudoers.d/kiosk-manager"
echo "# Kiosk Manager sudoers — auto-generated $(date)" > "$SUDOERS_FILE"
echo "Defaults:$SERVICE_USER !requiretty" >> "$SUDOERS_FILE"
echo "" >> "$SUDOERS_FILE"

# Only add entries for binaries that actually exist on this system
add_sudoers_entry() {
    local bin_path
    bin_path=$(command -v "$1" 2>/dev/null || true)
    if [ -n "$bin_path" ]; then
        if [ -n "$2" ]; then
            echo "$SERVICE_USER ALL=(ALL) NOPASSWD: $bin_path $2" >> "$SUDOERS_FILE"
            info "  sudoers: $bin_path $2"
        else
            echo "$SERVICE_USER ALL=(ALL) NOPASSWD: $bin_path" >> "$SUDOERS_FILE"
            info "  sudoers: $bin_path (any args)"
        fi
    fi
}

add_sudoers_entry reboot ""
add_sudoers_entry poweroff ""
add_sudoers_entry systemctl "reboot"
add_sudoers_entry systemctl "poweroff"
add_sudoers_entry systemctl "restart kiosk-manager"
add_sudoers_entry nmcli ""
add_sudoers_entry timedatectl ""
add_sudoers_entry hostnamectl ""

# Display-dependent sudoers entries (only if display is available)
if [ "$HEADLESS" = false ]; then
    add_sudoers_entry xrandr ""
    add_sudoers_entry wlr-randr ""
    add_sudoers_entry scrot ""
    add_sudoers_entry grim ""
    add_sudoers_entry gnome-screenshot ""
fi

# Also allow the resolved paths via sysdetect (shutil.which)
# Add common alternative paths for key binaries
for alt_bin in /sbin/reboot /usr/sbin/reboot; do
    if [ -x "$alt_bin" ]; then
        echo "$SERVICE_USER ALL=(ALL) NOPASSWD: $alt_bin" >> "$SUDOERS_FILE"
    fi
done
for alt_bin in /sbin/poweroff /usr/sbin/poweroff; do
    if [ -x "$alt_bin" ]; then
        echo "$SERVICE_USER ALL=(ALL) NOPASSWD: $alt_bin" >> "$SUDOERS_FILE"
    fi
done

chmod 440 "$SUDOERS_FILE"

# Validate sudoers file
if visudo -cf "$SUDOERS_FILE" &>/dev/null; then
    log "Sudoers configured at $SUDOERS_FILE"
else
    error "Sudoers file has syntax errors! Check $SUDOERS_FILE"
fi

# ══════════════════════════════════════════════════════════════
#  STEP 6: systemd services
# ══════════════════════════════════════════════════════════════
header "Step 6/7 — Installing systemd service"

SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")

cat > /etc/systemd/system/kiosk-manager.service <<EOF
[Unit]
Description=Kiosk Manager Dashboard
After=network.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120 --access-logfile - --error-logfile - wsgi:app
Restart=always
RestartSec=5
Environment=XDG_RUNTIME_DIR=/run/user/$(id -u $SERVICE_USER)
Environment=DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u $SERVICE_USER)/bus
Environment=KIOSK_SECRET_KEY=$SECRET_KEY

[Install]
WantedBy=multi-user.target
EOF

# Add display environment variables only when a display server is present
if [ "$HEADLESS" = false ]; then
    sed -i '/^\[Install\]/i Environment=DISPLAY=:0\nEnvironment=WAYLAND_DISPLAY=wayland-0\nEnvironment=XDG_SESSION_TYPE='"$DISPLAY_SERVER"'\nEnvironment=XAUTHORITY='"$REAL_HOME"'/.Xauthority' /etc/systemd/system/kiosk-manager.service
fi

# Resolution persistence service (only with a display server)
if [ "$HEADLESS" = false ] && [ -f "$INSTALL_DIR/deploy/apply-resolution.sh" ]; then
    chmod +x "$INSTALL_DIR/deploy/apply-resolution.sh"
    cat > /etc/systemd/system/kiosk-resolution.service <<EOF
[Unit]
Description=Apply saved display resolution on boot
After=display-manager.service

[Service]
Type=oneshot
User=$SERVICE_USER
Environment=DISPLAY=:0
Environment=WAYLAND_DISPLAY=wayland-0
Environment=XDG_SESSION_TYPE=$DISPLAY_SERVER
Environment=XAUTHORITY=$REAL_HOME/.Xauthority
Environment=XDG_RUNTIME_DIR=/run/user/$(id -u $SERVICE_USER)
ExecStart=$INSTALL_DIR/deploy/apply-resolution.sh
RemainAfterExit=yes

[Install]
WantedBy=graphical.target
EOF
    systemctl enable kiosk-resolution 2>/dev/null || true
fi

systemctl daemon-reload
systemctl enable kiosk-manager
systemctl start kiosk-manager
log "systemd services installed and started"

# ══════════════════════════════════════════════════════════════
#  STEP 7: Firewall
# ══════════════════════════════════════════════════════════════
header "Step 7/7 — Firewall"
if command -v ufw &>/dev/null; then
    ufw allow "$PORT"/tcp 2>/dev/null || true
    log "ufw: port $PORT opened"
elif command -v firewall-cmd &>/dev/null; then
    firewall-cmd --permanent --add-port="$PORT/tcp" 2>/dev/null || true
    firewall-cmd --reload 2>/dev/null || true
    log "firewalld: port $PORT opened"
else
    warn "No firewall tool found — open port $PORT manually if needed"
fi

# ══════════════════════════════════════════════════════════════
#  DONE — Print summary
# ══════════════════════════════════════════════════════════════
MACHINE_IP=$(hostname -I 2>/dev/null | awk '{print $1}')

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║       Kiosk Manager installed successfully!      ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${CYAN}System detected:${NC}"
echo -e "    Distro:   ${BLUE}${PRETTY_NAME:-$DISTRO}${NC}"
if [ "$HEADLESS" = true ]; then
    echo -e "    Display:  ${YELLOW}none (headless)${NC}"
    echo -e "    Mode:     ${YELLOW}Server mode — Kiosk/Display/Screenshots disabled${NC}"
else
    echo -e "    Display:  ${BLUE}$DISPLAY_SERVER${NC}"
fi
echo -e "    Packages: ${BLUE}$PKG_MGR${NC}"
echo ""
echo -e "  ${CYAN}Access:${NC}"
echo -e "    Local:    ${BLUE}http://localhost:${PORT}${NC}"
echo -e "    Network:  ${BLUE}http://${MACHINE_IP}:${PORT}${NC}"
echo ""
echo -e "  ${CYAN}Manage:${NC}"
echo -e "    Status:   ${YELLOW}sudo systemctl status kiosk-manager${NC}"
echo -e "    Logs:     ${YELLOW}sudo journalctl -u kiosk-manager -f${NC}"
echo -e "    Restart:  ${YELLOW}sudo systemctl restart kiosk-manager${NC}"
echo ""
