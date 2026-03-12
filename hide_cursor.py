#!/usr/bin/env python3
"""Background process that hides the X11 cursor using XFixes.

XFixes cursor hide is tied to the X client connection lifetime,
so this script must stay running to keep the cursor hidden.
Kill this process to restore the cursor.
"""
import ctypes
import signal
import sys
import os

def main():
    display = os.environ.get('DISPLAY', ':0')

    xlib = ctypes.cdll.LoadLibrary('libX11.so.6')
    xfixes = ctypes.cdll.LoadLibrary('libXfixes.so.3')

    xlib.XOpenDisplay.argtypes = [ctypes.c_char_p]
    xlib.XOpenDisplay.restype = ctypes.c_void_p
    xlib.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
    xlib.XDefaultRootWindow.restype = ctypes.c_ulong
    xlib.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
    xlib.XCloseDisplay.argtypes = [ctypes.c_void_p]
    xfixes.XFixesHideCursor.argtypes = [ctypes.c_void_p, ctypes.c_ulong]

    d = xlib.XOpenDisplay(display.encode())
    if not d:
        print(f'Cannot open display {display}', file=sys.stderr)
        sys.exit(1)

    root = xlib.XDefaultRootWindow(d)
    xfixes.XFixesHideCursor(d, root)
    xlib.XSync(d, False)

    # Sleep forever — cursor stays hidden while this process lives
    signal.pause()

if __name__ == '__main__':
    main()
