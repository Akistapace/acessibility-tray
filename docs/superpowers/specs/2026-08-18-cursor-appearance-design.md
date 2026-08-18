# FaceMesh Mouse — Cursor Appearance (Size / Color / Mista) — Design Spec

**Date:** 2026-08-18
**Status:** Draft
**Builds on:** `2026-08-05-facemesh-mouse-design.md` (v1),
`2026-08-05-usability-anchor-mode-design.md` (v2),
`2026-08-06-single-instance-background-startup-design.md` (v3),
`2026-08-07-gesture-expansion-modern-ui-design.md` (v4),
`2026-08-07-optical-flow-tracking-design.md` (v5),
`2026-08-07-mouse-yield-and-click-feedback-design.md` (v6),
`2026-08-13-virtual-keyboard-launcher-design.md` (v7),
`2026-08-13-floating-keyboard-button-design.md` (v8)

## Purpose

The app moves the real Windows cursor (via `pynput`, see `mouse_controller.py`)
— it has never drawn its own. Some users targeted by this app (motor
disabilities, per the accessibility focus of the whole project) benefit from
a bigger and/or higher-contrast pointer, the same way Windows' own
Accessibility settings already offer. This feature lets that be tuned from
inside the app's own config window instead of sending the user out to
Windows Settings: pointer **size**, a **solid color** (white/black/custom),
and a **"mista"** mode that inverts whatever is under the pointer, so it's
never invisible no matter the background.

## Approach

### Why not draw our own on-screen cursor

Considered and declined, matching this project's established stance (see
`virtual_keyboard.py`'s doc comment: "the app doesn't build its own... it
makes the existing one reachable"). Hiding the real system cursor to draw a
substitute is itself a global, OS-wide change with no simpler mechanism than
what's used here — and it would additionally require streaming cursor
position into the overlay window every frame and re-sampling the screen
under the pointer continuously for "mista," adding latency and CPU cost on
top of a change that's no more contained. Windows' own pointer customization
(`ms-settings:easeofaccess-mousepointer`) solves exactly this by writing a
generated cursor file into `HKCU\Control Panel\Cursors\Arrow` and calling
`SystemParametersInfoW(SPI_SETCURSORS)` to reload it — this design does the
same thing, so "mista" reuses Windows' real per-pixel inversion (a
mask-based cursor trick, see below) instead of polling screen colors.

**Scope:** only the `Arrow` cursor role. Windows has 17 cursor roles (Wait,
IBeam, Hand, resize arrows, ...); this feature only touches the one the user
asked about ("a seta do mouse"). The other 16 stay whatever the user's
Windows theme already has them as.

### `cursor_theme.py` (new)

```python
def apply_cursor(size_px: int, mode: str, custom_color: str) -> None
def restore_cursor() -> None
```

**`apply_cursor`** is a no-op (and never touches the registry) when
`size_px == 32` (Windows' own default) **and** `mode == "default"` — an
existing user who never opens this section sees no behavior change at all.
Otherwise it:

1. Builds a 32bpp BGRA arrow-shaped bitmap at `size_px` with Pillow, using
   the same silhouette as Windows' stock arrow, hotspot at the tip:
   - `mode="default"`: black fill, white outline (matches Windows' own
     stock look) — lets size be changed independent of color.
   - `mode="white"` / `"black"`: solid fill in that color, with a thin
     outline in whichever of black/white contrasts against it, so the
     shape stays legible against a same-color background (a static
     one-time contrast choice, not a live one — full protection against
     any background is what "mista" is for).
   - `mode="custom"`: same treatment, fill = `custom_color`.
   - `mode="mista"`: **not** a colored bitmap. Builds the classic 1bpp
     AND+XOR mask cursor instead: inside the arrow silhouette,
     `AND=1, XOR=1` (inverts whatever pixel is under it); outside the
     silhouette, `AND=1, XOR=0` (fully see-through). This is the exact
     mechanism behind Windows' own "Invertido" pointer scheme — real
     per-pixel inversion done by the cursor compositor, zero ongoing cost
     to this app (no polling, no screen sampling).
2. Serializes that bitmap into a `.cur` file (ICONDIR + one
   ICONDIRENTRY + legacy `BITMAPINFOHEADER`-based color+mask image data —
   the same on-disk format `.cur` has always used, no PNG payload, for
   maximum cursor-loader compatibility) at
   `%LOCALAPPDATA%\FaceMeshMouse\cursors\arrow.cur`.
3. On the **first** call this session that's about to overwrite
   `HKCU\Control Panel\Cursors\Arrow`, reads and stashes its current value
   (which may be empty/absent — that's a valid "original" too) into
   `%LOCALAPPDATA%\FaceMeshMouse\cursors\original_arrow.json`, only if that
   stash file doesn't already exist (so a second app run doesn't overwrite
   the *real* original with our own generated path from a prior run that
   never got restored, e.g. after a crash).
4. Writes the new path into that registry value and calls
   `ctypes.windll.user32.SystemParametersInfoW(SPI_SETCURSORS=0x0057, 0,
   None, SPIF_SENDCHANGE=0x0002)` to force every window to reload cursors.

**`restore_cursor`** reads `original_arrow.json` (no-op if it doesn't
exist — nothing was ever changed), writes that value back to
`HKCU\Control Panel\Cursors\Arrow` (or deletes the value if the stash says
it was absent), calls `SystemParametersInfoW(SPI_SETCURSORS)` again, then
deletes the stash file so a clean state doesn't linger.

Every public function in this module catches its own exceptions
(`OSError`, `ctypes` failures) and prints to stderr — matching
`virtual_keyboard.py`'s rule that a failure here must never affect
tracking, exactly as `BackendServer.handle_command`'s outer try/except
already guarantees for every command handler, but the module guards
itself too so `restore_cursor()` at shutdown can't raise past its
caller.

### Config (`config.py`)

```python
@dataclass
class CursorConfig:
    size_px: int = 32
    mode: str = "default"        # default | white | black | custom | mista
    custom_color: str = "#000000"  # hex, only meaningful when mode == "custom"
```

- `AppConfig` gains `cursor: CursorConfig = field(default_factory=CursorConfig)`.
- `CURSOR_SIZE_RANGE = (32, 96)` in the same clamping style as
  `CALIBRATION_RANGES`; `mode` falls back to `"default"` if it's not one of
  the five valid values (same pattern `_merge_gesture` uses for `action`).
- `config_to_dict` / `config_from_dict` gain a `cursor` key, parallel to
  `action_buttons`.
- `_cmd_save_config` in `backend.py` merges `cursor` the same way it already
  merges `action_buttons` (`merged["cursor"] = {**on_disk_dict["cursor"],
  **payload["cursor"]}` when `"cursor" in payload`).

### Backend wiring (`backend.py`)

- New command `_cmd_set_cursor_theme(self, command)`: updates
  `self.config.cursor` from the payload (clamped the same way
  `CalibrationConfig` fields are), then calls
  `cursor_theme.apply_cursor(...)`. This does **not** write `config.json` —
  same "changes apply immediately, only `Salvar` persists them for next
  launch" split the rest of the app already uses, just without needing
  `Iniciar` first, since cursor appearance isn't gated by
  `control_enabled`.
- `main()`: right after `config = config_mod.load_config(CONFIG_PATH)`, if
  the loaded `config.cursor` isn't the all-defaults value, call
  `cursor_theme.apply_cursor(...)` once at startup — a saved cursor theme
  must survive an app restart, not just a live session.
- `main()`'s existing `finally: stop.set(); engine.stop()` gains
  `cursor_theme.restore_cursor()` alongside them. This path already runs on
  a graceful shutdown: `BackendProcess.stop()` (`electron/src/main/backendProcess.ts`)
  closes stdin first and only force-kills after a 2s grace period, which is
  exactly what lets Python's `finally` block run before the process dies.

### Config UI (Electron)

New block in the **Extras** tab (`electron/src/renderer/config/index.html`),
below the existing keyboard/voice toggles — "Aparência do cursor":

```html
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
```

`index.ts` gains a `cursor` field on `AppConfigJson`/`currentConfig`
(defaults `{ size_px: 32, mode: "default", custom_color: "#000000" }`),
included in `applyConfigToForm`/`readFormIntoConfig` the same way
`calibration` fields are, and **kept** in the save/toggle payloads (unlike
`action_buttons`, this window is the sole owner of cursor settings — no
other window edits it).

Live-apply: an `input` listener on all three controls calls
`readFormIntoConfig()` then sends
`{ type: "set_cursor_theme", ...currentConfig.cursor }`, debounced ~150ms
(a `setTimeout`/`clearTimeout` pair, same shape as the existing save-state
timers) so dragging the size slider or the color picker doesn't regenerate
the cursor file and broadcast `SPI_SETCURSORS` dozens of times a second —
that would visibly flicker the real system pointer while dragging.

## Error Handling

- Every `cursor_theme.py` call swallows its own exceptions (registry
  access denied, disk write failure, malformed stash file) and prints to
  stderr, never raising into `BackendServer.handle_command` or `main()`'s
  shutdown path.
- A corrupt/missing `original_arrow.json` at restore time is treated as
  "nothing to restore" (logged, not raised) rather than guessing — an
  incorrect guess could leave the user's real original cursor overwritten
  with our own generated one after uninstall.

## Testing

Pure logic, no real registry/Windows calls, matching this project's
existing split (`test_config.py`'s style):

- `test_cursor_theme.py`: the AND/XOR mask bit pattern for `mista` (inside
  vs. outside the arrow silhouette), the `.cur` byte layout (ICONDIR
  count/type, ICONDIRENTRY hotspot fields), and the "original stash only
  written once" guard — all against an injected fake filesystem path, no
  registry access.
- `test_config.py`: `CursorConfig` clamping (`size_px` range, invalid
  `mode` falls back to `"default"`) and `config_to_dict`/`config_from_dict`
  round-trip, same shape as existing `CalibrationConfig` tests.
- `test_backend.py`: `_cmd_set_cursor_theme` updates `self.config.cursor`
  and calls a monkeypatched `cursor_theme.apply_cursor` with the right
  arguments; `_cmd_save_config` merges a partial `cursor` payload against
  on-disk values, mirroring the existing `action_buttons` merge test.
- **Manual checklist**: drag the size slider — real Windows arrow visibly
  grows/shrinks. Pick white/black/custom — arrow recolors. Pick "Mista" —
  arrow inverts whatever's under it (test over both a white and a black
  window background). Close the app (window close *and* tray "Sair") —
  Windows arrow returns to whatever it was before the app touched it.
  Restart the app after saving a theme — themed arrow reappears
  automatically without touching the slider again.

## Out of Scope (YAGNI)

- Any cursor role besides `Arrow` (IBeam, Hand, resize handles, Wait, ...).
- Per-monitor or per-DPI scaling beyond what Windows already applies to a
  fixed-pixel cursor bitmap.
- A live "hover-sampled" invert (reading actual screen pixel color under
  the pointer every frame) — "mista" uses the mask-based real inversion
  described above instead, which is exact and free, not an approximation.
- Any change to `mouse_controller.py`, `engine.py`, `gestures.py`, or the
  overlay's click-pulse rendering (`pulse.ts`) — this feature only touches
  the OS-level pointer bitmap, never the pulse feedback drawn on click.
- Syncing the theme to the `buttons` or `overlay` windows — they don't
  render a cursor themselves, so there's nothing in them to update.
