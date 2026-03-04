#!/bin/bash
# Apply saved display resolution on boot
# Called by kiosk-resolution.service

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
    xrandr --output "$OUTPUT" --mode "$MODE"
fi
