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


def show_pulse(parent: tk.Misc, x: int, y: int) -> tk.Toplevel | None:
    """Shows one expanding ring centered on (x, y), in screen coordinates.
    Returns the Toplevel (mainly so tests can inspect it) -- callers driving
    the real app can ignore the return value."""
    try:
        return _show_pulse(parent, x, y)
    except Exception as exc:  # noqa: BLE001 - a missing pulse must never crash tracking
        print(f"facemesh-mouse: click pulse failed ({exc!r})")
        return None


def _show_pulse(parent: tk.Misc, x: int, y: int) -> tk.Toplevel:
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
            outline=_RING_COLOR, width=3,
        )
        window.after(_DURATION_MS // _STEPS, step, index + 1)

    step(0)
    return window
