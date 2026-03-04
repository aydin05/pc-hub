#!/bin/bash
# ============================================================
#  Minimal Kiosk Display Setup
#  Installs X11 + Openbox + auto-login + auto-launch Chrome
#  For: Debian/Ubuntu CLI-only systems
#  Run as root: sudo bash setup-kiosk-display.sh
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

if [ "$EUID" -ne 0 ]; then
    error "Please run as root: sudo bash setup-kiosk-display.sh"
fi

KIOSK_USER="${SUDO_USER:-$(whoami)}"
KIOSK_HOME=$(eval echo "~$KIOSK_USER")
KIOSK_URL="https://www.google.com"

# Allow user to override the kiosk URL
if [ -n "$1" ]; then
    KIOSK_URL="$1"
fi

# ── Detect package manager ───────────────────────────────────
if command -v apt-get &>/dev/null; then
    PKG_MGR="apt"
elif command -v dnf &>/dev/null; then
    PKG_MGR="dnf"
elif command -v pacman &>/dev/null; then
    PKG_MGR="pacman"
else
    error "No supported package manager found"
fi

header "Step 1/5 — Installing X11 + Openbox + Chromium"

case "$PKG_MGR" in
    apt)
        apt-get update -qq
        apt-get install -y \
            xorg \
            openbox \
            chromium 2>/dev/null || apt-get install -y chromium-browser 2>/dev/null || true
        # Screenshot + display tools
        apt-get install -y scrot x11-xserver-utils unclutter 2>/dev/null || true
        ;;
    dnf)
        dnf install -y \
            xorg-x11-server-Xorg xorg-x11-xinit \
            openbox \
            chromium 2>/dev/null || true
        dnf install -y scrot xrandr unclutter 2>/dev/null || true
        ;;
    pacman)
        pacman -Sy --noconfirm \
            xorg-server xorg-xinit \
            openbox \
            chromium 2>/dev/null || true
        pacman -S --noconfirm scrot xorg-xrandr unclutter 2>/dev/null || true
        ;;
esac

# Find the browser
BROWSER=""
for b in chromium chromium-browser google-chrome google-chrome-stable; do
    if command -v "$b" &>/dev/null; then
        BROWSER="$b"
        break
    fi
done
[ -z "$BROWSER" ] && error "No Chromium/Chrome browser found after install"
log "Browser: $BROWSER"

header "Step 2/5 — Configuring auto-login on tty1"

# Configure getty to auto-login the kiosk user on tty1
mkdir -p /etc/systemd/system/getty@tty1.service.d
cat > /etc/systemd/system/getty@tty1.service.d/autologin.conf <<EOF
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin $KIOSK_USER --noclear %I \$TERM
EOF

log "Auto-login configured for user: $KIOSK_USER on tty1"

header "Step 3/5 — Creating .xinitrc (X11 startup)"

cat > "$KIOSK_HOME/.xinitrc" <<'XINITRC'
#!/bin/bash
# Kiosk X11 startup
LOGFILE="$HOME/.kiosk-x11.log"
exec >> "$LOGFILE" 2>&1
echo "=== Kiosk X11 starting at $(date) ==="

# Crash guard: if X crashed less than 10 seconds ago, wait before retrying
CRASH_FILE="$HOME/.kiosk-last-crash"
if [ -f "$CRASH_FILE" ]; then
    LAST_CRASH=$(cat "$CRASH_FILE")
    NOW=$(date +%s)
    DIFF=$((NOW - LAST_CRASH))
    if [ "$DIFF" -lt 10 ]; then
        echo "Crash loop detected (last crash ${DIFF}s ago). Sleeping 30s..."
        sleep 30
    fi
fi

# Disable screen saver and power management
xset s off
xset -dpms
xset s noblank

# Hide cursor after 3 seconds of inactivity
unclutter -idle 3 -root &

# Start openbox window manager
openbox-session &
WM_PID=$!

# Wait for openbox to be ready
sleep 2

# Build Chrome flags
CHROME_FLAGS=(
    --kiosk
    --noerrdialogs
    --disable-infobars
    --no-first-run
    --disable-session-crashed-bubble
    --disable-features=TranslateUI
    --disable-translate
    --check-for-update-interval=31536000
)

# Running as root requires --no-sandbox
if [ "$(id -u)" = "0" ]; then
    CHROME_FLAGS+=(--no-sandbox)
fi

# VM-friendly GPU flags
CHROME_FLAGS+=(--disable-gpu --disable-software-rasterizer)

# Launch Chrome in a loop — re-reads URL each time so dashboard changes take effect
while true; do
    KIOSK_URL_FILE="$HOME/.kiosk-url"
    if [ -f "$KIOSK_URL_FILE" ]; then
        URL=$(cat "$KIOSK_URL_FILE")
    else
        URL="__KIOSK_URL__"
    fi

    echo "Launching: __BROWSER__ ${CHROME_FLAGS[*]} $URL"
    __BROWSER__ "${CHROME_FLAGS[@]}" "$URL"
    RETCODE=$?

    echo "Chrome exited with code $RETCODE at $(date)"

    # Brief pause before relaunch to avoid tight loop on crash
    sleep 2
done
XINITRC

# Replace placeholders
sed -i "s|__BROWSER__|$BROWSER|g" "$KIOSK_HOME/.xinitrc"
sed -i "s|__KIOSK_URL__|$KIOSK_URL|g" "$KIOSK_HOME/.xinitrc"
chmod +x "$KIOSK_HOME/.xinitrc"
chown "$KIOSK_USER":"$KIOSK_USER" "$KIOSK_HOME/.xinitrc"

# Save the default URL
echo "$KIOSK_URL" > "$KIOSK_HOME/.kiosk-url"
chown "$KIOSK_USER":"$KIOSK_USER" "$KIOSK_HOME/.kiosk-url"

log "Created $KIOSK_HOME/.xinitrc with $BROWSER in kiosk mode"

header "Step 4/5 — Auto-start X on login"

# Add startx to .bash_profile so X starts automatically on tty1 login
BASH_PROFILE="$KIOSK_HOME/.bash_profile"

# Remove any existing kiosk auto-start block to avoid duplicates
if [ -f "$BASH_PROFILE" ]; then
    sed -i '/# Auto-start X11 on tty1/,/^fi$/d' "$BASH_PROFILE" 2>/dev/null || true
    # Also clean up any stray startx lines
    sed -i '/exec startx/d' "$BASH_PROFILE" 2>/dev/null || true
    # Remove trailing blank lines
    sed -i -e :a -e '/^\n*$/{$d;N;ba' -e '}' "$BASH_PROFILE" 2>/dev/null || true
fi

cat >> "$BASH_PROFILE" <<'PROFILE'

# Auto-start X11 on tty1 (kiosk mode)
if [ -z "$DISPLAY" ] && [ "$(tty)" = "/dev/tty1" ]; then
    exec startx
fi
PROFILE

chown "$KIOSK_USER":"$KIOSK_USER" "$BASH_PROFILE"
log "Auto-startx configured in $BASH_PROFILE"

header "Step 5/5 — Setting default target to graphical"

# Ensure the system boots to the correct target
# We keep multi-user since we're using getty autologin + startx
systemctl set-default multi-user.target
systemctl daemon-reload

log "System configured"

# ══════════════════════════════════════════════════════════════
#  DONE
# ══════════════════════════════════════════════════════════════
MACHINE_IP=$(hostname -I 2>/dev/null | awk '{print $1}')

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║     Kiosk Display Setup Complete!                 ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${CYAN}What was installed:${NC}"
echo -e "    - X11 (Xorg) display server"
echo -e "    - Openbox window manager"
echo -e "    - $BROWSER browser"
echo -e "    - unclutter (hides mouse cursor)"
echo -e ""
echo -e "  ${CYAN}What was configured:${NC}"
echo -e "    - Auto-login as ${BLUE}$KIOSK_USER${NC} on tty1"
echo -e "    - Auto-start X11 on login"
echo -e "    - Auto-launch Chrome in kiosk mode"
echo -e "    - Kiosk URL: ${BLUE}$KIOSK_URL${NC}"
echo ""
echo -e "  ${CYAN}Next steps:${NC}"
echo -e "    1. ${YELLOW}sudo reboot${NC}"
echo -e "    2. Chrome will launch in kiosk mode automatically"
echo -e "    3. Manage from: ${BLUE}http://${MACHINE_IP}:5000${NC}"
echo ""
echo -e "  ${CYAN}To change the kiosk URL:${NC}"
echo -e "    - Use the web dashboard, or:"
echo -e "    - ${YELLOW}echo 'https://example.com' > ~/.kiosk-url${NC}"
echo ""
echo -e "  ${CYAN}Tips:${NC}"
echo -e "    - Press ${YELLOW}Ctrl+Alt+F2${NC} to switch to a second terminal"
echo -e "    - Press ${YELLOW}Ctrl+Alt+F1${NC} to switch back to kiosk display"
echo ""
