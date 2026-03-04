import sqlite3
import os
from config import DATABASE


def get_db():
    """Get a database connection."""
    os.makedirs(os.path.dirname(DATABASE), exist_ok=True)
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Initialize the database with required tables and default values."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.executescript('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS screenshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    ''')

    defaults = {
        'kiosk_url': 'https://www.google.com',
        'kiosk_devtools': '0',
        'kiosk_watchdog': '1',
        'auth_enabled': '0',
        'auth_pin': '1234',
        'keyboard_enabled': '0',
        'screenshot_interval': '0',
        'display_resolution': '',
        'hostname': '',
    }

    for key, value in defaults.items():
        cursor.execute(
            'INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)',
            (key, value)
        )

    conn.commit()
    conn.close()


def get_setting(key, default=None):
    """Get a setting value by key."""
    conn = get_db()
    row = conn.execute('SELECT value FROM settings WHERE key = ?', (key,)).fetchone()
    conn.close()
    if row:
        return row['value']
    return default


def set_setting(key, value):
    """Set a setting value."""
    conn = get_db()
    conn.execute(
        'INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)',
        (key, str(value))
    )
    conn.commit()
    conn.close()


def get_all_settings():
    """Get all settings as a dictionary."""
    conn = get_db()
    rows = conn.execute('SELECT key, value FROM settings').fetchall()
    conn.close()
    return {row['key']: row['value'] for row in rows}
