# Floating Keyboard Button Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the tray-menu-item and config-window-button entry points for the virtual-keyboard launcher with a single always-visible, draggable circular widget that opens Windows' on-screen keyboard on click.

**Architecture:** `AppConfig` gains a small `KeyboardButtonConfig` (saved x/y, `None` = never dragged). A new `keyboard_button.py` module draws a borderless, always-on-top, transparent-background circle (the same `-transparentcolor` trick `click_feedback.py` uses) with click-vs-drag detection bound directly on it; a click calls `virtual_keyboard.open_virtual_keyboard()`, a drag past a small threshold repositions the window and saves the new spot straight to `config.json`. `main.py` constructs it once at startup and keeps it alive for the process's life; the old tray item and config-window button are removed.

**Tech Stack:** Python 3.11, plain `tkinter` (not CustomTkinter — matches `click_feedback.py`'s reason: needs raw Win32 window-style access), pytest.

## Global Constraints

- Every new module keeps `from __future__ import annotations` as its first import.
- UI strings stay in Portuguese with correct diacritics.
- Pure, independently-testable functions and their constants are named without a leading underscore, matching this codebase's convention in `point_tracker.py` (`prune_points`, `should_add_point`, `MIN_DISTANCE_TO_ADD`) and `mouse_controller.py` (`accelerate`, `clamp`). Only true instance-internal methods (event handlers on the widget class) keep the underscore.
- The floating button must never be click-through (unlike `click_feedback.py`'s pulse) — it has to receive drag and click events.
- No color/state reflection (paused/no-face/yielded), no edge-snapping, no drag/open animation, no resizing.
- Do not modify `virtual_keyboard.py`'s behavior, `engine.py`, `mouse_controller.py`, `gestures.py`, `hotkeys.py`, `single_instance.py`, or `point_tracker.py`.
- Run tests with `.venv\Scripts\python -m pytest tests/ -v` from the repo root. The suite must end with **0 skipped**.
- `tests/conftest.py` provides a session-scoped `root` fixture and a function-scoped `container` fixture (a `CTkFrame` parented to `root`). Never construct another Tk root.

---

### Task 1: `KeyboardButtonConfig` — position persistence in `config.py`

**Files:**
- Modify: `src/facemesh_mouse/modules/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `KeyboardButtonConfig(x: float | None = None, y: float | None = None)`; `AppConfig.keyboard_button: KeyboardButtonConfig`; `load_config`/`save_config` read and write it under the `"keyboard_button"` JSON key.
- Consumes: nothing from other tasks.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_config.py`:

```python
def test_default_config_has_no_saved_keyboard_button_position():
    kb = config_mod.default_config().keyboard_button
    assert kb.x is None
    assert kb.y is None


def test_keyboard_button_position_round_trips(tmp_path):
    path = tmp_path / "config.json"
    original = config_mod.default_config()
    original.keyboard_button.x = 120.5
    original.keyboard_button.y = 640.0

    config_mod.save_config(path, original)
    loaded = config_mod.load_config(path)

    assert loaded.keyboard_button.x == 120.5
    assert loaded.keyboard_button.y == 640.0


def test_missing_keyboard_button_section_defaults_to_none(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"calibration": {}, "gestures": {}}))

    loaded = config_mod.load_config(path)

    assert loaded.keyboard_button.x is None
    assert loaded.keyboard_button.y is None


def test_non_numeric_keyboard_button_position_falls_back_to_none(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"keyboard_button": {"x": "nope", "y": None}}))

    loaded = config_mod.load_config(path)

    assert loaded.keyboard_button.x is None
    assert loaded.keyboard_button.y is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_config.py -v`
Expected: FAIL — `AttributeError: 'AppConfig' object has no attribute 'keyboard_button'`

- [ ] **Step 3: Add `KeyboardButtonConfig` and wire it into `AppConfig`**

In `src/facemesh_mouse/modules/config.py`, add this dataclass right after `CalibrationConfig` (after its `CALIBRATION_RANGES`/`_clamped` block, before `GestureConfig`):

```python
@dataclass
class KeyboardButtonConfig:
    """Screen position of the floating keyboard-launcher button, in pixels
    (top-left corner). `None` means "never dragged" -- the button falls
    back to its default bottom-right corner (see keyboard_button.py)."""

    x: float | None = None
    y: float | None = None


def _optional_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
```

Change the `AppConfig` dataclass:

```python
@dataclass
class AppConfig:
    calibration: CalibrationConfig = field(default_factory=CalibrationConfig)
    gestures: dict = field(default_factory=dict)
```

to:

```python
@dataclass
class AppConfig:
    calibration: CalibrationConfig = field(default_factory=CalibrationConfig)
    gestures: dict = field(default_factory=dict)
    keyboard_button: KeyboardButtonConfig = field(default_factory=KeyboardButtonConfig)
```

- [ ] **Step 4: Parse it in `load_config` and write it in `save_config`**

In `load_config`, right before the final `return AppConfig(calibration=calibration, gestures=gestures)`, add:

```python
    raw_kb = raw.get("keyboard_button", {})
    keyboard_button = KeyboardButtonConfig(
        x=_optional_float(raw_kb.get("x")),
        y=_optional_float(raw_kb.get("y")),
    )
```

and change the return statement to:

```python
    return AppConfig(calibration=calibration, gestures=gestures, keyboard_button=keyboard_button)
```

In `save_config`, change:

```python
    data = {
        "calibration": asdict(config.calibration),
        "gestures": {name: asdict(cfg) for name, cfg in config.gestures.items()},
    }
```

to:

```python
    data = {
        "calibration": asdict(config.calibration),
        "gestures": {name: asdict(cfg) for name, cfg in config.gestures.items()},
        "keyboard_button": asdict(config.keyboard_button),
    }
```

- [ ] **Step 5: Run the tests**

Run: `.venv\Scripts\python -m pytest tests/test_config.py -v`
Expected: PASS (all tests, including the 4 new ones)

- [ ] **Step 6: Run the full suite**

Run: `.venv\Scripts\python -m pytest tests/ -v`
Expected: PASS, 0 skipped

- [ ] **Step 7: Commit**

```bash
git add src/facemesh_mouse/modules/config.py tests/test_config.py
git commit -m "feat(config): persist the floating keyboard button's dragged position"
```

---

### Task 2: `keyboard_button.py` — the draggable circle

**Files:**
- Create: `src/facemesh_mouse/ui/keyboard_button.py`
- Test: `tests/test_keyboard_button.py` (new)

**Interfaces:**
- Consumes: `KeyboardButtonConfig`/`AppConfig` from Task 1; `config_mod.save_config`; `virtual_keyboard.open_virtual_keyboard` (unchanged, already exists at `src/facemesh_mouse/virtual_keyboard.py`); `clamp` from `src/facemesh_mouse/modules/mouse_controller.py`.
- Produces:
  - `CLICK_DRAG_THRESHOLD_PX: int = 5`, `SIZE: int = 60`, `MARGIN: int = 24`
  - `default_position(screen_w: float, screen_h: float) -> tuple[float, float]`
  - `resolve_position(saved_x: float | None, saved_y: float | None, screen_w: float, screen_h: float) -> tuple[float, float]`
  - `is_click(press: tuple[float, float], release: tuple[float, float]) -> bool`
  - `KeyboardButton(parent: tk.Misc, config: AppConfig, config_path: str | Path, screen_size: tuple[int, int])` with `.destroy() -> None`. Nothing else consumes this class until Task 3.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_keyboard_button.py`:

```python
import ctypes

from facemesh_mouse.modules.config import default_config
from facemesh_mouse.ui import keyboard_button
from facemesh_mouse.ui.click_feedback import GWL_EXSTYLE, WS_EX_TRANSPARENT


class _FakeEvent:
    def __init__(self, x_root, y_root):
        self.x_root = x_root
        self.y_root = y_root


def test_is_click_within_threshold_on_both_axes():
    assert keyboard_button.is_click((100, 100), (103, 102))


def test_is_click_exactly_at_the_threshold_is_a_click():
    t = keyboard_button.CLICK_DRAG_THRESHOLD_PX
    assert keyboard_button.is_click((100, 100), (100 + t, 100 - t))


def test_is_click_past_the_threshold_on_either_axis_is_a_drag():
    t = keyboard_button.CLICK_DRAG_THRESHOLD_PX
    assert not keyboard_button.is_click((100, 100), (100 + t + 1, 100))
    assert not keyboard_button.is_click((100, 100), (100, 100 + t + 1))


def test_default_position_is_inset_from_the_bottom_right_corner():
    x, y = keyboard_button.default_position(1000, 800)
    assert x == 1000 - keyboard_button.SIZE - keyboard_button.MARGIN
    assert y == 800 - keyboard_button.SIZE - keyboard_button.MARGIN


def test_resolve_position_uses_the_saved_spot_when_it_still_fits():
    assert keyboard_button.resolve_position(50.0, 60.0, 1000, 800) == (50.0, 60.0)


def test_resolve_position_falls_back_to_default_without_a_saved_spot():
    assert keyboard_button.resolve_position(
        None, None, 1000, 800
    ) == keyboard_button.default_position(1000, 800)


def test_resolve_position_falls_back_when_the_saved_spot_is_off_the_smaller_screen():
    # saved from a larger, previous screen -- doesn't fit the current one
    assert keyboard_button.resolve_position(
        1900.0, 1000.0, 1000, 800
    ) == keyboard_button.default_position(1000, 800)


def test_button_builds_a_topmost_non_click_through_window(container):
    button = keyboard_button.KeyboardButton(
        container, default_config(), "unused-config-path.json", (1000, 800)
    )

    window = button._window
    assert window.winfo_exists()
    assert window.attributes("-topmost")

    parent_hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
    styles = ctypes.windll.user32.GetWindowLongW(parent_hwnd, GWL_EXSTYLE)
    assert not (styles & WS_EX_TRANSPARENT)  # must receive clicks, unlike the click-feedback pulse

    button.destroy()


def test_a_small_release_opens_the_keyboard_without_saving(monkeypatch, container, tmp_path):
    opened = []
    monkeypatch.setattr(
        keyboard_button.virtual_keyboard, "open_virtual_keyboard", lambda: opened.append(True)
    )
    config_path = tmp_path / "config.json"
    config = default_config()
    button = keyboard_button.KeyboardButton(container, config, config_path, (1000, 800))

    button._on_press(_FakeEvent(500, 500))
    button._on_release(_FakeEvent(502, 501))  # 2px on each axis -- within threshold

    assert opened == [True]
    assert not config_path.exists()  # a click never writes to disk

    button.destroy()


def test_a_large_release_saves_the_new_position_without_opening(monkeypatch, container, tmp_path):
    opened = []
    monkeypatch.setattr(
        keyboard_button.virtual_keyboard, "open_virtual_keyboard", lambda: opened.append(True)
    )
    config_path = tmp_path / "config.json"
    config = default_config()
    button = keyboard_button.KeyboardButton(container, config, config_path, (1000, 800))

    button._on_press(_FakeEvent(500, 500))
    button._on_motion(_FakeEvent(560, 500))  # 60px -- moves the window
    button._on_release(_FakeEvent(560, 500))

    assert opened == []
    assert config_path.exists()
    assert config.keyboard_button.x is not None
    assert config.keyboard_button.y is not None

    button.destroy()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_keyboard_button.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'facemesh_mouse.ui.keyboard_button'`

- [ ] **Step 3: Create `keyboard_button.py`**

```python
"""A floating, draggable, always-on-top circle that opens Windows' virtual
keyboard on click.

Stays alive for the whole app process -- constructed once in main.py,
never shown/hidden with the config window or pause state. Uses the same
`-transparentcolor` trick as click_feedback.py to render a circle instead
of a rectangular window, but -- unlike the click-feedback pulse -- is never
click-through: it has to receive the drag and click events itself.
"""
from __future__ import annotations

import tkinter as tk
from pathlib import Path

from .. import virtual_keyboard
from ..modules import config as config_mod
from ..modules.config import AppConfig
from ..modules.mouse_controller import clamp

# A release within this many pixels of the press point, on both axes, is a
# click; past it on either axis, it's a drag. Matches the scale of
# DWELL_STILL_PX/YIELD_DETECT_PX elsewhere in this codebase.
CLICK_DRAG_THRESHOLD_PX = 5

SIZE = 60  # circle diameter, px
MARGIN = 24  # gap from the screen edge for the default corner position
ACCENT_COLOR = "#4da3ff"  # same blue as click_feedback's pulse ring
GLYPH = "⌨"  # "⌨"


def default_position(screen_w: float, screen_h: float) -> tuple[float, float]:
    """Top-left corner for the button's default bottom-right placement."""
    return screen_w - SIZE - MARGIN, screen_h - SIZE - MARGIN


def resolve_position(
    saved_x: float | None, saved_y: float | None, screen_w: float, screen_h: float
) -> tuple[float, float]:
    """Uses the saved position if there is one and it still fits the
    current screen; falls back to the default corner otherwise (e.g. no
    position was ever saved, or the resolution changed since it was)."""
    if saved_x is None or saved_y is None:
        return default_position(screen_w, screen_h)
    if not (0 <= saved_x <= screen_w - SIZE) or not (0 <= saved_y <= screen_h - SIZE):
        return default_position(screen_w, screen_h)
    return saved_x, saved_y


def is_click(press: tuple[float, float], release: tuple[float, float]) -> bool:
    """A release within CLICK_DRAG_THRESHOLD_PX of the press point, on both
    axes, counts as a click rather than a drag -- forgiving of the small
    wobble a shaky press-and-release can have."""
    return (
        abs(release[0] - press[0]) <= CLICK_DRAG_THRESHOLD_PX
        and abs(release[1] - press[1]) <= CLICK_DRAG_THRESHOLD_PX
    )


class KeyboardButton:
    def __init__(
        self,
        parent: tk.Misc,
        config: AppConfig,
        config_path: str | Path,
        screen_size: tuple[int, int],
    ) -> None:
        self._config = config
        self._config_path = config_path
        self._screen_w, self._screen_h = screen_size
        self._press_root: tuple[float, float] | None = None
        self._window_start: tuple[int, int] | None = None

        x, y = resolve_position(
            config.keyboard_button.x, config.keyboard_button.y, self._screen_w, self._screen_h
        )

        self._window = tk.Toplevel(parent)
        self._window.overrideredirect(True)
        self._window.attributes("-topmost", True)
        self._window.attributes("-transparentcolor", "black")
        self._window.configure(bg="black")
        self._window.geometry(f"{SIZE}x{SIZE}+{int(x)}+{int(y)}")

        canvas = tk.Canvas(self._window, width=SIZE, height=SIZE, bg="black", highlightthickness=0)
        canvas.pack()
        canvas.create_oval(2, 2, SIZE - 2, SIZE - 2, fill=ACCENT_COLOR, outline="")
        canvas.create_text(SIZE / 2, SIZE / 2, text=GLYPH, fill="white", font=("Segoe UI", 20))

        canvas.bind("<ButtonPress-1>", self._on_press)
        canvas.bind("<B1-Motion>", self._on_motion)
        canvas.bind("<ButtonRelease-1>", self._on_release)

    def _on_press(self, event) -> None:
        self._press_root = (event.x_root, event.y_root)
        self._window_start = (self._window.winfo_x(), self._window.winfo_y())

    def _on_motion(self, event) -> None:
        if self._press_root is None or self._window_start is None:
            return
        dx = event.x_root - self._press_root[0]
        dy = event.y_root - self._press_root[1]
        new_x = clamp(self._window_start[0] + dx, 0, self._screen_w - SIZE)
        new_y = clamp(self._window_start[1] + dy, 0, self._screen_h - SIZE)
        self._window.geometry(f"+{int(new_x)}+{int(new_y)}")
        self._window.update_idletasks()

    def _on_release(self, event) -> None:
        if self._press_root is None:
            return
        if is_click(self._press_root, (event.x_root, event.y_root)):
            virtual_keyboard.open_virtual_keyboard()
        else:
            self._config.keyboard_button.x = float(self._window.winfo_x())
            self._config.keyboard_button.y = float(self._window.winfo_y())
            config_mod.save_config(self._config_path, self._config)
        self._press_root = None
        self._window_start = None

    def destroy(self) -> None:
        self._window.destroy()
```

- [ ] **Step 4: Run the tests**

Run: `.venv\Scripts\python -m pytest tests/test_keyboard_button.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Run the full suite**

Run: `.venv\Scripts\python -m pytest tests/ -v`
Expected: PASS, 0 skipped

- [ ] **Step 6: Commit**

```bash
git add src/facemesh_mouse/ui/keyboard_button.py tests/test_keyboard_button.py
git commit -m "feat(keyboard): draggable floating button that opens the virtual keyboard"
```

---

### Task 3: Wire it in, remove the old entry points

**Files:**
- Modify: `src/facemesh_mouse/main.py`
- Modify: `src/facemesh_mouse/ui/tray.py`
- Modify: `src/facemesh_mouse/ui/config_gui.py`
- Modify: `src/facemesh_mouse/virtual_keyboard.py` (docstring only)
- Modify: `README.md`

This task is atomic: `TrayIcon.__init__` loses a parameter, so `tray.py` and its one call site in `main.py` must change together or the app fails to start. The `config_gui.py` change in this same task also fixes a real bug the previous entry points had (see Step 3).

**Interfaces:**
- Consumes: `KeyboardButton` from Task 2.
- Produces: `TrayIcon.__init__(self, on_toggle_pause, on_open_config, on_quit)` — back to 3 parameters, `on_open_keyboard` removed.

No automated test: `tray.py`, `config_gui.py`, and `main.py` have no existing test files covering this kind of wiring (consistent with the pattern already established for these three files).

- [ ] **Step 1: Revert `tray.py` to 3 menu items**

In `src/facemesh_mouse/ui/tray.py`, change the module docstring's first line from:

```python
"""System tray icon: Pause/Resume, Open Config, Open Keyboard, Quit.
```

to:

```python
"""System tray icon: Pause/Resume, Open Config, Quit.
```

Replace the `__init__` method:

```python
    def __init__(
        self,
        on_toggle_pause: Callable[[], bool],
        on_open_config: Callable[[], None],
        on_open_keyboard: Callable[[], None],
        on_quit: Callable[[], None],
    ) -> None:
        self._on_toggle_pause = on_toggle_pause
        self._on_open_config = on_open_config
        self._on_open_keyboard = on_open_keyboard
        self._on_quit = on_quit
        self._paused = False
        self._no_face = False
        self._yielded = False
        self._icon = pystray.Icon(
            "facemesh_mouse",
            _ICON_RUNNING,
            "FaceMesh Mouse",
            menu=pystray.Menu(
                pystray.MenuItem(self._pause_label, self._toggle_pause),
                pystray.MenuItem("Reabrir Config", self._open_config, default=True),
                pystray.MenuItem("Abrir Teclado", self._open_keyboard),
                pystray.MenuItem("Sair", self._quit),
            ),
        )
```

with:

```python
    def __init__(
        self,
        on_toggle_pause: Callable[[], bool],
        on_open_config: Callable[[], None],
        on_quit: Callable[[], None],
    ) -> None:
        self._on_toggle_pause = on_toggle_pause
        self._on_open_config = on_open_config
        self._on_quit = on_quit
        self._paused = False
        self._no_face = False
        self._yielded = False
        self._icon = pystray.Icon(
            "facemesh_mouse",
            _ICON_RUNNING,
            "FaceMesh Mouse",
            menu=pystray.Menu(
                pystray.MenuItem(self._pause_label, self._toggle_pause),
                pystray.MenuItem("Reabrir Config", self._open_config, default=True),
                pystray.MenuItem("Sair", self._quit),
            ),
        )
```

Remove the `_open_keyboard` handler entirely:

```python
    def _open_keyboard(self, _icon=None, _item=None) -> None:
        self._on_open_keyboard()

```

(delete this whole method, including the blank line after it, so `_open_config` is immediately followed by `_quit`).

- [ ] **Step 2: Remove the "Abrir Teclado" button and its help text from `config_gui.py`, and fix a stale-save bug this feature exposed**

First, the bug: `ConfigWindow.__init__` deep-copies the `AppConfig` it's given into `self._config`, and `_start_and_hide` (bound to both the "Iniciar" button and the window's close box) later saves that `self._config` back to `config.json` — unconditionally, every single time the window closes, for the entire life of the running app, since `ConfigWindow` is constructed once and reused. `KeyboardButton` (Task 2) mutates the position directly on the *original*, non-copied `AppConfig` object that `main.py` holds. Without a fix, dragging the button and then simply opening and closing the config window once (e.g. to check gesture mappings) would silently overwrite the freshly-dragged position back to whatever `ConfigWindow`'s stale deep copy had at construction time. `keyboard_button` was never part of what the config-window panels read or edit, so there is no reason for `ConfigWindow`'s own copy of it to ever be treated as authoritative — the fix keeps `ConfigWindow` pointed at the live object for this one field, read fresh at save time.

In `src/facemesh_mouse/ui/config_gui.py`, remove the now-unused import:

```python
from .. import virtual_keyboard
```

(delete this line entirely from the import block).

In `ConfigWindow.__init__`, change:

```python
        self._config = copy.deepcopy(config)
        self._config_path = config_path
```

to:

```python
        self._config = copy.deepcopy(config)
        # Not part of the deep copy: no panel in this window reads or edits
        # the keyboard button's position, so there's nothing to buffer --
        # `_start_and_hide` reads it fresh from here at save time, so a
        # drag that happened after this window was built is never lost.
        self._live_config = config
        self._config_path = config_path
```

In `_start_and_hide`, change:

```python
    def _start_and_hide(self) -> None:
        self._calibration.apply_to_config()
        self._gestures.apply_to_config()
        config_mod.save_config(self._config_path, self._config)
        self._on_start(self._config)
        self._root.withdraw()
```

to:

```python
    def _start_and_hide(self) -> None:
        self._calibration.apply_to_config()
        self._gestures.apply_to_config()
        self._config.keyboard_button = self._live_config.keyboard_button
        config_mod.save_config(self._config_path, self._config)
        self._on_start(self._config)
        self._root.withdraw()
```

Now the button removal. Change:

```python
        ctk.CTkButton(
            tabs.tab("Ajuda"),
            text="Abrir Teclado",
            height=44,
            font=("Segoe UI", 14, "bold"),
            command=virtual_keyboard.open_virtual_keyboard,
        ).pack(fill="x", padx=6, pady=(6, 0))

        ctk.CTkLabel(
            tabs.tab("Ajuda"),
            text=_HELP_TEXT,
            justify="left",
            wraplength=390,
            anchor="nw",
        ).pack(fill="both", expand=True, padx=6, pady=6)
```

to:

```python
        ctk.CTkLabel(
            tabs.tab("Ajuda"),
            text=_HELP_TEXT,
            justify="left",
            wraplength=390,
            anchor="nw",
        ).pack(fill="both", expand=True, padx=6, pady=6)
```

And in `_HELP_TEXT`, change:

```python
    "3. Iniciar -- a janela some e o cursor passa a seguir a cabeça.\n\n"
    "O botão \"Abrir Teclado\" acima abre o teclado virtual do Windows -- útil "
    "aqui com o mouse físico ou a ajuda de outra pessoa, já que esta janela "
    "pausa o controle pela cabeça enquanto está aberta; para abrir o teclado "
    "pelo cursor controlado pela cabeça, use o mesmo item no menu da "
    "bandeja.\n\n"
    "Atalhos\n\n"
```

to:

```python
    "3. Iniciar -- a janela some e o cursor passa a seguir a cabeça.\n\n"
    "Atalhos\n\n"
```

- [ ] **Step 3: Wire `KeyboardButton` into `main.py`, remove `on_open_keyboard`**

In `src/facemesh_mouse/main.py`, add an import (alphabetically between the `config_gui` and `tray` imports):

```python
from .ui.config_gui import ConfigWindow, create_root
from .ui.keyboard_button import KeyboardButton
from .ui.tray import TrayIcon
```

Change:

```python
    root = create_root()
    screen_size = (root.winfo_screenwidth(), root.winfo_screenheight())
    engine.start(screen_size)

    config_window = ConfigWindow(
```

to:

```python
    root = create_root()
    screen_size = (root.winfo_screenwidth(), root.winfo_screenheight())
    engine.start(screen_size)

    keyboard_button = KeyboardButton(root, app_config, CONFIG_PATH, screen_size)

    config_window = ConfigWindow(
```

Change the `TrayIcon(...)` construction:

```python
    tray = TrayIcon(
        on_toggle_pause=toggle_pause,
        on_open_config=open_config,
        on_open_keyboard=virtual_keyboard.open_virtual_keyboard,
        on_quit=quit_app,
    )
```

to:

```python
    tray = TrayIcon(
        on_toggle_pause=toggle_pause,
        on_open_config=open_config,
        on_quit=quit_app,
    )
```

`from . import virtual_keyboard` at the top of `main.py` becomes unused after this change — remove that import line too.

- [ ] **Step 4: Update `virtual_keyboard.py`'s docstring**

Change:

```python
"""Launches Windows' built-in on-screen keyboard.

The app doesn't build its own on-screen keyboard -- Windows already ships
one that's accessible from any focused app. This module only makes it
reachable through the same head-tracked cursor the rest of the app uses
(tray menu, config window button).
"""
```

to:

```python
"""Launches Windows' built-in on-screen keyboard.

The app doesn't build its own on-screen keyboard -- Windows already ships
one that's accessible from any focused app. This module only makes it
reachable through the same head-tracked cursor the rest of the app uses --
called from the floating keyboard button (see ui/keyboard_button.py).
"""
```

- [ ] **Step 5: Update `README.md`**

Change the intro paragraph's last two sentences (currently):

```
rodando em segundo plano (sem janela visível), com ícone na bandeja e
atalhos globais. O app não tem teclado próprio, mas o teclado virtual do
Windows pode ser aberto pelo ícone da bandeja (o caminho acessível pelo
cursor controlado pela cabeça) ou por um botão na aba Ajuda da
configuração, pra quem também precisar digitar.
```

to:

```
rodando em segundo plano (sem janela visível), com ícone na bandeja e
atalhos globais. O app não tem teclado próprio, mas o teclado virtual do
Windows pode ser aberto por um círculo flutuante e arrastável que fica
sempre visível na tela (canto inferior direito por padrão), pra quem
também precisar digitar.
```

Change the spec-links paragraph's last entry (currently):

```
[docs/superpowers/specs/2026-08-13-virtual-keyboard-launcher-design.md](docs/superpowers/specs/2026-08-13-virtual-keyboard-launcher-design.md)
(abrir o teclado virtual do Windows pelo ícone da bandeja ou pela aba Ajuda)
para o design completo.
```

to:

```
[docs/superpowers/specs/2026-08-13-virtual-keyboard-launcher-design.md](docs/superpowers/specs/2026-08-13-virtual-keyboard-launcher-design.md)
(lançar o teclado virtual do Windows) e
[docs/superpowers/specs/2026-08-13-floating-keyboard-button-design.md](docs/superpowers/specs/2026-08-13-floating-keyboard-button-design.md)
(círculo flutuante e arrastável como único ponto de entrada, no lugar do
item na bandeja e do botão na aba Ajuda)
para o design completo.
```

Change the Ajuda tab's bullet (currently):

```
- **Ajuda**: o mesmo resumo de uso e atalhos, dentro da própria janela, com
  um botão "Abrir Teclado" para quem estiver usando mouse físico ou
  trackpad, ou for ajudado por outra pessoa (essa janela pausa o controle
  pela cabeça enquanto está aberta -- veja abaixo o caminho acessível pela
  cabeça, pelo ícone da bandeja).
```

to:

```
- **Ajuda**: o mesmo resumo de uso e atalhos, dentro da própria janela.
```

Change the tray-icon paragraph (currently):

```
Ícone na bandeja: Pausar/Retomar, Reabrir Config, Abrir Teclado, Sair.
"Abrir Teclado" é o caminho acessível pelo cursor controlado pela cabeça
pra abrir o teclado virtual do Windows, já que abrir a config pausa esse
controle. Clique com o botão esquerdo no ícone também reabre a config
direto; botão direito mostra o menu completo.
```

to:

```
Ícone na bandeja: Pausar/Retomar, Reabrir Config, Sair. Clique com o botão
esquerdo no ícone também reabre a config direto; botão direito mostra o
menu completo.

O teclado virtual do Windows é aberto por um círculo azul flutuante, sempre
visível por cima de tudo, no canto inferior direito por padrão -- inclusive
enquanto a config está aberta, já que abrir a config pausa o controle pela
cabeça. Clique nele (funciona pelo cursor controlado pela cabeça também)
para abrir o teclado; com o mouse físico ou trackpad, arraste-o para
qualquer lugar da tela -- a posição escolhida fica salva entre sessões.
```

- [ ] **Step 6: Run the full suite**

Run: `.venv\Scripts\python -m pytest tests/ -v`
Expected: PASS, 0 skipped

- [ ] **Step 7: Verify the app compiles**

Run: `.venv\Scripts\python -m py_compile src/facemesh_mouse/*.py src/facemesh_mouse/**/*.py`
Expected: clean, no output

- [ ] **Step 8: Commit**

```bash
git add src/facemesh_mouse/main.py src/facemesh_mouse/ui/tray.py src/facemesh_mouse/ui/config_gui.py src/facemesh_mouse/virtual_keyboard.py README.md
git commit -m "feat(keyboard): replace tray/config entry points with the floating button"
```

---

## Manual Verification (after implementation)

Not covered by the automated suite — run the app and check by hand:

- On startup, the blue circle appears in the bottom-right corner, on top of everything.
- Click it — Windows' on-screen keyboard opens.
- Drag it (physical mouse, hold and move) to another corner, release — it stays there, and clicking it still opens the keyboard.
- Quit and relaunch the app — the circle reappears where it was last dragged.
- Drag the circle, then open the config window (double-click the tray icon) and close it again (either the "Iniciar" button or the window's X) — the circle's position is unchanged (this is the stale-save bug fixed in Task 3, Step 2).
- With head-tracked cursor control active, aim a mapped gesture's click at the circle — it opens the keyboard the same as a physical click.
- Confirm the tray menu is back to 3 items (Pausar/Retomar, Reabrir Config, Sair) and the config window's "Ajuda" tab no longer has an "Abrir Teclado" button.

## Self-Review Notes

- **Spec coverage:** `KeyboardButtonConfig` + persistence → Task 1; circle rendering, click-vs-drag threshold, drag clamping, default/resolve position → Task 2; removal of the tray item and config button, `main.py` wiring, README → Task 3. The stale-save bug fix in Task 3 wasn't explicit in the spec's text but is required for the spec's own persistence requirement ("written straight to config.json... independent of whether the config window is even open") to actually hold once the config window has been opened even once.
- **Placeholder scan:** none — every step has literal code or an exact command.
- **Type/name consistency:** `KeyboardButtonConfig`/`AppConfig.keyboard_button` match between Task 1's definition and Task 2's `KeyboardButton.__init__`/tests. `default_position`, `resolve_position`, `is_click`, `CLICK_DRAG_THRESHOLD_PX`, `SIZE`, `MARGIN` match between Task 2's implementation and its own tests. `KeyboardButton(parent, config, config_path, screen_size)`'s signature matches between Task 2's class and Task 3's `main.py` call site.
- **Runnability:** Task 1 only adds a field with a default, so every existing `AppConfig(...)` construction (tests, `main.py`, `config_gui.py`) keeps working unchanged. Task 2 adds an unimported module. Task 3 changes `TrayIcon.__init__`'s signature and its one call site together, removes the config-window button and its import together, and fixes the stale-copy bug in the same file it lives in.
