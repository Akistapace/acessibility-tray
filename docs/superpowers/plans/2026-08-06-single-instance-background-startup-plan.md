# Single Instance & Background Startup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A second launch of the app signals the already-running instance to open its config window and exits immediately instead of starting a competing process; a launch with a saved `config.json` goes straight to background tracking without showing the wizard; double-clicking the tray icon opens config.

**Architecture:** A new `single_instance` module binds a fixed loopback TCP port as both the single-instance exclusivity check and the IPC signal channel (a second launch's failed bind becomes a connect-and-signal instead). `main.py` wires this in before opening the camera, and adds a `config.json`-existence check to skip the wizard on repeat launches. `tray.py` gets one `default=True` flag so double-clicking the icon reuses the existing "Reabrir Config" action.

**Tech Stack:** Python 3.11, stdlib `socket`/`threading` (no new dependency), pytest.

## Global Constraints

- Windows-only single-instance mechanism using stdlib `socket` only — no new pip dependency.
- Loopback-only bind (`127.0.0.1`), fixed port `51737` as the production default; `acquire_or_signal` must accept `host`/`port` overrides so tests can use a free ephemeral port instead of the real fixed port.
- No `SO_REUSEADDR` on the listening socket — on Windows this can permit binding a port that's already actively listened on, which would defeat the exclusivity check this mechanism depends on.
- The single-instance guard runs before `engine.open_camera()` in `main()` — a second launch must exit without touching the webcam, tray, or hotkeys.
- `config.json` existence (`Path(CONFIG_PATH).exists()`) is the sole signal for "already configured" — no deeper validation of its contents.
- `tray.py`'s single-left-click-opens-menu behavior must be unaffected — `default=True` only adds a double-click shortcut on top of it.
- Run tests with `.venv\Scripts\python -m pytest tests/ -v` (repo root). `pyproject.toml` sets `pythonpath = ["src"]`.
- Every module keeps `from __future__ import annotations` as its first import, matching the existing files.

---

### Task 1: `single_instance` module — bind-or-signal over a loopback socket

**Files:**
- Create: `src/facemesh_mouse/single_instance.py`
- Test: `tests/test_single_instance.py`

**Interfaces:**
- Produces: `HOST: str = "127.0.0.1"`, `PORT: int = 51737`,
  `acquire_or_signal(on_signal: Callable[[], None], host: str = HOST, port: int = PORT) -> socket.socket | None`.
  Returns the bound, listening `socket.socket` if this call became the
  primary instance (caller must keep a reference alive for the process
  lifetime — closing it releases the port and stops the accept loop).
  Returns `None` if another instance already holds the port (this call
  connected to it and signaled it, then closed its own client connection).
  `on_signal` is invoked, on a background daemon thread, once per
  connection accepted by the primary instance's listener — it fires
  repeatedly, once per second-launch attempt, not just once.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_single_instance.py`:

```python
import socket
import threading
import time

from facemesh_mouse import single_instance


def _free_port() -> int:
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return port


def test_acquire_returns_socket_and_invokes_callback_on_connect():
    port = _free_port()
    signaled = threading.Event()

    primary = single_instance.acquire_or_signal(on_signal=signaled.set, port=port)
    try:
        assert primary is not None

        with socket.create_connection(("127.0.0.1", port), timeout=1.0):
            pass

        assert signaled.wait(timeout=1.0)
    finally:
        primary.close()


def test_acquire_signals_existing_instance_and_returns_none_when_port_taken():
    port = _free_port()
    signaled = threading.Event()
    primary = single_instance.acquire_or_signal(on_signal=signaled.set, port=port)
    try:
        assert primary is not None

        result = single_instance.acquire_or_signal(on_signal=lambda: None, port=port)

        assert result is None
        assert signaled.wait(timeout=1.0)
    finally:
        primary.close()


def test_listener_keeps_accepting_after_first_signal():
    port = _free_port()
    call_count = {"n": 0}
    lock = threading.Lock()

    def on_signal() -> None:
        with lock:
            call_count["n"] += 1

    primary = single_instance.acquire_or_signal(on_signal=on_signal, port=port)
    try:
        assert primary is not None

        for _ in range(3):
            with socket.create_connection(("127.0.0.1", port), timeout=1.0):
                pass
            time.sleep(0.05)

        assert call_count["n"] == 3
    finally:
        primary.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_single_instance.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'facemesh_mouse.single_instance'`

- [ ] **Step 3: Implement `single_instance.py`**

Create `src/facemesh_mouse/single_instance.py`:

```python
"""Single-instance guard: binds a fixed localhost TCP port to detect (and
signal) an already-running instance. The bind is both the exclusivity
check and the IPC channel -- no separate mutex or lock file."""
from __future__ import annotations

import socket
import threading
from typing import Callable

HOST = "127.0.0.1"
PORT = 51737


def acquire_or_signal(
    on_signal: Callable[[], None],
    host: str = HOST,
    port: int = PORT,
) -> socket.socket | None:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.bind((host, port))
    except OSError:
        listener.close()
        _signal_existing_instance(host, port)
        return None

    listener.listen(1)
    thread = threading.Thread(target=_listen_loop, args=(listener, on_signal), daemon=True)
    thread.start()
    return listener


def _listen_loop(listener: socket.socket, on_signal: Callable[[], None]) -> None:
    while True:
        try:
            conn, _addr = listener.accept()
        except OSError:
            return
        conn.close()
        on_signal()


def _signal_existing_instance(host: str, port: int) -> None:
    try:
        with socket.create_connection((host, port), timeout=1.0):
            pass
    except OSError:
        pass
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/test_single_instance.py -v`
Expected: PASS (all 3 tests)

- [ ] **Step 5: Run the full suite**

Run: `.venv\Scripts\python -m pytest tests/ -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/facemesh_mouse/single_instance.py tests/test_single_instance.py
git commit -m "feat(single-instance): bind-or-signal loopback socket guard"
```

---

### Task 2: Wire the single-instance guard into `main.py`

**Files:**
- Modify: `src/facemesh_mouse/main.py`

**Interfaces:**
- Consumes: `single_instance.acquire_or_signal(on_signal, host=..., port=...) -> socket.socket | None` (Task 1), called with no `host`/`port` override so it uses the production defaults.
- Produces: no new interface — `main()`'s externally-visible behavior (what it does when run) changes, but there's nothing else in the codebase that calls into `main.py`.

No automated test: `main()` wires together real camera/Tk/tray/hotkeys and isn't unit-tested today (see the v1 spec's testing section — this module is manual-checklist only). Verification here is a `py_compile` syntax check; the manual checklist (Task 4 of this plan) covers the real behavior.

- [ ] **Step 1: Add the guard**

In `src/facemesh_mouse/main.py`, add the import:

```python
from . import config as config_mod
from . import single_instance
from .config_gui import ConfigWindow
```

(inserted alphabetically between the existing `from . import config as config_mod` and `from .config_gui import ConfigWindow` lines)

Replace:

```python
def main() -> None:
    app_config = config_mod.load_config(CONFIG_PATH)
    engine = Engine(app_config)
```

with:

```python
def main() -> None:
    _config_window_opener = None

    def _on_singleton_signal() -> None:
        if _config_window_opener is not None:
            _config_window_opener()

    singleton_socket = single_instance.acquire_or_signal(on_signal=_on_singleton_signal)
    if singleton_socket is None:
        sys.exit(0)

    app_config = config_mod.load_config(CONFIG_PATH)
    engine = Engine(app_config)
```

`_config_window_opener` starts `None` and is a plain local variable in
`main()`'s scope — `_on_singleton_signal` (a nested function) reads it via
closure each time it's invoked, so it doesn't matter that it's still
`None` at this point in `main()`'s execution; by the time any real signal
can arrive (another process would need to start, import Python, and
connect — much slower than the rest of `main()` finishing its setup),
`_config_window_opener` will already hold the real function assigned in
Step 2 below.

- [ ] **Step 2: Point the opener reference at the real `open_config`**

Replace:

```python
    def open_config() -> None:
        engine.control_enabled.clear()
        root.after(0, config_window.show)

    def quit_app() -> None:
```

with:

```python
    def open_config() -> None:
        engine.control_enabled.clear()
        root.after(0, config_window.show)

    _config_window_opener = open_config

    def quit_app() -> None:
```

- [ ] **Step 3: Syntax-check and run the full suite**

Run: `.venv\Scripts\python -m py_compile src/facemesh_mouse/main.py`
Expected: no output, exit code 0

Run: `.venv\Scripts\python -m pytest tests/ -v`
Expected: PASS (unaffected by this change, confirms nothing else broke)

- [ ] **Step 4: Commit**

```bash
git add src/facemesh_mouse/main.py
git commit -m "feat(main): exit and signal the running instance on a second launch"
```

---

### Task 3: Skip the config wizard when `config.json` already exists

**Files:**
- Modify: `src/facemesh_mouse/main.py`

**Interfaces:**
- Consumes: `Engine.control_enabled: threading.Event` (existing, unchanged), `ConfigWindow` (existing, unchanged — this task never touches `config_gui.py`).
- Produces: no new interface.

No automated test, same reasoning as Task 2 — `py_compile` plus the manual checklist.

- [ ] **Step 1: Add the `Path` import**

In `src/facemesh_mouse/main.py`, add near the top with the other stdlib imports:

```python
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox
```

(`from pathlib import Path` inserted alphabetically between `sys` and `tkinter`)

- [ ] **Step 2: Add the skip-wizard branch**

Replace:

```python
    config_window = ConfigWindow(
        root,
        engine,
        app_config,
        CONFIG_PATH,
        on_start=_make_on_start(engine),
    )

    def toggle_pause() -> bool:
```

with:

```python
    config_window = ConfigWindow(
        root,
        engine,
        app_config,
        CONFIG_PATH,
        on_start=_make_on_start(engine),
    )

    if Path(CONFIG_PATH).exists():
        engine.control_enabled.set()
        root.withdraw()

    def toggle_pause() -> bool:
```

No call to `engine.update_config(app_config)` is needed here — `engine`
was already constructed with `app_config` at the top of `main()`, and
nothing has modified it on this code path (the wizard never ran).

- [ ] **Step 3: Syntax-check and run the full suite**

Run: `.venv\Scripts\python -m py_compile src/facemesh_mouse/main.py`
Expected: no output, exit code 0

Run: `.venv\Scripts\python -m pytest tests/ -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/facemesh_mouse/main.py
git commit -m "feat(main): skip config wizard on launch when config.json already exists"
```

---

### Task 4: Tray icon double-click opens config

**Files:**
- Modify: `src/facemesh_mouse/tray.py:38-42`

**Interfaces:**
- Consumes: nothing new.
- Produces: nothing new — purely a `pystray.MenuItem` flag change.

No automated test — `tray.py` is manual-checklist only (real system tray, not testable in pytest). Verification is `py_compile` plus the manual checklist below.

- [ ] **Step 1: Add `default=True`**

In `src/facemesh_mouse/tray.py`, replace:

```python
            menu=pystray.Menu(
                pystray.MenuItem(self._pause_label, self._toggle_pause),
                pystray.MenuItem("Reabrir Config", self._open_config),
                pystray.MenuItem("Sair", self._quit),
            ),
```

with:

```python
            menu=pystray.Menu(
                pystray.MenuItem(self._pause_label, self._toggle_pause),
                pystray.MenuItem("Reabrir Config", self._open_config, default=True),
                pystray.MenuItem("Sair", self._quit),
            ),
```

- [ ] **Step 2: Syntax-check and run the full suite**

Run: `.venv\Scripts\python -m py_compile src/facemesh_mouse/tray.py`
Expected: no output, exit code 0

Run: `.venv\Scripts\python -m pytest tests/ -v`
Expected: PASS

- [ ] **Step 3: Manual verification checklist**

With a real webcam, from a shell in the repo root:

1. Delete `config.json` if present. Run `.venv\Scripts\python run.py` — the
   config wizard window appears (first-run behavior, unchanged).
2. Complete calibration/gesture mapping and click "▶ Iniciar controle do
   mouse". Window hides, cursor follows head movement, tray icon appears.
3. **Without quitting**, run `.venv\Scripts\python run.py` again in a
   second terminal. The second process should exit almost immediately
   (check its exit code / that the shell prompt returns quickly) and the
   *first* process's config window should reappear on screen.
4. Close that config window again (via "Iniciar" or the X button). Quit
   the app entirely via the tray menu's "Sair".
5. Run `.venv\Scripts\python run.py` once more. Since `config.json` now
   exists from step 2, the wizard should NOT appear — the app should go
   straight to background tracking (check the tray icon appears with no
   window ever shown).
6. Double-click the tray icon. The config window should open (same result
   as using "Reabrir Config" from the menu or `Ctrl+Alt+O`).

- [ ] **Step 4: Commit**

```bash
git add src/facemesh_mouse/tray.py
git commit -m "feat(tray): double-click icon opens config window"
```

---

## Self-Review Notes

- **Spec coverage:** single-instance bind-or-signal mechanism → Task 1; wiring before camera open → Task 2; skip-wizard-on-existing-config → Task 3; tray double-click → Task 4; error handling (bind failure treated as "already running", failed signal connection ignored) → covered by Task 1's `except OSError` blocks matching the spec's error-handling section exactly; manual checklist additions from the spec → Task 4 Step 3.
- **Placeholder scan:** no TBD/TODO; every step has literal code or an exact command.
- **Type/name consistency checked:** `acquire_or_signal`'s signature matches between Task 1's definition and Task 2's call site (`on_signal=` keyword, no `host`/`port` override needed at the production call site since defaults match). `CONFIG_PATH` referenced in Task 3 matches the existing module-level constant already in `main.py`.
- **Out of scope, confirmed absent from all tasks:** passing structured data through the signal socket, cross-platform handling, deeper config-file validation beyond existence.
