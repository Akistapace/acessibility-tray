# Cursor Appearance (Size / Color / Mista) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user adjust the real Windows Arrow cursor's size, a solid color, or a "mista" (true per-pixel-invert) mode from the app's own config window, applied live and restored on app exit.

**Architecture:** A pure bitmap-generation module (`cursor_image.py`, no filesystem/registry) builds the arrow silhouette and serializes it into a legacy (non-PNG) `.cur` file. A thin OS-integration module (`cursor_theme.py`) writes that file to disk, points `HKCU\Control Panel\Cursors\Arrow` at it via `winreg`, and reloads it system-wide via `SystemParametersInfoW(SPI_SETCURSORS)` — the same mechanism Windows' own Accessibility pointer settings use. `backend.py` wires a new IPC command to it, re-applies a saved theme at startup, and restores the original cursor on graceful shutdown. The Electron config window gets a new debounced-live-apply section in the Extras tab.

**Tech Stack:** Python 3.11, `Pillow` (already a dependency), `ctypes`/`winreg` (stdlib, same pattern as `virtual_keyboard.py`), TypeScript/Electron renderer (no new npm dependency).

**Spec:** `docs/superpowers/specs/2026-08-18-cursor-appearance-design.md`

## Global Constraints

- Windows-only — no cross-platform guards needed, matching `virtual_keyboard.py`'s unconditional `import winreg`/`ctypes.windll` at module scope.
- Only the `Arrow` cursor role is ever touched. The other 16 Windows cursor roles are left alone.
- `.cur` files use the legacy (non-PNG) combined XOR+AND DIB format — no PNG payload.
- `size_px == 32` (Windows' own default) and `mode == "default"` together must be a complete no-op: no registry read, no file write. An existing user who never opens this section sees zero behavior change.
- `CURSOR_SIZE_RANGE = (32, 96)`. Valid `mode` values: `default`, `white`, `black`, `custom`, `mista`. An invalid `mode` falls back to `"default"`.
- Registry/`ctypes` calls are never unit-tested against the real OS — monkeypatched in tests, matching `test_virtual_keyboard.py`'s existing convention. Real behavior is manual-checklist-verified.
- Any failure inside `cursor_theme.py` is caught and printed to stderr, never raised to its caller — matching `virtual_keyboard.py`'s and `BackendServer.handle_command`'s existing "a secondary feature must never crash tracking" rule.

---

### Task 1: `cursor_image.py` — pure arrow bitmap + `.cur` byte generation

**Files:**
- Create: `src/facemesh_mouse/modules/cursor_image.py`
- Test: `tests/test_cursor_image.py`

**Interfaces:**
- Consumes: nothing (pure, stdlib + Pillow only).
- Produces (used by Task 3):
  - `VALID_MODES: set[str]` — `{"default", "white", "black", "custom", "mista"}`
  - `render_color_bitmap(size_px: int, fill: tuple[int, int, int]) -> PIL.Image.Image` — RGBA, `size_px`×`size_px`.
  - `build_cur_bytes_color(image: PIL.Image.Image) -> bytes`
  - `build_cur_bytes_mista(size_px: int) -> bytes`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_cursor_image.py
import struct

from facemesh_mouse.modules import cursor_image


def test_arrow_mask_tip_is_inside_and_far_corner_is_outside():
    mask = cursor_image._arrow_mask(32)
    assert mask.getpixel((0, 0)) == 255       # the tip, first polygon vertex
    assert mask.getpixel((31, 31)) == 0        # opposite corner, outside the silhouette


def test_contrast_outline_color_picks_black_on_a_light_fill():
    assert cursor_image._contrast_outline_color((255, 255, 255)) == (0, 0, 0)


def test_contrast_outline_color_picks_white_on_a_dark_fill():
    assert cursor_image._contrast_outline_color((0, 0, 0)) == (255, 255, 255)


def test_render_color_bitmap_is_transparent_outside_the_silhouette():
    image = cursor_image.render_color_bitmap(32, (255, 0, 0))
    assert image.getpixel((31, 31))[3] == 0


def test_render_color_bitmap_is_opaque_fill_color_at_the_tip():
    image = cursor_image.render_color_bitmap(32, (255, 0, 0))
    r, g, b, a = image.getpixel((1, 1))
    assert a == 255
    assert (r, g, b) == (255, 0, 0)


def test_pack_1bpp_rows_pads_each_row_to_a_four_byte_boundary():
    # width=8 -> 1 real byte of bits + 3 bytes of padding per row
    packed = cursor_image._pack_1bpp_rows(8, lambda x, y: True)
    assert len(packed) == 8 * 4
    assert packed[0] == 0xFF
    assert packed[1:4] == b"\x00\x00\x00"


def test_pack_1bpp_rows_is_bottom_up():
    # Only the top row (y=0) is set; bottom-up storage puts it in the LAST row block.
    packed = cursor_image._pack_1bpp_rows(8, lambda x, y: y == 0)
    assert packed[-4] == 0xFF
    assert packed[0] == 0x00


def test_build_cur_bytes_color_has_a_cursor_type_icondir_header():
    image = cursor_image.render_color_bitmap(32, (0, 0, 0))
    data = cursor_image.build_cur_bytes_color(image)
    reserved, id_type, count = struct.unpack_from("<HHH", data, 0)
    assert (reserved, id_type, count) == (0, 2, 1)


def test_build_cur_bytes_color_entry_declares_32x32_and_32bpp():
    image = cursor_image.render_color_bitmap(32, (0, 0, 0))
    data = cursor_image.build_cur_bytes_color(image)
    width, height = struct.unpack_from("<BB", data, 6)
    assert (width, height) == (32, 32)
    bmi_offset = 6 + 16
    _size, _w, bi_height, _planes, bit_count = struct.unpack_from("<IiiHH", data, bmi_offset)
    assert bit_count == 32
    assert bi_height == 64  # 2x actual height (XOR + AND)


def test_build_cur_bytes_mista_is_1bpp_with_a_fully_set_and_mask():
    data = cursor_image.build_cur_bytes_mista(32)
    bmi_offset = 6 + 16
    _size, _w, _h, _planes, bit_count = struct.unpack_from("<IiiHH", data, bmi_offset)
    assert bit_count == 1
    xor_len = 32 * 4  # row_bytes(4) * 32 rows, 1bpp padded to a 4-byte boundary
    and_start = bmi_offset + 40 + 8 + xor_len  # header + 2-entry color table + xor mask
    assert data[and_start] == 0xFF
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\pytest tests/test_cursor_image.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'facemesh_mouse.modules.cursor_image'`

- [ ] **Step 3: Write the implementation**

```python
# src/facemesh_mouse/modules/cursor_image.py
"""Pure cursor bitmap / .cur-file generation -- no filesystem, no registry,
no ctypes. Builds an arrow silhouette and serializes it into the classic
(non-PNG) .cur container: ICONDIR + one ICONDIRENTRY + a combined XOR+AND
legacy DIB image, the same layout every .cur file has used since Windows
3.1. See docs/superpowers/specs/2026-08-18-cursor-appearance-design.md.
"""
from __future__ import annotations

import struct

from PIL import Image, ImageDraw

# Arrow silhouette as a fraction of the bitmap's own side length, tip at the
# origin (top-left) -- the polygon's first vertex is always the cursor's
# hotspot.
_ARROW_POINTS_FRACTION = [
    (0.0, 0.0), (0.0, 0.62), (0.18, 0.48),
    (0.29, 0.72), (0.40, 0.67), (0.29, 0.44), (0.5, 0.44),
]

VALID_MODES = {"default", "white", "black", "custom", "mista"}


def _polygon_points(size_px: int) -> list[tuple[float, float]]:
    return [(x * size_px, y * size_px) for x, y in _ARROW_POINTS_FRACTION]


def _arrow_mask(size_px: int) -> Image.Image:
    """1-channel mask, 255 inside the arrow silhouette, 0 outside."""
    mask = Image.new("L", (size_px, size_px), 0)
    ImageDraw.Draw(mask).polygon(_polygon_points(size_px), fill=255)
    return mask


def _contrast_outline_color(fill: tuple[int, int, int]) -> tuple[int, int, int]:
    """Black outline on a light fill, white outline on a dark fill --
    relative luminance (ITU-R BT.601) thresholded at the midpoint. A static
    one-time contrast choice -- "mista" mode is what protects against an
    arbitrary/changing background, this is just so a solid-color arrow
    doesn't disappear against a same-color background at the moment it's
    picked."""
    r, g, b = fill
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    return (0, 0, 0) if luminance > 127 else (255, 255, 255)


def render_color_bitmap(size_px: int, fill: tuple[int, int, int]) -> Image.Image:
    """RGBA arrow: `fill` inside, a contrasting outline traced on the
    silhouette edge, fully transparent outside."""
    mask = _arrow_mask(size_px)
    outline = _contrast_outline_color(fill)
    image = Image.new("RGBA", (size_px, size_px), (0, 0, 0, 0))
    ImageDraw.Draw(image).polygon(
        _polygon_points(size_px), fill=(*fill, 255), outline=(*outline, 255)
    )
    image.putalpha(mask)
    return image


def _pack_1bpp_rows(size_px: int, bit_is_set) -> bytes:
    """`bit_is_set(x, y) -> bool` for a size_px x size_px grid. Returns
    bottom-up rows (DIB convention), each padded to a 4-byte boundary, MSB
    of each byte = the leftmost pixel of that byte's 8-pixel span -- the
    shared row layout both the AND and XOR 1bpp masks use."""
    row_bytes = ((size_px + 31) // 32) * 4
    out = bytearray()
    for y in range(size_px - 1, -1, -1):
        row = bytearray(row_bytes)
        for x in range(size_px):
            if bit_is_set(x, y):
                row[x // 8] |= 0x80 >> (x % 8)
        out += row
    return bytes(out)


def _pack_32bpp_rows(image: Image.Image) -> bytes:
    """Bottom-up BGRA rows -- DIB byte order, not Pillow's RGBA."""
    size_px = image.width
    px = image.load()
    out = bytearray()
    for y in range(size_px - 1, -1, -1):
        for x in range(size_px):
            r, g, b, a = px[x, y]
            out += bytes((b, g, r, a))
    return bytes(out)


def _assemble_cur(
    size_px: int, bit_count: int, xor_data: bytes, and_data: bytes, hotspot: tuple[int, int]
) -> bytes:
    bmi = struct.pack(
        "<IiiHHIIiiII",
        40,  # biSize
        size_px,  # biWidth
        size_px * 2,  # biHeight -- combined XOR + AND
        1,  # biPlanes
        bit_count,  # biBitCount
        0,  # biCompression (BI_RGB)
        len(xor_data) + len(and_data),  # biSizeImage
        0, 0,  # biXPelsPerMeter, biYPelsPerMeter
        0, 0,  # biClrUsed, biClrImportant
    )
    # DIB rule: bpp<=8 requires a palette. The values are irrelevant here
    # (the mask bits, not palette indices, drive AND/XOR interpretation) --
    # only its presence is required for the header to be valid.
    color_table = bytes([0, 0, 0, 0, 255, 255, 255, 0]) if bit_count <= 8 else b""
    image_data = bmi + color_table + xor_data + and_data

    icondir = struct.pack("<HHH", 0, 2, 1)  # idType=2 -> cursor, idCount=1
    side = size_px if size_px < 256 else 0  # 0 means 256 in the ICO/CUR format
    icondirentry = struct.pack(
        "<BBBBHHII",
        side, side, 0, 0,
        hotspot[0], hotspot[1],
        len(image_data),
        6 + 16,  # offset: ICONDIR (6 bytes) + this one ICONDIRENTRY (16 bytes)
    )
    return icondir + icondirentry + image_data


def build_cur_bytes_color(image: Image.Image) -> bytes:
    size_px = image.width
    xor_data = _pack_32bpp_rows(image)
    px = image.load()
    and_data = _pack_1bpp_rows(size_px, lambda x, y: px[x, y][3] == 0)
    return _assemble_cur(size_px, bit_count=32, xor_data=xor_data, and_data=and_data, hotspot=(0, 0))


def build_cur_bytes_mista(size_px: int) -> bytes:
    """The classic invert-cursor trick: AND=1 everywhere (nothing is ever
    fully opaque-covered), XOR=1 only inside the arrow silhouette. Where
    AND=1,XOR=1 the compositor inverts the destination pixel; where
    AND=1,XOR=0 it's untouched -- so the silhouette inverts the screen
    under it and everywhere else is fully see-through, with zero ongoing
    cost to this app."""
    mask = _arrow_mask(size_px)
    mpx = mask.load()
    and_data = _pack_1bpp_rows(size_px, lambda x, y: True)
    xor_data = _pack_1bpp_rows(size_px, lambda x, y: mpx[x, y] > 127)
    return _assemble_cur(size_px, bit_count=1, xor_data=xor_data, and_data=and_data, hotspot=(0, 0))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\pytest tests/test_cursor_image.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/facemesh_mouse/modules/cursor_image.py tests/test_cursor_image.py
git commit -m "feat(cursor): add pure arrow bitmap and .cur file generation"
```

---

### Task 2: `CursorConfig` in `config.py`

**Files:**
- Modify: `src/facemesh_mouse/modules/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: nothing new.
- Produces (used by Task 4):
  - `CursorConfig` dataclass: `size_px: int = 32`, `mode: str = "default"`, `custom_color: str = "#000000"`.
  - `AppConfig.cursor: CursorConfig`.
  - `CURSOR_SIZE_RANGE: tuple[int, int]` = `(32, 96)`.
  - `VALID_CURSOR_MODES: set[str]`.
  - `cursor_from_dict(raw_cursor: dict) -> CursorConfig` — public, called both by `config_from_dict` internally and directly by Task 4's `_cmd_set_cursor_theme`.
  - `config_to_dict`/`config_from_dict` include a `"cursor"` key shaped like `{"size_px": int, "mode": str, "custom_color": str}`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_config.py`:

```python
def test_default_config_has_the_default_cursor_theme():
    cursor = config_mod.default_config().cursor
    assert cursor.size_px == 32
    assert cursor.mode == "default"
    assert cursor.custom_color == "#000000"


def test_cursor_fields_round_trip(tmp_path):
    path = tmp_path / "config.json"
    original = config_mod.default_config()
    original.cursor.size_px = 64
    original.cursor.mode = "mista"
    original.cursor.custom_color = "#ff8800"

    config_mod.save_config(path, original)
    loaded = config_mod.load_config(path)

    assert loaded.cursor.size_px == 64
    assert loaded.cursor.mode == "mista"
    assert loaded.cursor.custom_color == "#ff8800"


def test_load_config_clamps_out_of_range_cursor_size(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"cursor": {"size_px": 999, "mode": "custom"}}))

    loaded = config_mod.load_config(path)

    assert loaded.cursor.size_px == config_mod.CURSOR_SIZE_RANGE[1]


def test_load_config_invalid_cursor_mode_falls_back_to_default(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"cursor": {"mode": "rainbow"}}))

    loaded = config_mod.load_config(path)

    assert loaded.cursor.mode == "default"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\pytest tests/test_config.py -v`
Expected: FAIL with `AttributeError: 'AppConfig' object has no attribute 'cursor'`

- [ ] **Step 3: Write the implementation**

Add near `ActionButtonsConfig` in `src/facemesh_mouse/modules/config.py`:

```python
CURSOR_SIZE_RANGE = (32, 96)
VALID_CURSOR_MODES = {"default", "white", "black", "custom", "mista"}


@dataclass
class CursorConfig:
    """The real Windows Arrow cursor's theme. size_px==32 and mode=="default"
    together mean "untouched" -- see cursor_theme.apply_cursor's no-op
    guard, which this config's defaults are built to trigger."""

    size_px: int = 32
    mode: str = "default"
    custom_color: str = "#000000"
```

Add `cursor: CursorConfig = field(default_factory=CursorConfig)` to `AppConfig`.

Add a clamp helper next to `_clamped`/`_optional_float`:

```python
def _clamped_cursor_size(raw_cursor: dict, fallback: int) -> int:
    low, high = CURSOR_SIZE_RANGE
    try:
        value = int(raw_cursor.get("size_px", fallback))
    except (TypeError, ValueError):
        value = fallback
    return max(low, min(high, value))


def cursor_from_dict(raw_cursor: dict) -> CursorConfig:
    """Public (unlike `_merge_gesture`) because backend.py's
    `_cmd_set_cursor_theme` (Task 4) calls this directly with a single
    command's fields, not just from `config_from_dict`'s full-document
    parse -- both need the exact same clamp/fallback rules."""
    default = CursorConfig()
    mode = raw_cursor.get("mode", default.mode)
    if mode not in VALID_CURSOR_MODES:
        mode = default.mode
    custom_color = raw_cursor.get("custom_color", default.custom_color)
    if not isinstance(custom_color, str):
        custom_color = default.custom_color
    return CursorConfig(
        size_px=_clamped_cursor_size(raw_cursor, default.size_px),
        mode=mode,
        custom_color=custom_color,
    )
```

In `config_to_dict`, add: `"cursor": asdict(config.cursor),`

In `config_from_dict`, add `cursor = cursor_from_dict(raw.get("cursor", {}))` and pass
`cursor=cursor` into the returned `AppConfig(...)`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\pytest tests/test_config.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/facemesh_mouse/modules/config.py tests/test_config.py
git commit -m "feat(cursor): add CursorConfig to AppConfig"
```

---

### Task 3: `cursor_theme.py` — apply/restore via registry + `SystemParametersInfo`

**Files:**
- Create: `src/facemesh_mouse/cursor_theme.py`
- Test: `tests/test_cursor_theme.py`

**Interfaces:**
- Consumes: `cursor_image.VALID_MODES`, `cursor_image.render_color_bitmap`, `cursor_image.build_cur_bytes_color`, `cursor_image.build_cur_bytes_mista` (Task 1).
- Produces (used by Task 4):
  - `apply_cursor(size_px: int, mode: str, custom_color: str, cursor_dir: Path = _CURSOR_DIR) -> None`
  - `restore_cursor(cursor_dir: Path = _CURSOR_DIR) -> None`
  - Both catch and print their own exceptions; never raise.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_cursor_theme.py
import json

import pytest
from unittest.mock import MagicMock

from facemesh_mouse import cursor_theme


@pytest.fixture(autouse=True)
def _no_real_registry_or_broadcast(monkeypatch):
    """Every test below drives cursor_theme through a tmp_path cursor_dir
    and a mocked winreg/SystemParametersInfoW -- none should touch the
    real Windows registry, mirroring test_virtual_keyboard.py's rule."""
    monkeypatch.setattr(cursor_theme.winreg, "OpenKey", MagicMock(side_effect=FileNotFoundError))
    monkeypatch.setattr(cursor_theme.winreg, "QueryValueEx", MagicMock())
    monkeypatch.setattr(cursor_theme.winreg, "CreateKeyEx", MagicMock())
    monkeypatch.setattr(cursor_theme.winreg, "SetValueEx", MagicMock())
    monkeypatch.setattr(cursor_theme.winreg, "DeleteValue", MagicMock())
    monkeypatch.setattr(
        cursor_theme.ctypes.windll.user32, "SystemParametersInfoW", MagicMock()
    )


def test_apply_cursor_is_a_no_op_at_the_untouched_defaults(tmp_path):
    cursor_theme.apply_cursor(32, "default", "#000000", cursor_dir=tmp_path)

    cursor_theme.winreg.CreateKeyEx.assert_not_called()
    assert not (tmp_path / "arrow.cur").exists()


def test_apply_cursor_writes_a_cur_file_and_sets_the_registry(tmp_path):
    cursor_theme.apply_cursor(48, "white", "#000000", cursor_dir=tmp_path)

    assert (tmp_path / "arrow.cur").exists()
    (_key, name, _reserved, _kind, value), _kwargs = cursor_theme.winreg.SetValueEx.call_args
    assert name == cursor_theme._ARROW_VALUE
    assert value == str(tmp_path / "arrow.cur")
    cursor_theme.ctypes.windll.user32.SystemParametersInfoW.assert_called_once_with(
        cursor_theme._SPI_SETCURSORS, 0, None, cursor_theme._SPIF_SENDCHANGE
    )


def test_apply_cursor_stashes_the_original_registry_value_once(tmp_path):
    cursor_theme.winreg.QueryValueEx.return_value = ("C:\\some\\original.cur", 1)

    cursor_theme.apply_cursor(32, "black", "#000000", cursor_dir=tmp_path)
    stash = json.loads((tmp_path / "original_arrow.json").read_text())
    assert stash == {"value": "C:\\some\\original.cur"}

    # A second apply must not re-stash over the real original with our own
    # previously-generated path.
    cursor_theme.winreg.QueryValueEx.return_value = ("should-not-be-stashed.cur", 1)
    cursor_theme.apply_cursor(64, "black", "#000000", cursor_dir=tmp_path)
    stash_again = json.loads((tmp_path / "original_arrow.json").read_text())
    assert stash_again == {"value": "C:\\some\\original.cur"}


def test_apply_cursor_stashes_none_when_no_original_value_exists(tmp_path):
    cursor_theme.winreg.OpenKey.side_effect = FileNotFoundError

    cursor_theme.apply_cursor(32, "black", "#000000", cursor_dir=tmp_path)

    stash = json.loads((tmp_path / "original_arrow.json").read_text())
    assert stash == {"value": None}


def test_restore_cursor_writes_back_the_stashed_value_and_deletes_the_stash(tmp_path):
    (tmp_path / "original_arrow.json").write_text(json.dumps({"value": "C:\\original.cur"}))

    cursor_theme.restore_cursor(cursor_dir=tmp_path)

    (_key, name, _reserved, _kind, value), _kwargs = cursor_theme.winreg.SetValueEx.call_args
    assert name == cursor_theme._ARROW_VALUE
    assert value == "C:\\original.cur"
    assert not (tmp_path / "original_arrow.json").exists()


def test_restore_cursor_deletes_the_value_when_original_was_absent(tmp_path):
    (tmp_path / "original_arrow.json").write_text(json.dumps({"value": None}))

    cursor_theme.restore_cursor(cursor_dir=tmp_path)

    cursor_theme.winreg.DeleteValue.assert_called_once()


def test_restore_cursor_is_a_no_op_when_nothing_was_ever_applied(tmp_path):
    cursor_theme.restore_cursor(cursor_dir=tmp_path)

    cursor_theme.winreg.SetValueEx.assert_not_called()
    cursor_theme.winreg.DeleteValue.assert_not_called()


def test_apply_cursor_survives_a_registry_failure(tmp_path, capsys):
    cursor_theme.winreg.CreateKeyEx.side_effect = OSError("access denied")

    cursor_theme.apply_cursor(48, "white", "#000000", cursor_dir=tmp_path)  # must not raise

    assert "cursor theme" in capsys.readouterr().err
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\pytest tests/test_cursor_theme.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'facemesh_mouse.cursor_theme'`

- [ ] **Step 3: Write the implementation**

```python
# src/facemesh_mouse/cursor_theme.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\pytest tests/test_cursor_theme.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/facemesh_mouse/cursor_theme.py tests/test_cursor_theme.py
git commit -m "feat(cursor): apply/restore the real Windows Arrow cursor"
```

---

### Task 4: `backend.py` wiring — command, startup re-apply, shutdown restore

**Files:**
- Modify: `src/facemesh_mouse/backend.py`
- Test: `tests/test_backend.py`

**Interfaces:**
- Consumes: `cursor_theme.apply_cursor`, `cursor_theme.restore_cursor` (Task 3); `config_mod.CursorConfig`, `AppConfig.cursor`, `config_mod.cursor_from_dict` (Task 2).
- Produces: IPC command `set_cursor_theme` (payload: `size_px`, `mode`, `custom_color`), consumed by Task 5's Electron UI.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_backend.py`:

```python
def test_set_cursor_theme_command_updates_config_and_calls_apply_cursor(monkeypatch):
    calls = []
    monkeypatch.setattr(
        backend.cursor_theme, "apply_cursor", lambda *a, **kw: calls.append((a, kw))
    )
    server = backend.BackendServer(Engine(config_mod.default_config()), config_mod.default_config())

    server.handle_command({
        "type": "set_cursor_theme",
        "size_px": 64,
        "mode": "mista",
        "custom_color": "#112233",
    })

    assert server.config.cursor.size_px == 64
    assert server.config.cursor.mode == "mista"
    assert server.config.cursor.custom_color == "#112233"
    assert calls == [((64, "mista", "#112233"), {})]


def test_set_cursor_theme_command_clamps_and_falls_back_like_config_loading(monkeypatch):
    monkeypatch.setattr(backend.cursor_theme, "apply_cursor", lambda *a, **kw: None)
    server = backend.BackendServer(Engine(config_mod.default_config()), config_mod.default_config())

    server.handle_command({
        "type": "set_cursor_theme",
        "size_px": 999,
        "mode": "not_a_real_mode",
        "custom_color": "#000000",
    })

    assert server.config.cursor.size_px == config_mod.CURSOR_SIZE_RANGE[1]
    assert server.config.cursor.mode == "default"


def test_save_config_command_merges_partial_cursor_payload_onto_disk(tmp_path):
    path = tmp_path / "config.json"
    saved = config_mod.default_config()
    saved.cursor.mode = "black"
    config_mod.save_config(path, saved)
    server = backend.BackendServer(
        Engine(config_mod.default_config()), config_mod.default_config(), config_path=str(path)
    )

    server.handle_command({
        "type": "save_config",
        "config": {"cursor": {"size_px": 80}},
    })

    reloaded = config_mod.load_config(path)
    assert reloaded.cursor.mode == "black"  # untouched field survives the merge
    assert reloaded.cursor.size_px == 80
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\pytest tests/test_backend.py -v`
Expected: FAIL — `set_cursor_theme` has no handler (silently does nothing, so
`server.config.cursor` stays at its default and the assertions fail); the
merge test fails with a `KeyError: 'cursor'` inside `_cmd_save_config`.

- [ ] **Step 3: Write the implementation**

Add the import near the other same-package imports in `backend.py`:

```python
from . import cursor_theme
```

Add a command handler (near `_cmd_update_config`):

```python
    def _cmd_set_cursor_theme(self, command: dict) -> None:
        self.config.cursor = config_mod.cursor_from_dict({
            "size_px": command.get("size_px"),
            "mode": command.get("mode"),
            "custom_color": command.get("custom_color"),
        })
        cursor_theme.apply_cursor(
            self.config.cursor.size_px, self.config.cursor.mode, self.config.cursor.custom_color
        )
```

In `_cmd_save_config`, alongside the existing `action_buttons` merge line, add:

```python
        if "cursor" in payload:
            merged["cursor"] = {**on_disk_dict["cursor"], **payload["cursor"]}
```

In `main()`, right after `config = config_mod.load_config(CONFIG_PATH)`, apply a saved theme at startup:

```python
    if (config.cursor.size_px, config.cursor.mode) != (32, "default"):
        cursor_theme.apply_cursor(
            config.cursor.size_px, config.cursor.mode, config.cursor.custom_color
        )
```

In `main()`'s existing shutdown block, restore on the way out:

```python
    try:
        for command in proto.read_messages(sys.stdin):
            server.handle_command(command)
    finally:
        stop.set()
        engine.stop()
        cursor_theme.restore_cursor()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\pytest tests/test_backend.py -v`
Expected: all PASS

- [ ] **Step 5: Run the full Python suite**

Run: `.venv\Scripts\pytest`
Expected: all PASS (no regressions in `test_config.py`, `test_cursor_image.py`, `test_cursor_theme.py`, etc.)

- [ ] **Step 6: Commit**

```bash
git add src/facemesh_mouse/backend.py tests/test_backend.py
git commit -m "feat(cursor): wire set_cursor_theme command, startup re-apply, shutdown restore"
```

---

### Task 5: Electron config UI — Extras tab section, live-apply

**Files:**
- Modify: `electron/src/renderer/config/index.html`
- Modify: `electron/src/renderer/config/index.ts`
- Modify: `electron/src/renderer/config/style.css`
- Modify: `README.md`

**Interfaces:**
- Consumes: IPC command `set_cursor_theme` (Task 4); `AppConfigJson.cursor` shape `{ size_px: number; mode: string; custom_color: string }` (mirrors `config_to_dict`'s `"cursor"` key from Task 2).
- Produces: nothing consumed by a later task — this is the plan's last functional task.

No new automated test for this file: `config/index.ts`'s existing wiring
(tab switching, save-button state, gesture rows) has no test file today
either — same precedent this task follows.

- [ ] **Step 1: Add the HTML section**

In `electron/src/renderer/config/index.html`, inside `#tab-extras`, right
before its `save-trigger` button:

```html
        <div class="cursor-section">
          <p class="hint">Aparência do cursor</p>
          <label>Tamanho da seta
            <input type="range" id="cursor_size_px" min="32" max="96" step="8" />
          </label>
          <label>Cor
            <select id="cursor_mode">
              <option value="default">Padrão do Windows</option>
              <option value="white">Branco</option>
              <option value="black">Preto</option>
              <option value="custom">Personalizada</option>
              <option value="mista">Mista (inverte com o fundo)</option>
            </select>
          </label>
          <label>Cor personalizada
            <input type="color" id="cursor_custom_color" />
          </label>
        </div>
```

- [ ] **Step 2: Wire config state in `index.ts`**

Extend `AppConfigJson` and `currentConfig`:

```typescript
interface AppConfigJson {
  calibration: Record<string, number | boolean>;
  gestures: Record<string, { action: string; threshold: number; cooldown_ms: number; hold_ms: number }>;
  action_buttons: { x: number | null; y: number | null };
  cursor: { size_px: number; mode: string; custom_color: string };
}

let currentConfig: AppConfigJson = {
  calibration: { /* ...unchanged... */ },
  gestures: {},
  action_buttons: { x: null, y: null },
  cursor: { size_px: 32, mode: "default", custom_color: "#000000" },
};
```

Extend `applyConfigToForm` and `readFormIntoConfig` (after the existing
`calibration` loops):

```typescript
function applyConfigToForm(): void {
  for (const [id, value] of Object.entries(currentConfig.calibration)) {
    const el = document.getElementById(id) as HTMLInputElement | null;
    if (!el) continue;
    if (el.type === "checkbox") el.checked = Boolean(value);
    else el.value = String(value);
  }
  (document.getElementById("cursor_size_px") as HTMLInputElement).value =
    String(currentConfig.cursor.size_px);
  (document.getElementById("cursor_mode") as HTMLSelectElement).value = currentConfig.cursor.mode;
  (document.getElementById("cursor_custom_color") as HTMLInputElement).value =
    currentConfig.cursor.custom_color;
  renderGestureRows();
}

function readFormIntoConfig(): void {
  for (const key of Object.keys(currentConfig.calibration)) {
    const el = document.getElementById(key) as HTMLInputElement | null;
    if (!el) continue;
    currentConfig.calibration[key] = el.type === "checkbox" ? el.checked : Number(el.value);
  }
  currentConfig.cursor = {
    size_px: Number((document.getElementById("cursor_size_px") as HTMLInputElement).value),
    mode: (document.getElementById("cursor_mode") as HTMLSelectElement).value,
    custom_color: (document.getElementById("cursor_custom_color") as HTMLInputElement).value,
  };
  for (const name of GESTURE_NAMES) {
    // ...unchanged...
  }
}
```

`configPayloadWithoutButtons` needs no change — `cursor` stays included
(this window is `cursor`'s sole owner, unlike `action_buttons`).

- [ ] **Step 3: Live-apply, debounced**

Add near the other top-level `document.getElementById(...).addEventListener`
wiring at the bottom of `index.ts`:

```typescript
const CURSOR_APPLY_DEBOUNCE_MS = 150;
let cursorApplyTimer: ReturnType<typeof setTimeout> | null = null;

function sendCursorTheme(): void {
  readFormIntoConfig();
  window.backend.send({ type: "set_cursor_theme", ...currentConfig.cursor });
}

["cursor_size_px", "cursor_mode", "cursor_custom_color"].forEach((id) => {
  document.getElementById(id)?.addEventListener("input", () => {
    if (cursorApplyTimer) clearTimeout(cursorApplyTimer);
    cursorApplyTimer = setTimeout(sendCursorTheme, CURSOR_APPLY_DEBOUNCE_MS);
  });
});
```

- [ ] **Step 4: Style the new section**

In `electron/src/renderer/config/style.css`, add:

```css
.cursor-section { display: flex; flex-direction: column; gap: 10px; }

input[type="color"] {
  width: 100%;
  height: 32px;
  padding: 2px;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 4px;
  cursor: pointer;
}
```

- [ ] **Step 5: Build and run the Electron test suite**

Run: `cd electron && npx tsc --noEmit -p tsconfig.json && npm test`
Expected: no type errors, all existing tests still PASS (this task adds no
new `.test.ts` file, matching `config/index.ts`'s existing precedent).

- [ ] **Step 6: Document the feature in README**

In `README.md`'s **Extras** bullet (currently describing only the
keyboard-button toggle), add a sentence covering the new section:
"Aparência do cursor" ajusta o tamanho da seta real do Windows e sua cor
(branco, preto, personalizada, ou "mista", que inverte a cor do que está
embaixo dela para nunca ficar invisível) — aplica na hora, e some junto
com o cursor original do Windows quando o app é fechado, a menos que você
clique em Salvar configurações.

- [ ] **Step 7: Commit**

```bash
git add electron/src/renderer/config/index.html electron/src/renderer/config/index.ts electron/src/renderer/config/style.css README.md
git commit -m "feat(cursor): add cursor appearance controls to the Extras tab"
```

---

### Task 6: Full-repo verification + manual checklist

**Files:** none (verification only).

- [ ] **Step 1: Run the full test suite**

```bash
.venv\Scripts\pytest
cd electron
npx tsc --noEmit -p tsconfig.json
npm test
```

Expected: all green.

- [ ] **Step 2: Manual checklist (real Windows, real cursor)**

1. `npm run dev` from `electron/` (with `.venv` activated first, per README).
2. Open the config window's Extras tab.
3. Drag the size slider — the real Windows arrow visibly grows/shrinks
   within ~150ms of releasing, no flicker while dragging.
4. Pick "Branco" — arrow turns white with a dark outline. Pick "Preto" —
   arrow turns black with a light outline.
5. Pick "Personalizada" and choose a color in the picker — arrow recolors
   to match.
6. Pick "Mista" — move the arrow over a plain white window and a plain
   black window (e.g. Notepad vs. a maximized black terminal); the arrow
   should stay visible in both, visibly inverting the pixels under it.
7. Close the app (window close button, or tray "Sair") — the real Windows
   arrow returns to exactly what it looked like before the app ever
   touched it.
8. Reopen the app after clicking "Salvar configurações" with a theme
   applied — the themed arrow reappears automatically at startup, with no
   slider interaction needed.
9. `git status` — confirm no stray `arrow.cur`/`original_arrow.json`
   artifacts under the repo (they belong under `%LOCALAPPDATA%`, not the
   project directory).

- [ ] **Step 3: Report results**

Summarize pass/fail for each checklist item before considering this plan
complete.

## Plan Self-Review

**Spec coverage:**
- Pure bitmap/`.cur` generation, including the AND/XOR "mista" mask → Task 1.
- `CursorConfig`, `CURSOR_SIZE_RANGE`, dict round-trip → Task 2.
- Registry apply/restore, first-touch stash guard, `SystemParametersInfo`
  reload, no-op at untouched defaults → Task 3.
- `set_cursor_theme` command, `_cmd_save_config` merge, startup re-apply,
  shutdown restore → Task 4.
- Extras-tab UI, debounced live-apply, `cursor` kept in the save payload,
  README documentation → Task 5.
- Manual verification of every OS-dependent behavior the spec calls out
  (visible resize/recolor, "mista" over both light and dark backgrounds,
  restore-on-exit, re-apply-on-restart) → Task 6.
- "Out of Scope" items (other cursor roles, DPI scaling, live pixel
  sampling, overlay/pulse changes, buttons/overlay window sync) — no task
  touches any of them, confirmed absent by construction.

**Placeholder scan:** no TBD/TODO; every code step is complete, runnable
code, not a description of code.

**Type consistency:** `apply_cursor(size_px: int, mode: str, custom_color: str, cursor_dir: Path)`
and `restore_cursor(cursor_dir: Path)` (Task 3) match exactly how Task 4
calls them. `CursorConfig`'s three fields (Task 2) match the dict keys
`_cmd_set_cursor_theme` reads (Task 4) and `AppConfigJson.cursor`'s shape
on the TypeScript side (Task 5). `cursor_image.VALID_MODES` (Task 1) is
the same set `CursorConfig`'s fallback logic and `cursor_theme.apply_cursor`
both check against (Tasks 2-3) — defined once, referenced everywhere else.
