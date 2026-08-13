# FaceMesh Mouse — Floating Keyboard Button — Design Spec

**Date:** 2026-08-13
**Status:** Approved
**Builds on:** `2026-08-05-facemesh-mouse-design.md` (v1),
`2026-08-05-usability-anchor-mode-design.md` (v2),
`2026-08-06-single-instance-background-startup-design.md` (v3),
`2026-08-07-gesture-expansion-modern-ui-design.md` (v4),
`2026-08-07-optical-flow-tracking-design.md` (v5),
`2026-08-07-mouse-yield-and-click-feedback-design.md` (v6),
`2026-08-13-virtual-keyboard-launcher-design.md` (v7)

**Supersedes:** v7's "Entry points" section. `virtual_keyboard.py` and its
`open_virtual_keyboard()` function are unchanged; only how the user reaches
them changes.

## Purpose

v7 wired the on-screen-keyboard launcher into the tray menu and a
config-window button. Both require the user to first reach a menu or open a
window — an extra step, and one of the two (the config-window button) turns
out to freeze head-tracked cursor control the moment it's reachable (see
v7's corrected "Entry points" section). This spec replaces both with a
single, always-visible floating button: a small draggable circle sitting in
a screen corner the whole time the app runs, one click away regardless of
what else is open.

## Approach

### `keyboard_button.py` (new, `src/facemesh_mouse/ui/`)

A borderless, always-on-top `tk.Toplevel` — a circle ~60px in diameter,
solid `#4da3ff` fill (the same blue as the click-feedback pulse ring,
`click_feedback.py`'s `_RING_COLOR`), with a white "⌨" glyph centered on it.
Built with the same `-transparentcolor` trick `click_feedback.py` already
uses to render a non-rectangular window: `wm_attributes("-transparentcolor",
"black")`, a `tk.Canvas` with a black background, `create_oval` for the
circle. Unlike the click-feedback pulse, this window is **not**
click-through — it must receive drag and click events — so it skips
`_make_click_through` entirely.

Constructed once in `main.py`, alongside the engine and tray, and kept alive
for the process's lifetime — no show/hide wiring into `_poll_status` or the
pause/no-face state machine. It stays visible while paused, while no face is
detected, and while the config window is open on top of it (the config
window no longer has a keyboard-related button of its own, so there's
nothing to conflict with — see "Removed" below).

### Click vs. drag

Bound directly on the Toplevel: `<ButtonPress-1>` records the press point
and the window's current position; `<B1-Motion>` moves the window by the
same delta as the cursor, live, clamped so the circle can't be dragged
fully off-screen; `<ButtonRelease-1>` decides what happened. If the release
point is within `CLICK_DRAG_THRESHOLD_PX = 5` of the press point — the same
scale as `DWELL_STILL_PX` and `YIELD_DETECT_PX` elsewhere in this codebase
— it's a click: call `virtual_keyboard.open_virtual_keyboard()`. Past the
threshold, it's a drag: no click fires, and the new position is persisted
(below).

A gesture-fired click (`pynput`'s synthetic `Button.left` click via
`MouseController.fire_action`) generates the same OS-level button-down/up
pair a physical click does, arriving at the Toplevel through the same Tk
bindings — so opening the keyboard through the head-tracked cursor keeps
working with no special-casing. Dragging needs a real press-hold-move-release
sequence, which only a physical mouse or trackpad can produce today (there's
no "hold" primitive in the gesture/dwell-click system) — consistent with
this being explicitly a mouse interaction, not a keyboard-feature one.

### Position: default and persistence

`AppConfig` gains a new field:

```python
@dataclass
class KeyboardButtonConfig:
    x: float | None = None
    y: float | None = None
```

`None` (the default, and what a fresh `config.json` has) means "not yet
dragged" — the button places itself in the bottom-right corner, inset by a
fixed margin, computed from the screen size already read in `main.py`
(`root.winfo_screenwidth()`/`winfo_screenheight()`).

On `<ButtonRelease-1>` past the drag threshold, the new top-left position is
written straight to `config.json` via `config_mod.save_config` — this is a
UI preference, not a calibration value, so it doesn't go through
`ConfigWindow`'s deep-copy/apply-on-start flow; it saves immediately,
independent of whether the config window is even open.

On load, if a saved position falls outside the current screen bounds (a
resolution or monitor change since it was last dragged), it's treated as
absent and the button falls back to the default corner — the same
"clamp on load" philosophy `CALIBRATION_RANGES` already uses for hand-edited
config values.

### Removed

- `tray.py`: the "Abrir Teclado" `pystray.MenuItem`, `TrayIcon.__init__`'s
  `on_open_keyboard` parameter, and the `_open_keyboard` handler — back to
  the three items from before v7 (Pausar/Retomar, Reabrir Config, Sair).
- `config_gui.py`: the "Abrir Teclado" `CTkButton` on the "Ajuda" tab, the
  sentence v7 added to `_HELP_TEXT` about it, and the now-unused
  `virtual_keyboard` import.
- `main.py`: the `on_open_keyboard=virtual_keyboard.open_virtual_keyboard`
  keyword passed to `TrayIcon(...)`. `virtual_keyboard` is still imported,
  but only to wire it into the new `KeyboardButton` instead.

`virtual_keyboard.py` itself — `open_virtual_keyboard()` and its
swallow-and-print error handling — is untouched; it just gains a new (and
now sole) caller.

## Error Handling

Unchanged from v7: a failed `osk.exe` launch is caught and printed inside
`open_virtual_keyboard`, never reaches the button's click handler. If the
button's own construction fails for some reason (unlikely — no known
failure mode, mirroring `click_feedback`'s reasoning), the exception is
caught in `main.py` and printed once rather than crashing startup; the app
still runs, just without the floating button.

## Testing

- **Click-vs-drag decision** as a pure function, e.g. `_is_click(press_xy,
  release_xy) -> bool`, tested directly: within threshold on both axes is a
  click; past it on either axis is a drag; exactly at the threshold (an
  edge case worth pinning down explicitly).
- **Default position** computed from a given screen size lands in the
  bottom-right corner with the expected margin.
- **Position persistence**: saving after a drag round-trips through
  `save_config`/`load_config`; a saved position outside a smaller screen
  size falls back to the default on load.
- **Construction smoke test**, matching `click_feedback`'s pattern under
  the shared Tk root fixture: build and destroy the button, assert it
  doesn't raise, and assert the transparent-circle window attributes are
  set (`-transparentcolor`, `-topmost`) — and, unlike the pulse, that
  click-through styling is **not** applied.
- **Manual checklist**: click the circle — OSK opens. Drag the circle to
  another corner, restart the app — it reopens there. Resize/change display
  resolution so the saved spot is off-screen, restart — it falls back to
  the default corner. Trigger a mapped gesture aimed at the circle — OSK
  opens the same as a physical click.

## Out of Scope (YAGNI)

- The circle changing color/state (paused, no-face, yielded) — the tray
  icon already communicates that; duplicating it here is unrequested.
- Snapping to screen edges/corners while dragging.
- Any animation on drag or on open.
- Resizing the circle, or a user-configurable size.
- Any change to `virtual_keyboard.py`, `engine.py`, `mouse_controller.py`,
  `gestures.py`, `hotkeys.py`, `single_instance.py`, or `point_tracker.py`.
