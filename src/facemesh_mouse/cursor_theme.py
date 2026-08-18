"""Applies/restores the real Windows Arrow cursor via the same mechanism
Windows' own Accessibility > Mouse pointer settings use: write a .cur file,
point HKCU\\Control Panel\\Cursors\\Arrow at it, and call
SystemParametersInfoW(SPI_SETCURSORS) to reload it everywhere. Only the
Arrow role is ever touched. A failure here must never affect tracking --
same rule as virtual_keyboard.py.
"""
from __future__ import annotations

import ctypes
import json
import os
import sys
import winreg
from pathlib import Path

from .modules import cursor_image

_CURSOR_DIR = Path(os.environ.get("LOCALAPPDATA", ".")) / "FaceMeshMouse" / "cursors"
_CUR_FILENAME = "arrow.cur"
_STASH_FILENAME = "original_arrow.json"

_CURSORS_KEY = r"Control Panel\Cursors"
_ARROW_VALUE = "Arrow"

_SPI_SETCURSORS = 0x0057
_SPIF_SENDCHANGE = 0x0002

_DEFAULT_SIZE_PX = 32
_MODE_COLORS = {
    "default": (0, 0, 0),
    "white": (255, 255, 255),
    "black": (0, 0, 0),
}


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    hex_color = hex_color.lstrip("#")
    return (int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16))


def _stash_original_if_needed(cursor_dir: Path) -> None:
    stash_path = cursor_dir / _STASH_FILENAME
    if stash_path.exists():
        return
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _CURSORS_KEY) as key:
            value, _ = winreg.QueryValueEx(key, _ARROW_VALUE)
    except FileNotFoundError:
        value = None
    cursor_dir.mkdir(parents=True, exist_ok=True)
    stash_path.write_text(json.dumps({"value": value}), encoding="utf-8")


def _write_arrow_registry(value: str | None) -> None:
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, _CURSORS_KEY) as key:
        if value is None:
            try:
                winreg.DeleteValue(key, _ARROW_VALUE)
            except FileNotFoundError:
                pass
        else:
            winreg.SetValueEx(key, _ARROW_VALUE, 0, winreg.REG_SZ, value)
    ctypes.windll.user32.SystemParametersInfoW(_SPI_SETCURSORS, 0, None, _SPIF_SENDCHANGE)


def apply_cursor(
    size_px: int, mode: str, custom_color: str, cursor_dir: Path = _CURSOR_DIR
) -> None:
    if size_px == _DEFAULT_SIZE_PX and mode == "default":
        return
    try:
        effective_mode = mode if mode in cursor_image.VALID_MODES else "default"
        if effective_mode == "mista":
            cur_bytes = cursor_image.build_cur_bytes_mista(size_px)
        else:
            fill = _hex_to_rgb(custom_color) if effective_mode == "custom" else _MODE_COLORS[effective_mode]
            image = cursor_image.render_color_bitmap(size_px, fill)
            cur_bytes = cursor_image.build_cur_bytes_color(image)

        _stash_original_if_needed(cursor_dir)
        cursor_dir.mkdir(parents=True, exist_ok=True)
        cur_path = cursor_dir / _CUR_FILENAME
        cur_path.write_bytes(cur_bytes)
        _write_arrow_registry(str(cur_path))
    except Exception as exc:  # noqa: BLE001 - a cursor theme failure must never affect tracking
        print(f"facemesh-mouse: cursor theme apply failed ({exc!r})", file=sys.stderr)


def restore_cursor(cursor_dir: Path = _CURSOR_DIR) -> None:
    stash_path = cursor_dir / _STASH_FILENAME
    if not stash_path.exists():
        return
    try:
        stash = json.loads(stash_path.read_text(encoding="utf-8"))
        _write_arrow_registry(stash.get("value"))
        stash_path.unlink()
    except Exception as exc:  # noqa: BLE001 - see apply_cursor
        print(f"facemesh-mouse: cursor theme restore failed ({exc!r})", file=sys.stderr)
