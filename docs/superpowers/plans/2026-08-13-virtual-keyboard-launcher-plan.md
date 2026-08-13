# Virtual Keyboard Launcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a way to open Windows' built-in on-screen keyboard (`osk.exe`) from the tray menu and from the config window, so users who can't reliably use a physical keyboard have a text-input path reachable through the app's existing head-tracked cursor.

**Architecture:** A new `virtual_keyboard.py` module owns one function, `open_virtual_keyboard()`, that launches `osk.exe` via `subprocess.Popen` and swallows any failure. `tray.py` gets a third menu item calling it through an injected callback (mirroring the existing `on_open_config` pattern); `config_gui.py` gets a button on the "Ajuda" tab calling it directly. Neither entry point tracks whether the keyboard is already open — Windows' OSK is closable through its own window, clickable by the same cursor.

**Tech Stack:** Python 3.11, stdlib `subprocess`, CustomTkinter, pystray, pytest.

## Global Constraints

- Every new module keeps `from __future__ import annotations` as its first import.
- UI strings stay in Portuguese with correct diacritics.
- No `shell=True` on the `subprocess.Popen` call.
- No process tracking, toggle, or close path for `osk.exe` — closing it is via its own window.
- No elevation/UAC handling.
- Do not modify `engine.py`, `mouse_controller.py`, `gestures.py`, `hotkeys.py`, `single_instance.py`, or `point_tracker.py`.
- Run tests with `.venv\Scripts\python -m pytest tests/ -v` from the repo root. The suite must end with **0 skipped**.
- `tests/test_panels.py` has a module-scoped `root` fixture and a function-scoped `container` fixture. Never construct another Tk root — more than one per process fails intermittently under pytest's output capture.

---

### Task 1: `virtual_keyboard.py` — launch `osk.exe`

**Files:**
- Create: `src/facemesh_mouse/virtual_keyboard.py`
- Test: `tests/test_virtual_keyboard.py` (new)

**Interfaces:**
- Produces: `open_virtual_keyboard() -> None`.
- Consumes: nothing from other tasks. Nothing imports this file until Task 2.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_virtual_keyboard.py`:

```python
from unittest.mock import MagicMock

from facemesh_mouse import virtual_keyboard


def test_open_virtual_keyboard_launches_osk(monkeypatch):
    popen_mock = MagicMock()
    monkeypatch.setattr(virtual_keyboard.subprocess, "Popen", popen_mock)

    virtual_keyboard.open_virtual_keyboard()

    popen_mock.assert_called_once_with(["osk.exe"])


def test_open_virtual_keyboard_survives_a_launch_failure(monkeypatch, capsys):
    """A missing/blocked osk.exe must never crash the caller -- the tray
    thread or the Tk event loop, depending on which entry point calls it."""

    def _boom(*_args, **_kwargs):
        raise FileNotFoundError("simulated osk.exe launch failure")

    monkeypatch.setattr(virtual_keyboard.subprocess, "Popen", _boom)

    virtual_keyboard.open_virtual_keyboard()  # must not raise

    assert "osk.exe" in capsys.readouterr().out
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_virtual_keyboard.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'facemesh_mouse.virtual_keyboard'`

- [ ] **Step 3: Create `virtual_keyboard.py`**

```python
"""Launches Windows' built-in on-screen keyboard.

The app doesn't build its own on-screen keyboard -- Windows already ships
one that's accessible from any focused app. This module only makes it
reachable through the same head-tracked cursor the rest of the app uses
(tray menu, config window button).
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
```

- [ ] **Step 4: Run the tests**

Run: `.venv\Scripts\python -m pytest tests/test_virtual_keyboard.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Run the full suite**

Run: `.venv\Scripts\python -m pytest tests/ -v`
Expected: PASS, 0 skipped

- [ ] **Step 6: Commit**

```bash
git add src/facemesh_mouse/virtual_keyboard.py tests/test_virtual_keyboard.py
git commit -m "feat(keyboard): launch osk.exe via virtual_keyboard.open_virtual_keyboard"
```

---

### Task 2: Tray menu item

**Files:**
- Modify: `src/facemesh_mouse/tray.py`
- Modify: `src/facemesh_mouse/main.py`

This task is atomic: `TrayIcon.__init__` gains a required callback parameter, so `tray.py` and its one call site in `main.py` must change together or the app fails to start.

**Interfaces:**
- Consumes: `virtual_keyboard.open_virtual_keyboard`, from Task 1.
- Produces: `TrayIcon.__init__(self, on_toggle_pause, on_open_config, on_open_keyboard, on_quit)` — **signature changed**, `on_open_keyboard` inserted before `on_quit`.

No automated test: `tray.py` has no existing test file (`pystray` drives a real system tray icon, not testable under pytest) — this task follows that existing pattern.

- [ ] **Step 1: Add the callback parameter and menu item to `tray.py`**

In `src/facemesh_mouse/tray.py`, replace the `__init__` method:

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

with:

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

Then add a handler method next to `_open_config`:

```python
    def _open_config(self, _icon=None, _item=None) -> None:
        self._on_open_config()

    def _open_keyboard(self, _icon=None, _item=None) -> None:
        self._on_open_keyboard()
```

- [ ] **Step 2: Wire the callback in `main.py`**

In `src/facemesh_mouse/main.py`, add the import alongside the other same-package imports:

```python
from . import virtual_keyboard
```

Then update the `TrayIcon` construction:

```python
    tray = TrayIcon(
        on_toggle_pause=toggle_pause,
        on_open_config=open_config,
        on_quit=quit_app,
    )
```

becomes:

```python
    tray = TrayIcon(
        on_toggle_pause=toggle_pause,
        on_open_config=open_config,
        on_open_keyboard=virtual_keyboard.open_virtual_keyboard,
        on_quit=quit_app,
    )
```

- [ ] **Step 3: Run the full suite**

Run: `.venv\Scripts\python -m pytest tests/ -v`
Expected: PASS, 0 skipped

- [ ] **Step 4: Verify the app compiles**

Run: `.venv\Scripts\python -m py_compile src/facemesh_mouse/*.py`
Expected: clean, no output

- [ ] **Step 5: Commit**

```bash
git add src/facemesh_mouse/tray.py src/facemesh_mouse/main.py
git commit -m "feat(tray): add \"Abrir Teclado\" menu item"
```

---

### Task 3: Config window button

**Files:**
- Modify: `src/facemesh_mouse/config_gui.py`

**Interfaces:**
- Consumes: `virtual_keyboard.open_virtual_keyboard`, from Task 1.
- Produces: nothing consumed by later tasks — this is the last task.

No automated test: `config_gui.py`'s shell (as opposed to the panels it hosts, which do have tests via `test_panels.py`) has no existing test file — this task follows that existing pattern.

- [ ] **Step 1: Import the module**

In `src/facemesh_mouse/config_gui.py`, add to the same-package imports:

```python
from . import virtual_keyboard
```

- [ ] **Step 2: Add the button to the "Ajuda" tab**

In `_build_widgets`, the "Ajuda" tab currently only gets the help-text label:

```python
        ctk.CTkLabel(
            tabs.tab("Ajuda"),
            text=_HELP_TEXT,
            justify="left",
            wraplength=390,
            anchor="nw",
        ).pack(fill="both", expand=True, padx=6, pady=6)
```

Add a button above it, so the block becomes:

```python
        ctk.CTkButton(
            tabs.tab("Ajuda"),
            text="Abrir Teclado",
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

- [ ] **Step 3: Run the full suite**

Run: `.venv\Scripts\python -m pytest tests/ -v`
Expected: PASS, 0 skipped

- [ ] **Step 4: Verify the app compiles**

Run: `.venv\Scripts\python -m py_compile src/facemesh_mouse/*.py`
Expected: clean, no output

- [ ] **Step 5: Commit**

```bash
git add src/facemesh_mouse/config_gui.py
git commit -m "feat(gui): add \"Abrir Teclado\" button to the Ajuda tab"
```

---

## Manual Verification (after implementation)

Not covered by the automated suite — run the app and check by hand:

- Right-click the tray icon, click "Abrir Teclado" — the Windows on-screen keyboard opens.
- Open the config window (double-click the tray icon), go to the "Ajuda" tab, click "Abrir Teclado" — the on-screen keyboard opens.
- With head-tracked cursor control active, click a key on the on-screen keyboard, then click its own close button, using the head-tracked cursor for both.

## Self-Review Notes

- **Spec coverage:** `open_virtual_keyboard()` wrapping `subprocess.Popen(["osk.exe"])` with a swallowed failure → Task 1; tray menu item via injected callback → Task 2; config-window button on "Ajuda" → Task 3; no process tracking/toggle/close path, no elevation handling → absent from every task, matching the spec's Out of Scope.
- **Placeholder scan:** none found — every step has literal code or an exact command.
- **Type/name consistency:** `open_virtual_keyboard` matches across Task 1's definition, Task 2's `main.py` wiring, and Task 3's button `command`. `TrayIcon.__init__`'s new `on_open_keyboard` parameter name matches the keyword used in `main.py`'s call site.
- **Runnability:** Task 1 adds an unimported module (safe on its own). Task 2 changes `TrayIcon.__init__`'s signature and its one call site together, so the app stays runnable after the commit. Task 3 is additive only.
