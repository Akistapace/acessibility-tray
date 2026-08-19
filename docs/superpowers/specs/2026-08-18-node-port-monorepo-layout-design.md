# FaceMesh Mouse — Node Port — Monorepo Layout Design

**Date:** 2026-08-18
**Status:** Draft
**Supersedes:** the "Folder layout" section of `2026-08-17-node-port-design.md` only —
every other section of that spec (Architecture, Component mapping, Native
integration, Camera pipeline requirements, What gets deleted, Testing,
Packaging, Out of scope) is unchanged and still authoritative.

## Purpose

The 2026-08-17 spec flattened `electron/` into the repo root as `src/modules`
(main-process logic) + `src/ui` (renderer code) — a single-package repo. This
supersedes that flat layout with a pnpm-workspace monorepo: `apps/desktop`
(this app) + `packages/shared` (cross-cutting types/constants), matching the
user-specified target shape below. No `electron/` folder exists anywhere in
the result — it is not a nested sub-project and it does not survive as a
flat `src/` either; its contents move into `apps/desktop/`.

## Target layout

```
facemesh-mouse/
├── apps/
│   └── desktop/
│       ├── src/
│       │   ├── main/
│       │   │   ├── index.ts                    # app bootstrap
│       │   │   ├── windows/
│       │   │   │   ├── configWindow.ts
│       │   │   │   ├── buttonsWindow.ts
│       │   │   │   ├── overlayWindow.ts
│       │   │   │   ├── trackingWindow.ts        # new: hidden always-alive tracking window
│       │   │   │   └── buttonsPosition.ts
│       │   │   ├── ipc/
│       │   │   │   ├── index.ts                 # wires ipcMain.on('backend:send', ...) to relay + registers each domain module
│       │   │   │   ├── relay.ts                 # mainRelay EventEmitter + namespaced re-emit (was ipcRelay.ts)
│       │   │   │   ├── config.ipc.ts             # config:* handlers -> services/config.service.ts, windows/configWindow.ts
│       │   │   │   ├── buttons.ipc.ts            # buttons:* handlers -> windows/buttonsWindow.ts
│       │   │   │   └── engine.ipc.ts             # start/stop/pause/resume/save_config/update_config/open_keyboard/open_voice_typing/highlight_gesture/get_config -> services/engine.service.ts
│       │   │   ├── services/
│       │   │   │   ├── engine.service.ts         # was engine.ts: command dispatch + frame loop orchestration
│       │   │   │   ├── gestures.service.ts        # was gestures.ts
│       │   │   │   ├── mouseController.service.ts  # was mouseController.ts (nut-js)
│       │   │   │   ├── config.service.ts            # was config.ts: calibration/gesture config load/save/merge/clamp
│       │   │   │   ├── clickLog.service.ts           # was clickLog.ts
│       │   │   │   ├── win32.service.ts               # was win32.ts: koffi COM/registry/foreground-window
│       │   │   │   └── tray.service.ts                 # was tray.ts + trayState.ts
│       │   │   └── config/
│       │   │       └── environment.ts             # app-level runtime config: isDev, paths, version — distinct from services/config.service.ts's user-facing calibration config
│       │   ├── preload/
│       │   │   └── index.ts                        # contextBridge, unchanged contract
│       │   └── renderer/
│       │       ├── tracking/                        # hidden window: camera + FaceLandmarker (WASM) + opencv.js + point tracker
│       │       │   ├── faceMetrics.ts                # was tracker.py
│       │       │   ├── pointTracker.ts               # was point_tracker.py
│       │       │   └── index.html, index.ts
│       │       ├── config/                            # was src/ui/config
│       │       ├── buttons/                            # was src/ui/buttons
│       │       └── overlay/                             # was src/ui/overlay
│       ├── tests/                                        # was repo-root tests/*.ts
│       ├── package.json
│       ├── tsconfig.json, tsconfig.renderer.json
│       ├── vitest.config.ts
│       ├── electron-builder.yml
│       └── scripts/                                       # buildRenderer.mjs, copyStaticAssets.mjs
│
├── packages/
│   └── shared/
│       ├── src/
│       │   ├── types/
│       │   │   └── tracking.ts                # FaceMetrics, TrackingFrame (was modules/types.ts) — crosses the tracking-renderer <-> main boundary
│       │   ├── constants/
│       │   │   └── gestures.ts                # GESTURE_NAMES, GestureName (was duplicated between modules/config.ts and ui/config/labels.ts)
│       │   └── schemas/                        # empty for now — no cross-cutting validation schema exists yet; not consolidating config validation as a side effect of this move
│       └── package.json
│
├── package.json              # root: workspace-level scripts only (pnpm -r build/test/dev)
├── pnpm-workspace.yaml        # packages: ["apps/*", "packages/*"]
└── tsconfig.json               # root references, if needed for editor tooling
```

`apps/api` and `packages/ui` from the reference diagram are not created: this
app has no HTTP backend (no auth, no users domain — everything runs
in-process inside Electron's main process per the architecture section of
the 2026-08-17 spec) and no second UI consumer to share components with.
Creating empty placeholder packages for them is scope the app doesn't need
yet.

## Why `ipc/` splits per-domain instead of staying one relay module

The existing (pre-port) `electron/src/main/ipcRelay.ts` centralizes both the
renderer-to-main multiplexed channel (`backend:send`, a discriminated union
on `type`) and the re-emit-to-`mainRelay` routing for namespaced commands
(`config:*`, `buttons:*`). `configWindow.ts`/`buttonsWindow.ts` each register
their own `mainRelay.on(...)` listener directly, since they need closure
over their own `win` variable.

Matching the diagram's `ipc/index.ts` + `auth.ipc.ts` + `app.ipc.ts` pattern
means separating "own the BrowserWindow" from "handle the IPC event" more
than the current code does:

- `ipc/relay.ts` keeps only the router plumbing: the `mainRelay` EventEmitter
  and the `backend:send` -> either `mainRelay.emit` (namespaced) or
  `engine.handleCommand` (everything else) split.
- `ipc/config.ipc.ts` and `ipc/buttons.ipc.ts` hold the
  `mainRelay.on('config:reset-position', ...)` /
  `mainRelay.on('buttons:drag-move', ...)` / `mainRelay.on('buttons:drag-end',
  ...)` listeners that today live inside `windows/configWindow.ts` /
  `windows/buttonsWindow.ts`. They call back into the window modules through
  exported functions (`resetButtonsPosition()`, a new
  `moveButtonsWindow(dx, dy)` / `endButtonsDrag()` pair) instead of the
  window module owning the listener itself.
- `ipc/engine.ipc.ts` holds the handlers for engine-lifecycle commands
  (`start`, `stop`, `pause`, `resume`, `save_config`, `update_config`,
  `open_keyboard`, `open_voice_typing`, `highlight_gesture`, `get_config`) —
  these already dispatch through `BackendServer.handle_command`'s equivalent
  (`engine.service.ts`'s command table) in the current design, so this file
  is mostly a thin re-export of that dispatch, wired to the `backend:send`
  channel by `ipc/index.ts`.

The renderer-facing contract (`window.backend.send(message)` /
`window.backend.on(channel, cb)`) does not change — this reorganizes where
the receiving code lives on the main-process side only, per the "IPC
handlers stay thin" / receive-delegate-respond guidance in
`.claude/skills/electron-node-architecture/SKILL.md`.

## What moves into `packages/shared`

Only content with a real cross-boundary or duplication justification today:

Only `types/tracking.ts` moves here (`FaceMetrics`, `TrackingFrame`) —
both are used exclusively via `import type`, which TypeScript erases at
compile time, so there is no runtime resolution cost in either the main
process (Node, real `node_modules` resolution) or the renderer (plain
`<script type="module">`, no bundler, no import map).

`GESTURE_NAMES`/`GestureName` do **not** move here despite the
duplication between `services/config.service.ts` and
`renderer/config/labels.ts`: `GESTURE_NAMES` is consumed as a runtime
*value* by `labels.ts`, and the renderer has no bundler to resolve a bare
`@facemesh-mouse/shared` value import at runtime — it would compile and
pass every Node-environment vitest test cleanly, then 404 the moment the
real app opens the config window. Fixing the duplication needs either a
build-time copy step or (more likely) having the renderer derive its
gesture list from the `config` message it already receives instead of
importing a static list — real work, left for a follow-up rather than
riding along with a folder-layout move.

Nothing else moves preemptively — `packages/shared/src/schemas/` is created
empty as a placeholder directory only, not populated, since no other
cross-cutting schema exists yet and consolidating config validation is out
of scope for a folder-layout change.

## Tooling

- `pnpm-workspace.yaml` at repo root: `packages: ["apps/*", "packages/*"]`.
- pnpm is not installed locally; bootstrap via Node 24's built-in corepack
  (`corepack enable`, pin a `packageManager` field in the root
  `package.json`) rather than a global npm install.
- Each workspace package owns its own `package.json`. `apps/desktop` also
  owns `vitest.config.ts` and `tests/`; `packages/shared` owns a
  `tsconfig.json` and a `typecheck` script, since it currently holds only
  type-only exports with nothing to runtime-test. Root `package.json` only
  fans out (`pnpm -r build`, `pnpm -r test`, `pnpm --filter desktop dev`).
- `apps/desktop/tsconfig.json` references `packages/shared` via TS project
  references (or a plain workspace `"@facemesh-mouse/shared": "workspace:*"`
  dependency, whichever the implementation plan finds simpler once the
  actual `tsconfig` structure is in hand) so type-only imports resolve
  without a build step during `vitest`/`tsc --noEmit`.

## Migration mechanics

The `worktree-node-port` branch already has 8 commits against the old flat
`src/modules` + `src/ui` layout (config.ts, gestures.ts, mouseController
math, clickLog.ts, pointTracker.ts, faceMetrics.ts, win32.ts ports) plus
uncommitted WIP (`package.json`, `mouseController.ts`,
`mouseController.test.ts`). This is a path-rewrite pass on top of that work:

1. Commit or stash the current uncommitted WIP first — nothing gets lost.
2. Create the workspace skeleton (`pnpm-workspace.yaml`, root `package.json`,
   `apps/desktop/package.json`, `packages/shared/package.json`).
3. `git mv` each existing file to its new path per the layout above (main
   modules -> `apps/desktop/src/main/services/*.service.ts`, IPC listener
   code split out of `windows/*.ts` into the new `ipc/*.ipc.ts` files, `src/ui`
   -> `apps/desktop/src/renderer`, `types.ts`/`GESTURE_NAMES` ->
   `packages/shared`).
4. Update every import path touched by the move; update `tsconfig.json`,
   `vitest.config.ts`, `electron-builder.yml`'s `files` globs, and
   `scripts/buildRenderer.mjs`/`copyStaticAssets.mjs` for the new roots.
5. Re-run the full vitest suite + `tsc --noEmit` in both packages before
   continuing with the remaining node-port tasks (tracking renderer,
   native integration) from the original 19-task plan — those tasks
   proceed against the new paths, unmodified in substance.

The 19-task implementation plan (`docs/superpowers/plans/2026-08-17-node-port.md`)
needs its file paths updated to match this layout; that update happens in
writing-plans, not in this spec.
