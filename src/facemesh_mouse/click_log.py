"""Rotating local log of every gesture-fired mouse action.

Never sent anywhere -- a plain text file in the app directory, capped by
rotation so it can't grow without bound. Attaching a handler is opt-in via
`enable()`; until that's called, `record()` is a no-op that never touches
the filesystem, so disabling logging in the GUI costs nothing per click.
"""
from __future__ import annotations

import ctypes
import logging
import logging.handlers
from pathlib import Path
from typing import Callable

LOG_PATH = "clicks.log"

_logger = logging.getLogger("facemesh_mouse.clicks")
_logger.setLevel(logging.INFO)
_logger.propagate = False


def enable(
    path: str | Path = LOG_PATH,
    max_bytes: int = 1_000_000,
    backup_count: int = 3,
) -> None:
    """Attaches the rotating file handler. Safe to call more than once --
    a second call is a no-op, so it never doubles up handlers."""
    if any(isinstance(h, logging.handlers.RotatingFileHandler) for h in _logger.handlers):
        return
    handler = logging.handlers.RotatingFileHandler(
        path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    _logger.addHandler(handler)


def disable() -> None:
    for handler in list(_logger.handlers):
        _logger.removeHandler(handler)
        handler.close()


def _foreground_window_title() -> str:
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        buffer = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buffer, length + 1)
        return buffer.value or "?"
    except Exception:
        # A missing/renamed window mid-transition must never break logging
        # or crash the caller -- "?" is a fine record for a rare edge case.
        return "?"


def record(
    gesture_name: str,
    action: str,
    position: tuple[int, int],
    window_title_fn: Callable[[], str] = _foreground_window_title,
) -> None:
    if not _logger.handlers:
        return
    title = window_title_fn() or "?"
    _logger.info(
        '%s %s (%d, %d) "%s"', gesture_name, action, position[0], position[1], title
    )
