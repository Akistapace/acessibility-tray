# FaceMesh Mouse — Custom On-Screen Keyboard — Design Spec

**Date:** 2026-08-13
**Status:** Approved
**Builds on:** `2026-08-13-virtual-keyboard-launcher-design.md` (v7, superseded by this spec),
`2026-08-13-floating-keyboard-button-design.md` (v8, superseded by this spec's UI half)

## Purpose

The floating keyboard button currently opens Windows' built-in touch keyboard via
the undocumented `ITipInvocation::Toggle()` COM interface. In practice this has
proven unreliable for this app's users in a way that isn't fixable from our side:

- Windows only renders the touch keyboard when the foreground app has a focused
  editable text control that its legacy heuristic recognizes. `Toggle()` still
  returns success when it doesn't -- there is no error to catch.
- That heuristic frequently fails to recognize modern web/Electron-rendered text
  fields (confirmed: VS Code's own chat input, likely other Electron/Chromium
  apps too), which is exactly the kind of field this app's users need to type
  into.
- The failure is silent and, without the diagnostic work done this session,
  indistinguishable from the click simply not registering.

This app's whole purpose is giving users who can't reliably use a physical
keyboard a way to interact via head-tracked cursor clicks. A keyboard that
silently refuses to appear in common apps defeats that purpose. Building a
small on-screen keyboard directly into the app removes the dependency on
Windows' text-field detection entirely: every key just sends a synthetic
keystroke (the same mechanism `voice_typing.py` already uses for Win+H), which
every focused field receives identically to a real key press, regardless of
how that field is implemented.

## Approach

### Remove `virtual_keyboard.py`

Delete `src/facemesh_mouse/virtual_keyboard.py` and `tests/test_virtual_keyboard.py`
outright. No COM/`ITipInvocation` code remains. `action_buttons.py`'s keyboard
circle no longer needs the warning-pulse/tooltip machinery added this session
to compensate for the OS API's silent failures (`WARNING_PULSE_COLOR`,
`NO_FOCUS_TOOLTIP_TEXT`, and the `opened`/red-pulse branch in `_on_release`)
-- the custom keyboard cannot fail this way, so that branch collapses back to
a single unconditional `show_pulse` call, same as the mic button already does.
`click_feedback.show_tooltip` (added this session for the same reason) has no
remaining caller after this change and is removed along with its tests.

### `modules/config.py`: `CustomKeyboardConfig`

Same shape and pattern as `ActionButtonsConfig`:

```python
@dataclass
class CustomKeyboardConfig:
    """Screen position of the custom on-screen keyboard panel, in pixels
    (top-left corner). `None` means "never dragged" -- the panel falls back
    to its default bottom-center position (see ui/custom_keyboard.py).
    `compact` persists which of the two layouts (letters-only vs full
    QWERTY) the user last had selected."""

    x: float | None = None
    y: float | None = None
    compact: bool = True
```

Wired into `AppConfig`, `load_config`, `save_config` exactly like
`action_buttons` is today (new `"custom_keyboard"` JSON key, `_optional_float`
reused for x/y, plain `bool()` coercion with a safe fallback to `True` for a
non-boolean `compact` value).

### `ui/custom_keyboard.py` (new)

A `CustomKeyboard` class, constructed once in `main.py` alongside
`ActionButtons` and kept alive for the process's life, starting hidden
(`withdraw()`). This mirrors `ConfigWindow`'s show/hide lifecycle rather than
`ActionButtons`' always-visible one, and means the panel's widget tree, shift
state, and layout-mode selection persist across opens within a session.

**Window:** plain `tkinter.Toplevel` (not CustomTkinter -- same reason
`action_buttons.py` gives: needs the raw Win32 `WS_EX_NOACTIVATE` style so
clicking a key never steals focus away from the real text field being typed
into). Borderless, always-on-top, draggable via a thin title strip at the top
(the strip is the only drag handle -- individual keys must not double as drag
targets, or a slightly-off click meant to press a key would move the window
instead). The title strip also hosts the compact/full toggle and the close
(X) button.

**Default position:** bottom-center, above the taskbar -- reuses
`action_buttons._taskbar_reserved_px` (promoted to a shared helper, see
below) rather than duplicating the `SPI_GETWORKAREA` logic. Draggable
afterward; position and layout-mode choice save to `config.json` on drag
release and on toggling compact/full, following the same read-modify-write
pattern `action_buttons.py._save_position` uses (never writing a stale whole-
`AppConfig` snapshot).

**Layout data** (module-level constants, pure data -- no OS calls, directly
testable):

```python
COMPACT_ROWS = [
    list("QWERTYUIOP"),
    list("ASDFGHJKL"),
    list("ZXCVBNM"),
]
FULL_EXTRA_ROWS = [
    list("1234567890"),
    [",", ".", "-", "?"],
]
```

Compact mode renders `COMPACT_ROWS` plus a bottom row of
Shift / Space / Backspace / Enter. Full mode renders `FULL_EXTRA_ROWS` above
that same letter grid, plus the same bottom row. Keys are ~46px square
`tk.Button`s in a `grid()` layout; the bottom row's Space key spans multiple
columns (it's the most-used key and the largest target is the easiest to hit
with head-tracked cursor precision).

**Key press -> synthetic input:** one `pynput.keyboard.Controller()` instance
held by the `CustomKeyboard`, matching `voice_typing.py`'s usage:

- Letters/numbers/punctuation/space: `controller.type(char)`, uppercased
  first if Shift is active. `.type()` handles the shift state internally, so
  there's no manual `Key.shift` press/release sequencing to get wrong.
- Backspace: `controller.press(Key.backspace); controller.release(Key.backspace)`.
- Enter: `controller.press(Key.enter); controller.release(Key.enter)`.

**Shift:** a toggle, not a hold (holding isn't possible when every press is
a discrete head-tracked-cursor click). Clicking Shift flips an internal
`self._shift_active` bool and changes that key's own background color to
show it's engaged; every subsequent letter is typed uppercase until Shift is
clicked again. It does not auto-release after one letter -- explicitly
rejected in favor of toggle during design (fewer clicks for multi-word
sentences with several capitals, e.g. names).

**Open/close:** `show()` (called from `action_buttons.py`, replacing
`virtual_keyboard.open_virtual_keyboard()`) calls `deiconify()` if hidden;
already-visible is a no-op -- the button only opens, matching the existing
convention (`ui/action_buttons.py`'s original docstring: "open the touch
keyboard ... on click", never a toggle-closed-by-the-same-button). Closing is
exclusively the panel's own X button, calling `withdraw()`. This sidesteps
the entire class of bug this session spent most of its time on: since the
window's shown/hidden state lives in our own process as plain Python/Tk
state (`winfo_viewable()`), there is no external OS-tracked flag to desync
from.

### `ui/action_buttons.py` changes

Unlike `virtual_keyboard`/`voice_typing` (stateless modules -- every call is
independent, nothing persists between them), `CustomKeyboard` is a real
window that must be constructed once and stay alive so its shift state and
layout-mode selection survive across opens. `ActionButtons` can't reach it
through a bare module-level call the way it does today; it needs an actual
reference to the same instance `main.py` constructs.

- `ActionButtons.__init__` gains a `custom_keyboard: CustomKeyboard`
  parameter, stored as `self._custom_keyboard`, mirroring how it already
  takes `config`/`config_path`.
- `_on_release`'s keyboard branch collapses to:

  ```python
  self._custom_keyboard.show()
  click_feedback.show_pulse(self._window, event.x_root, event.y_root)
  ```

  (single call, no branching -- matches the mic button's existing shape).
- Remove the `virtual_keyboard` import, `WARNING_PULSE_COLOR`,
  `NO_FOCUS_TOOLTIP_TEXT`, and the `opened` variable/branch.

### Shared taskbar-offset helper

`action_buttons._taskbar_reserved_px` moves to a small shared module (e.g.
`ui/screen.py`) since both `action_buttons.py` and `custom_keyboard.py` need
it for their default-position math. `action_buttons.py` is updated to import
it from there; behavior is unchanged, this is a pure relocation to avoid
duplicating the `SPI_GETWORKAREA` ctypes call in two files.

### `main.py` wiring

Construct `CustomKeyboard` once, same call shape as `ActionButtons`:

```python
custom_keyboard_panel = CustomKeyboard(root, app_config, CONFIG_PATH, screen_size)
```

Held alive for the process's life; not shown/hidden with the config window or
pause state (same lifecycle rule `action_buttons.py`'s docstring already
states for itself).

### README

Replace the "clique num campo de texto antes" caveat (added this session)
with a short note that the app's own keyboard is used instead of Windows'
touch keyboard, so it works in any focused field.

## Testing

`tests/test_custom_keyboard.py`, following `test_action_buttons.py`'s
existing patterns (`container` fixture, `_FakeEvent`, monkeypatching
`pynput.keyboard.Controller`):

- Layout data: compact mode renders exactly `COMPACT_ROWS` + bottom row;
  full mode additionally renders `FULL_EXTRA_ROWS`.
- Each letter/number/punctuation key click calls `Controller.type` with the
  correct (lower or upper, depending on shift state) character.
- Backspace/Enter click call `press`/`release` with the right `Key`.
- Clicking Shift toggles `_shift_active` and the next letter is typed
  uppercase; clicking Shift again reverts to lowercase without needing a
  letter click in between.
- Toggling compact/full persists `compact` to `config.json` (read-modify-
  write, not a stale whole-config overwrite -- same guard
  `test_dragging_does_not_clobber_settings_saved_after_startup` proves for
  `action_buttons.py`).
- `show()` is idempotent when already visible (no double-`deiconify`
  side effects to worry about, but assert it doesn't raise/duplicate state).
- The title-strip drag saves position the same way `action_buttons.py`'s
  drag does; clicking a key never triggers the drag path.
- `CustomKeyboardConfig` round-trips through `load_config`/`save_config`
  (`tests/test_config.py`, same shape as the existing `ActionButtonsConfig`
  tests).

`tests/test_action_buttons.py`: update the keyboard-click tests to assert
`custom_keyboard.show` is called and a single unconditional pulse is shown;
delete the two warning-pulse/tooltip tests added this session (no longer
applicable).

`tests/test_click_feedback.py`: delete the three `show_tooltip` tests added
this session.

## Out of Scope (YAGNI)

- Ctrl/Alt/Windows/function keys, arrow keys, Tab, Esc -- this app's purpose
  is typing text into a focused field, not general keyboard/app control.
- Autocomplete, word suggestions, or predictive text.
- Multiple keyboard layouts (e.g. non-QWERTY, non-Portuguese punctuation
  sets) -- one layout, matching the rest of the UI being Portuguese-only.
- Resizing the panel or its keys -- fixed size, matching `action_buttons.py`'s
  fixed circle size.
- Any change to `voice_typing.py` (unrelated feature, already reliable since
  it also uses synthetic input rather than an OS heuristic) or to
  `engine.py`, `mouse_controller.py`, `gestures.py`, `tracker.py`.
