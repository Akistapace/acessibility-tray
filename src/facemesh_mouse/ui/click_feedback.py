"""Click-through visual pulse shown at the cursor when a gesture fires an
action.

A borderless, always-on-top ring that expands and fades over ~300ms, then
destroys itself. Click-through is essential: without it the overlay window
would intercept the very next click, which would be actively harmful for a
tool whose whole purpose is clicking.

The click-through recipe (GetParent(winfo_id()) + WS_EX_TRANSPARENT) was
verified against this project's actual Tcl/Tk build: winfo_id() returns a
Tk-internal child window, and the real top-level HWND Windows composites --
the one that must carry the extended styles -- is its parent. Verifying the
visual result requires PrintWindow with PW_RENDERFULLCONTENT; a plain
BitBlt/CopyFromScreen capture does not correctly show a layered window.
"""
from __future__ import annotations

import ctypes
import tkinter as tk

_DURATION_MS = 300
_STEPS = 10
_START_RADIUS = 6
_END_RADIUS = 28
_RING_COLOR = "#4da3ff"

_LOCK_DURATION_MS = 500
_LOCK_GLYPH = "🔒"
_UNLOCK_GLYPH = "🔓"
_LOCK_COLOR = "#ffc94d"

_TOOLTIP_DURATION_MS = 2500
_TOOLTIP_BG = "#2b2b2b"
_TOOLTIP_FG = "white"

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080


def _make_click_through(window: tk.Toplevel) -> None:
    hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
    styles = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    ctypes.windll.user32.SetWindowLongW(
        hwnd, GWL_EXSTYLE, styles | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW
    )


def show_pulse(parent: tk.Misc, x: int, y: int, color: str = _RING_COLOR) -> tk.Toplevel | None:
    """Shows one expanding ring centered on (x, y), in screen coordinates.
    `color` defaults to the standard click ring; callers use a different
    one to distinguish outcomes (e.g. action_buttons.py's warning pulse
    when the touch keyboard silently declines to open). Returns the
    Toplevel (mainly so tests can inspect it) -- callers driving the real
    app can ignore the return value."""
    try:
        return _show_pulse(parent, x, y, color)
    except Exception as exc:  # noqa: BLE001 - a missing pulse must never crash tracking
        print(f"facemesh-mouse: click pulse failed ({exc!r})")
        return None


def _show_pulse(parent: tk.Misc, x: int, y: int, color: str = _RING_COLOR) -> tk.Toplevel:
    size = _END_RADIUS * 2 + 4
    window = tk.Toplevel(parent)
    window.overrideredirect(True)
    window.attributes("-topmost", True)
    window.attributes("-transparentcolor", "black")
    window.configure(bg="black")
    window.geometry(f"{size}x{size}+{x - size // 2}+{y - size // 2}")

    canvas = tk.Canvas(window, width=size, height=size, bg="black", highlightthickness=0)
    canvas.pack()

    window.update_idletasks()
    _make_click_through(window)

    center = size / 2

    def step(index: int) -> None:
        if not window.winfo_exists():
            return
        canvas.delete("all")
        if index > _STEPS:
            window.destroy()
            return
        progress = index / _STEPS
        radius = _START_RADIUS + (_END_RADIUS - _START_RADIUS) * progress
        canvas.create_oval(
            center - radius, center - radius, center + radius, center + radius,
            outline=color, width=3,
        )
        window.after(_DURATION_MS // _STEPS, step, index + 1)

    step(0)
    return window


def show_tooltip(parent: tk.Misc, x: int, y: int, text: str) -> tk.Toplevel | None:
    """Shows a small text bubble centered above (x, y) for a couple
    seconds, then disappears on its own -- click-through, like the pulse.
    Used where a color-coded pulse alone doesn't explain *why* (e.g.
    action_buttons.py's warning when the touch keyboard silently declines
    to open)."""
    try:
        return _show_tooltip(parent, x, y, text)
    except Exception as exc:  # noqa: BLE001 - a missing tooltip must never crash tracking
        print(f"facemesh-mouse: tooltip failed ({exc!r})")
        return None


def _show_tooltip(parent: tk.Misc, x: int, y: int, text: str) -> tk.Toplevel:
    window = tk.Toplevel(parent)
    window.overrideredirect(True)
    window.attributes("-topmost", True)

    tk.Label(
        window, text=text, bg=_TOOLTIP_BG, fg=_TOOLTIP_FG, font=("Segoe UI", 10), padx=10, pady=6
    ).pack()

    window.update_idletasks()
    width, height = window.winfo_reqwidth(), window.winfo_reqheight()
    window.geometry(f"{width}x{height}+{x - width // 2}+{y - height - 16}")
    window.update_idletasks()
    _make_click_through(window)

    def expire() -> None:
        if window.winfo_exists():
            window.destroy()

    window.after(_TOOLTIP_DURATION_MS, expire)
    return window


def show_lock_pulse(parent: tk.Misc, x: int, y: int, locked: bool) -> tk.Toplevel | None:
    """Shows a brief lock/unlock glyph centered on (x, y) -- called right
    after freeze_cursor toggles, `locked=True` when it just engaged,
    `False` when it just released. Not a persistent indicator: it fades out
    the same way the click pulse does, just slower, so it reads as
    confirmation of the toggle rather than an always-on frozen-state icon."""
    try:
        return _show_lock_pulse(parent, x, y, locked)
    except Exception as exc:  # noqa: BLE001 - a missing pulse must never crash tracking
        print(f"facemesh-mouse: lock pulse failed ({exc!r})")
        return None


def _show_lock_pulse(parent: tk.Misc, x: int, y: int, locked: bool) -> tk.Toplevel:
    size = _END_RADIUS * 2 + 4
    window = tk.Toplevel(parent)
    window.overrideredirect(True)
    window.attributes("-topmost", True)
    window.attributes("-transparentcolor", "black")
    window.configure(bg="black")
    window.geometry(f"{size}x{size}+{x - size // 2}+{y - size // 2}")

    canvas = tk.Canvas(window, width=size, height=size, bg="black", highlightthickness=0)
    canvas.pack()

    window.update_idletasks()
    _make_click_through(window)

    center = size / 2
    glyph = _LOCK_GLYPH if locked else _UNLOCK_GLYPH

    def step(index: int) -> None:
        if not window.winfo_exists():
            return
        canvas.delete("all")
        if index > _STEPS:
            window.destroy()
            return
        progress = index / _STEPS
        radius = _START_RADIUS + (_END_RADIUS - _START_RADIUS) * progress
        canvas.create_oval(
            center - radius, center - radius, center + radius, center + radius,
            outline=_LOCK_COLOR, width=3,
        )
        canvas.create_text(center, center, text=glyph, font=("Segoe UI Emoji", 18))
        window.after(_LOCK_DURATION_MS // _STEPS, step, index + 1)

    step(0)
    return window
