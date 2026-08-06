# FaceMesh Mouse — Single Instance & Background Startup — Design Spec

**Date:** 2026-08-06
**Status:** Approved
**Builds on:** `2026-08-05-facemesh-mouse-design.md` (v1), `2026-08-05-usability-anchor-mode-design.md` (v2)

## Purpose

Two friction points remain in the app's launch flow:

1. Launching the app a second time (double-clicking the exe/shortcut again
   while it's already running in the background) starts a second, fully
   independent process — a second camera-capture thread competing for the
   same webcam, a second tray icon, a second hotkey listener registering
   the same global hotkeys.
2. Every launch shows the full config wizard, even when a previous run
   already saved a working calibration and gesture mapping to
   `config.json` — the user has to click through to "Iniciar" every time
   just to get back to background tracking.

This spec adds: single-instance enforcement (a second launch signals the
already-running instance instead of starting its own), skip-the-wizard
startup when a saved config already exists, and a tray-icon double-click
shortcut to reopen the config window.

## Approach: Single Instance via Loopback Socket

### Why a loopback TCP bind instead of a mutex or lock file

A Windows named mutex (via `ctypes`) is the traditional approach, but it
only answers "is another instance running" — reaching the user's actual
request (have the *existing* instance open its config window) still needs
a separate IPC channel. A lock file has the same gap, plus a stale-lock
risk if the process is killed without cleanup.

Binding a fixed TCP port on `127.0.0.1` solves both problems with one
mechanism and no new dependency (`socket` is stdlib): the bind itself is
the exclusivity check (the OS refuses a second bind to an in-use port,
and releases it automatically if the owning process dies or is killed —
no stale-lock cleanup to write), and the same socket doubles as the
signaling channel once a listener is attached to it.

### Mechanism

New module `src/facemesh_mouse/single_instance.py`:

```
HOST = "127.0.0.1"
PORT = 51737  # fixed, arbitrary, loopback-only

acquire_or_signal(on_signal: Callable[[], None]) -> socket.socket | None
```

- Tries to bind `(HOST, PORT)`.
  - **Success (primary instance):** starts a daemon thread that `accept()`s
    connections in a loop; each accepted connection is closed immediately
    after being accepted (no payload needed — the connection itself is the
    signal) and `on_signal()` is invoked. Returns the bound, listening
    socket — the caller must keep a reference alive for the process
    lifetime (closing it releases the port).
  - **Failure (`OSError` — port already bound, another instance is
    primary):** connects to `(HOST, PORT)` as a client, immediately closes
    the connection (the connection attempt itself is the signal), and
    returns `None`.
- No `SO_REUSEADDR`: on Windows this can silently permit binding a port
  that's already actively listened on, which would defeat the exclusivity
  check this mechanism depends on. Left at the socket default (off).

### Wiring in `main.py`

```
_singleton_socket = single_instance.acquire_or_signal(on_signal=open_config)
if _singleton_socket is None:
    sys.exit(0)  # another instance is already running and was just signaled
```

Placed at the very top of `main()`, before the camera is opened — a second
launch must exit immediately without touching the webcam, the tray, or
hotkeys, all of which are already owned by the primary instance.

`on_signal=open_config` reuses the existing `open_config` function
unchanged (already used by both the tray menu and the global hotkey) — it
already does the right thing (`engine.control_enabled.clear()` then
`root.after(0, config_window.show)`), and calling it from the socket
listener's background thread is the same pattern already used when the
tray thread calls it directly.

`_singleton_socket` must be held in a variable that outlives `main()`'s
setup and stays referenced through `root.mainloop()` — assigning it in
`main()`'s local scope is sufficient since `main()`'s frame is alive for
the whole process lifetime (it's blocked in `root.mainloop()`).

## Approach: Skip Wizard on Subsequent Launches

`main.py` already loads `config.json` via `config_mod.load_config` at the
top of `main()` unconditionally (returning defaults if the file is
missing). The new signal for "already set up" is simply whether that file
exists on disk:

```
has_saved_config = Path(CONFIG_PATH).exists()
```

After constructing `ConfigWindow` (still always constructed — it's cheap,
and it must exist so `open_config`/the tray/the hotkey can show it later):

- **`has_saved_config` is `True`:** call `engine.control_enabled.set()`
  directly (the engine already holds the loaded config from its
  construction — no `update_config` call needed since nothing changed it),
  then `root.withdraw()`. The app goes straight to background tracking; no
  window is ever shown this launch.
- **`has_saved_config` is `False`** (first run, no config file yet): leave
  the root window in its default visible state, exactly as today — the
  user must complete the wizard at least once since there's nothing to
  start with yet.

No change to `ConfigWindow` itself — "Iniciar controle do mouse" (or
closing the window) still saves + applies + hides, identically, whenever
the window is shown (first run or reopened later via tray/hotkey/second
launch).

## Approach: Tray Double-Click Opens Config

`tray.py`'s existing `pystray.MenuItem("Reabrir Config", self._open_config)`
gets `default=True` added. On the Windows backend, the default menu item
is the one activated when the user double-clicks the tray icon directly,
without first opening the menu. Single left-click still opens the menu as
it does today (unchanged) — this is purely an additional shortcut, not a
behavior change to the existing click path.

## Error Handling

- If the loopback port is unreachable for reasons other than "already
  bound" (e.g. some local firewall rule blocking `127.0.0.1`, which would
  be unusual), `acquire_or_signal`'s bind attempt raises `OSError` and is
  treated identically to "another instance is running" — the launch exits
  after attempting to signal. This is an acceptable simplification: a
  loopback-only bind failing for a reason *other* than port-in-use is rare
  enough not to warrant a separate error path, and failing closed (exit
  rather than risk a duplicate instance) is the safer default.
- If the signal connection itself fails when a second launch tries to
  reach the primary instance (e.g. the primary instance is in the middle
  of shutting down and just released the port), the second launch's
  connect attempt raises `OSError`, which is caught and ignored — the
  second launch still exits either way, since the bind-failure branch is
  what triggered the signal attempt in the first place, and a failed
  signal isn't worth retrying or surfacing to the user.

## Testing

- `single_instance.py`'s bind/signal logic is testable with real loopback
  sockets in pytest (no mocking needed): bind a test port directly in the
  test to simulate "already running", call `acquire_or_signal` against
  that same port and assert it returns `None` and that the test's own
  listening socket receives a connection; separately, call
  `acquire_or_signal` against a free port and assert it returns a bound
  socket and that a subsequent client connection triggers the `on_signal`
  callback.
- `has_saved_config` branching in `main.py` is a one-line `Path.exists()`
  check with no new pure-logic surface — covered by the manual checklist,
  consistent with the rest of `main.py` (already manual-checklist-only per
  the v1 spec's testing section).
- Tray `default=True` wiring is a one-line change with no pure logic —
  manual checklist only, consistent with the rest of `tray.py`.
- **Manual checklist additions:** launch the app twice in a row and
  confirm the second launch exits immediately and the first instance's
  config window appears; delete `config.json` and confirm the wizard
  shows on next launch; run once, close (not quit) via "Iniciar", relaunch
  and confirm it goes straight to background with no window shown;
  double-click the tray icon and confirm the config window opens.

## Out of Scope (YAGNI)

- Passing data (e.g. a specific config field to jump to) through the
  signal connection — the signal is a bare connect/close, not a message
  protocol. If a future need arises to pass structured data between
  instances, the socket is already there to extend.
- Cross-platform single-instance handling (macOS/Linux) — Windows only,
  per the v1 spec's existing scope.
- Detecting and recovering a config file that exists but is corrupt or
  incomplete as a distinct case from "no config file" — `load_config`
  already falls back to defaults on invalid JSON (v1 behavior, unchanged),
  and `Path(CONFIG_PATH).exists()` being `True` for a corrupt file is an
  edge case rare enough not to special-case: it would show the "skip
  wizard" background-start path with default calibration bounds, which is
  self-correcting the next time the user reopens config and recalibrates.
