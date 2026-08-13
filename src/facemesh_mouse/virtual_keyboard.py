"""Launches Windows' built-in on-screen keyboard.

The app doesn't build its own on-screen keyboard -- Windows already ships
one that's accessible from any focused app. This module only makes it
reachable through the same head-tracked cursor the rest of the app uses --
called from the floating keyboard button (see ui/keyboard_button.py).
"""
from __future__ import annotations

import subprocess


def open_virtual_keyboard() -> None:
    """Launches osk.exe. A failure here must never crash tracking, the
    tray, or the config window -- it's caught and printed, not raised."""
    try:
        subprocess.Popen(["osk.exe"])
    except Exception as exc:  # noqa: BLE001 - a missing keyboard must never crash tracking
        print(f"facemesh-mouse: could not launch osk.exe ({exc!r})")
