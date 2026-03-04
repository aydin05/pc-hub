#!/bin/bash
# Apply saved display resolution on boot
# Called by kiosk-resolution.service
# Supports both X11 (xrandr) and Wayland (wlr-randr)

DB_PATH="/opt/kiosk-manager/data/kiosk.db"

if [ ! -f "$DB_PATH" ]; then
    exit 0
fi

RESOLUTION=$(sqlite3 "$DB_PATH" "SELECT value FROM settings WHERE key='display_resolution'" 2>/dev/null)

if [ -z "$RESOLUTION" ]; then
    exit 0
fi

OUTPUT=$(echo "$RESOLUTION" | cut -d':' -f1)
MODE=$(echo "$RESOLUTION" | cut -d':' -f2)

if [ -n "$OUTPUT" ] && [ -n "$MODE" ]; then
    sleep 3

    # Detect display server and apply
    if [ "$XDG_SESSION_TYPE" = "wayland" ] || [ -n "$WAYLAND_DISPLAY" ]; then
        if command -v wlr-randr &>/dev/null; then
            wlr-randr --output "$OUTPUT" --mode "$MODE"
        fi
    else
        if command -v xrandr &>/dev/null; then
            xrandr --output "$OUTPUT" --mode "$MODE"
        fi
    fi
fi
