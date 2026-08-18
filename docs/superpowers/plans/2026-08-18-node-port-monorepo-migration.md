# Node Port Monorepo Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reshape the `worktree-node-port` branch's already-flat `src/modules` + `src/ui` layout into a pnpm-workspace monorepo (`apps/desktop` + `packages/shared`), with no `electron/` folder anywhere and no behavior change beyond what the move itself requires.

**Architecture:** This is a structural move, not new functionality: every file gets `git mv`'d to its new home, import paths get updated to match, and the two `__dirname`-relative path computations that change depth as a direct result of the move (`backendCommand.ts`'s dev-mode `run.py` lookup, `tray.service.ts`'s icon lookup, the three window modules' `preload`/`renderer` lookups) get fixed to match their new depth. `main/ipcRelay.ts`'s single relay module splits into `main/ipc/{relay,config.ipc,buttons.ipc,index}.ts` so window modules (`windows/`) stop owning their own `ipcMain.on(...)` registrations. Nothing about the Python backend, the existing gesture/mouse-control logic, or the remaining Task 9-19 engine-port work changes in substance.

**Tech Stack:** TypeScript, Electron, Vitest, pnpm workspaces (bootstrapped via Node 24's built-in corepack).

**Spec:** `docs/superpowers/specs/2026-08-18-node-port-monorepo-layout-design.md` (supersedes only the "Folder layout" section of `docs/superpowers/specs/2026-08-17-node-port-design.md`, which stays authoritative for everything else).

## Global Constraints

- No `electron/` folder anywhere in the result — contents land in `apps/desktop/`, not nested and not left flat at repo root.
- Only `apps/desktop` and `packages/shared` are created. No `apps/api`, no `packages/ui` — nothing in this project would import them.
- `packages/shared` ships only `types/tracking.ts` (`FaceMetrics`, `TrackingFrame`) — **not** `GESTURE_NAMES`/`GestureName`. Deviation from the spec's "What moves into packages/shared" section, discovered during this plan: `apps/desktop/src/renderer/*` is loaded by Chromium directly via `<script type="module" src="index.js">` with no bundler and no import map (confirmed by the existing renderer code's relative `"./clickOrDrag.js"`-style imports) — a bare-specifier runtime *value* import (`import { GESTURE_NAMES } from "@facemesh-mouse/shared"`) would 404 in the real app despite compiling and testing clean, because `vitest.config.ts` runs every test under `environment: "node"`, which resolves bare specifiers the way Node does and would never catch a browser-only resolution failure. A **type-only** import (`FaceMetrics`, `TrackingFrame`, `GestureName`) is erased at compile time and has no such risk, in either context — that's the line this plan draws. `GESTURE_NAMES`'s existing duplication between `config.service.ts` and `labels.ts` is left exactly as it is today; a real fix (e.g. the renderer deriving its gesture list from the `config` message it already receives instead of importing a static list) is a follow-up, not part of this move. Task 5 patches the spec doc to reflect this.
- Every task ends with `pnpm --filter <package> test` (and, for apps/desktop, `tsc --noEmit` on both tsconfigs) green before moving to the next task.
- Preserve every existing code comment that explains non-obvious rationale (taskbar bounds-vs-workArea, single-instance-lock ordering, before-quit sequencing, etc.) — only comments that describe something the new structure now makes self-evident (e.g. "these are re-emitted by ipcRelay.ts (Step 7 below)") get reworded to match the new location.

---

## File Structure

```
facemesh-mouse/                        (repo root - unchanged: Python, docs, .claude/, .superpowers/)
├── run.py, src/facemesh_mouse/, requirements*.txt, pyproject.toml, backend.spec   # untouched, out of scope
├── pnpm-workspace.yaml                 # new
├── package.json                        # new: workspace-level fan-out only
├── apps/
│   └── desktop/
│       ├── package.json                # was repo-root package.json, renamed/rescoped
│       ├── tsconfig.json                # was repo-root tsconfig.json, include paths updated
│       ├── tsconfig.renderer.json        # was repo-root tsconfig.renderer.json, include paths updated
│       ├── vitest.config.ts               # was repo-root vitest.config.ts, unchanged content
│       ├── electron-builder.yml            # was repo-root electron-builder.yml, icon path fixed
│       ├── config.json.keep                # was repo-root config.json.keep
│       ├── scripts/                          # was repo-root scripts/, "ui"->"renderer" path strings updated
│       ├── assets/                            # was repo-root assets/
│       ├── tests/                              # was repo-root tests/*.ts, import paths updated
│       └── src/
│           ├── main/
│           │   ├── index.ts                     # was src/modules/index.ts
│           │   ├── config/
│           │   │   └── environment.ts             # new
│           │   ├── ipc/
│           │   │   ├── index.ts                    # new
│           │   │   ├── relay.ts                     # was src/modules/ipcRelay.ts
│           │   │   ├── config.ipc.ts                 # new (extracted from windows/configWindow.ts)
│           │   │   └── buttons.ipc.ts                 # new (extracted from windows/buttonsWindow.ts)
│           │   ├── services/
│           │   │   ├── backendCommand.ts                # was src/modules/backendCommand.ts, signature fixed
│           │   │   ├── backendProcess.ts                  # was src/modules/backendProcess.ts
│           │   │   ├── protocol.ts                          # was src/modules/protocol.ts
│           │   │   ├── clickLog.service.ts                    # was src/modules/clickLog.ts
│           │   │   ├── config.service.ts                        # was src/modules/config.ts
│           │   │   ├── gestures.service.ts                        # was src/modules/gestures.ts
│           │   │   ├── mouseController.service.ts                   # was src/modules/mouseController.ts
│           │   │   ├── win32.service.ts                               # was src/modules/win32.ts
│           │   │   ├── tray.service.ts                                  # was src/modules/tray.ts
│           │   │   └── trayState.ts                                      # was src/modules/trayState.ts
│           │   └── windows/
│           │       ├── buttonsPosition.ts       # was src/modules/windows/buttonsPosition.ts
│           │       ├── buttonsWindow.ts           # was src/modules/windows/buttonsWindow.ts, ipc listeners extracted
│           │       ├── configWindow.ts              # was src/modules/windows/configWindow.ts, ipc listener extracted
│           │       └── overlayWindow.ts               # was src/modules/windows/overlayWindow.ts
│           ├── preload/
│           │   └── index.ts                       # was src/ui/preload/index.ts
│           └── renderer/
│               ├── buttons/                         # was src/ui/buttons/
│               ├── config/                            # was src/ui/config/
│               ├── overlay/                             # was src/ui/overlay/
│               └── tracking/                              # was src/ui/tracking/
│                   └── faceMetrics.ts                       # import source updated
└── packages/
    └── shared/
        ├── package.json                # new
        ├── tsconfig.json                 # new (typecheck only, no build step)
        └── src/
            └── types/
                └── tracking.ts             # was src/modules/types.ts
```

## Interfaces carried across tasks

- **`resolveBackendCommand(isPackaged: boolean, resourcesPath: string, appPath: string): { command: string; args: string[] }`** — signature gains a third parameter in Task 3; Task 3's `index.ts` update and `backendCommand.test.ts` both use this new signature.
- **`moveButtonsWindow(dx: number, dy: number): void`** and **`endButtonsDrag(): void`** — new exports from `windows/buttonsWindow.ts`, created in Task 3, consumed by `ipc/buttons.ipc.ts` in the same task.
- **`wireIpc(backend: BackendProcess): void`** — new export from `main/ipc/index.ts`, created in Task 3, replaces `index.ts`'s direct call to `wireBackendRelay`.
- **`@facemesh-mouse/shared`** exports `FaceMetrics` and `TrackingFrame` (types only) from `packages/shared/src/types/tracking.ts`, created in Task 2.

---

### Task 1: Checkpoint-commit the in-progress Task 9 work

**Files:**
- Modify (commit only, no content changes): `package.json`, `src/modules/mouseController.ts`, `tests/mouseController.test.ts`

- [ ] **Step 1: Confirm what's uncommitted**

Run: `git status --short`
Expected:
```
 M package.json
 M src/modules/mouseController.ts
 M tests/mouseController.test.ts
```

- [ ] **Step 2: Run the existing test suite to confirm current state is green before moving anything**

Run: `npx vitest run`
Expected: all suites pass (this captures the Task 9 WIP's current state, whatever it is — this plan does not evaluate whether that work is complete, only that it survives the move unmodified).

- [ ] **Step 3: Commit as a checkpoint**

```bash
git add package.json src/modules/mouseController.ts tests/mouseController.test.ts
git commit -m "$(cat <<'EOF'
wip(mouseController): checkpoint Task 9 progress before monorepo restructure

Committed as-is so the folder-layout migration (git mv) has a clean tree
to work from. No content changes.
EOF
)"
```

---

### Task 2: `packages/shared` and the pnpm workspace root

**Files:**
- Create: `pnpm-workspace.yaml`
- Create: `package.json` (repo root — new, replaces nothing yet since the old one moves in Task 3)
- Create: `packages/shared/package.json`
- Create: `packages/shared/tsconfig.json`
- Create: `packages/shared/src/types/tracking.ts`
- Delete (after copy verified): none yet — `src/modules/types.ts` deletion happens in Task 3 once its last consumer (`gestures.ts`) moves and its import updates in the same commit as the file's removal, so nothing is left importing a dead path mid-task.

**Interfaces:**
- Produces: `@facemesh-mouse/shared` package exporting `FaceMetrics`, `TrackingFrame` from `src/types/tracking.ts`.

- [ ] **Step 1: Create the pnpm workspace manifest**

`pnpm-workspace.yaml`:
```yaml
packages:
  - "apps/*"
  - "packages/*"
```

- [ ] **Step 2: Create the new root package.json (workspace fan-out only)**

`package.json` (repo root):
```json
{
  "name": "facemesh-mouse",
  "private": true,
  "scripts": {
    "build": "pnpm --filter @facemesh-mouse/desktop build",
    "dev": "pnpm --filter @facemesh-mouse/desktop dev",
    "test": "pnpm -r test",
    "dist": "pnpm --filter @facemesh-mouse/desktop dist"
  }
}
```

This temporarily shadows the pre-existing repo-root `package.json` (the Electron app's own manifest, which still has real content needed for Task 3). Since `git mv` can't target an already-occupied path, Task 3 explicitly moves the *old* file's content into `apps/desktop/package.json` before this new one is written — so do this step, then immediately continue to Step 3 so the workspace has at least one real member before anyone runs `pnpm install` against it.

- [ ] **Step 3: Create packages/shared**

`packages/shared/package.json`:
```json
{
  "name": "@facemesh-mouse/shared",
  "version": "0.1.0",
  "private": true,
  "main": "src/types/tracking.ts",
  "types": "src/types/tracking.ts"
}
```

`packages/shared/tsconfig.json`:
```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ES2022",
    "moduleResolution": "Bundler",
    "strict": true,
    "skipLibCheck": true,
    "noEmit": true
  },
  "include": ["src"]
}
```

No `vitest.config.ts` and no `test` script here: `types/tracking.ts` is two pure interfaces with no runtime behavior to assert. `tsc --noEmit` (added as a `"typecheck"` script) is the real verification for this package.

Add a `"typecheck": "tsc --noEmit"` script to `packages/shared/package.json`'s `"scripts"`.

- [ ] **Step 4: Move the shared types**

```bash
mkdir -p packages/shared/src/types
git mv src/modules/types.ts packages/shared/src/types/tracking.ts
```

Content is unchanged — `FaceMetrics` and `TrackingFrame`, verbatim.

- [ ] **Step 5: Bootstrap pnpm via corepack and install**

```bash
corepack enable
corepack use pnpm@latest
pnpm install
```

`corepack use` pins the resolved version into the root `package.json`'s `"packageManager"` field automatically — no version number to hand-guess.

- [ ] **Step 6: Verify the shared package typechecks on its own**

Run: `pnpm --filter @facemesh-mouse/shared typecheck`
Expected: exits 0, no errors (two interfaces, nothing to fail on).

- [ ] **Step 7: Commit**

```bash
git add pnpm-workspace.yaml package.json packages/shared src/modules/types.ts .npmrc 2>/dev/null
git add -u src/modules
git commit -m "$(cat <<'EOF'
build: bootstrap pnpm workspace, extract packages/shared/types

FaceMetrics/TrackingFrame move to a shared package -- both are type-only
everywhere they're consumed, so this is safe in both the Node-context
main process and the bundler-less renderer (type-only imports erase at
compile time, never resolved at runtime).
EOF
)"
```

(`src/modules/types.ts`'s removal shows as staged via `git mv` already tracked by `git add -u`; the commit message reflects that consumers of it still point at the old path until Task 3 — this is fine, since nothing runs `tsc` against the old `src/modules` tree exclusively between now and Task 3 in this plan's sequencing. If running this plan interactively task-by-task, note `src/modules/gestures.ts`'s `import type { FaceMetrics } from "./types"` is now a dangling import until Task 3 fixes it — Task 3 starts immediately after, so this window is not independently shipped.)

---

### Task 3: `apps/desktop` skeleton + full `main/` move

This is the large task: `main/` is one cohesive compilation unit (bootstrap, services, windows, ipc all import each other), so it can't be split into independently-green sub-tasks without temporary shims that would just be thrown away. Every step below happens before the final "run full suite" verification at the end.

**Files:**
- Create: `apps/desktop/package.json`, `apps/desktop/tsconfig.json`, `apps/desktop/vitest.config.ts`, `apps/desktop/electron-builder.yml`, `apps/desktop/config.json.keep`
- Move: `assets/` → `apps/desktop/assets/`
- Move + edit: every file under `src/modules/` (see table below)
- Create: `apps/desktop/src/main/config/environment.ts`, `apps/desktop/src/main/ipc/{index,config.ipc,buttons.ipc}.ts`
- Move + edit: `tests/backendCommand.test.ts`, `tests/backendProcess.test.ts`, `tests/clickLog.test.ts`, `tests/config.test.ts`, `tests/gestures.test.ts`, `tests/mouseController.test.ts`, `tests/protocol.test.ts`, `tests/trayState.test.ts`, `tests/ipcRelay.test.ts` (renamed `relay.test.ts`)
- Create: `apps/desktop/tests/buttonsWindow.test.ts` (new coverage for the two functions extracted out of `buttonsWindow.ts`)

**Interfaces:**
- Consumes: `@facemesh-mouse/shared` (Task 2).
- Produces: `resolveBackendCommand(isPackaged, resourcesPath, appPath)`, `moveButtonsWindow(dx, dy)`, `endButtonsDrag()`, `wireIpc(backend)` — see "Interfaces carried across tasks" above.

- [ ] **Step 1: Move the old root package.json into apps/desktop, rescoped**

```bash
mkdir -p apps/desktop
git mv package.json apps/desktop/package.json
```

Wait — `package.json` at the root is now the *new* workspace-fan-out one from Task 2. Since Task 2 already replaced it, recover the pre-Task-2 content instead:

```bash
git show HEAD~1:package.json > apps/desktop/package.json
```

(`HEAD~1` is the Task 1 checkpoint commit — the last commit before Task 2's root `package.json` rewrite. If tasks are executed by different sessions/subagents, look up the actual pre-Task-2 commit hash with `git log --oneline -- package.json` instead of assuming `HEAD~1`.)

Edit `apps/desktop/package.json` to:
```json
{
  "name": "@facemesh-mouse/desktop",
  "version": "0.1.0",
  "private": true,
  "main": "dist/main/index.js",
  "scripts": {
    "build": "tsc -p tsconfig.json && node scripts/buildRenderer.mjs && node scripts/copyStaticAssets.mjs",
    "dev": "pnpm run build && electron .",
    "test": "vitest run",
    "dist": "pnpm run build && electron-builder --config electron-builder.yml"
  },
  "devDependencies": {
    "@types/node": "^22.10.0",
    "electron": "^33.2.0",
    "electron-builder": "^25.1.8",
    "typescript": "^5.7.2",
    "vitest": "^2.1.8"
  },
  "dependencies": {
    "@nut-tree-fork/nut-js": "^4.2.0",
    "koffi": "^3.1.5",
    "@facemesh-mouse/shared": "workspace:*"
  }
}
```

- [ ] **Step 2: Move tsconfig, vitest config, electron-builder config, static config placeholder**

```bash
git mv tsconfig.json apps/desktop/tsconfig.json
git mv tsconfig.renderer.json apps/desktop/tsconfig.renderer.json
git mv vitest.config.ts apps/desktop/vitest.config.ts
git mv electron-builder.yml apps/desktop/electron-builder.yml
git mv config.json.keep apps/desktop/config.json.keep
```

Edit `apps/desktop/tsconfig.json`'s `"include"`:
```json
"include": ["src/main", "src/preload"]
```

Edit `apps/desktop/tsconfig.renderer.json`'s `"include"`:
```json
"include": ["src/renderer/config", "src/renderer/buttons", "src/renderer/overlay", "src/renderer/tracking"]
```

`apps/desktop/vitest.config.ts` needs no content change — `include: ["tests/**/*.test.ts"]` is already relative to the package directory, which is exactly where it now lives.

Edit `apps/desktop/electron-builder.yml`'s icon path — it was `../assets/icon.ico`, written when this file sat inside a nested `electron/` folder (before the original flatten in Task 1 of the 19-task port plan). `assets/` is now a sibling of this file, not a parent:
```yaml
win:
  target: nsis
  icon: assets/icon.ico
```

- [ ] **Step 3: Move assets and scripts**

```bash
git mv assets apps/desktop/assets
git mv scripts apps/desktop/scripts
```

Edit `apps/desktop/scripts/buildRenderer.mjs` — change both `"src/ui"` references to `"src/renderer"`:
```js
import { existsSync, readdirSync } from "node:fs";
import { execFileSync } from "node:child_process";

function hasTypeScriptFiles(dir) {
  if (!existsSync(dir)) return false;
  for (const entry of readdirSync(dir, { withFileTypes: true, recursive: true })) {
    if (entry.isFile() && entry.name.endsWith(".ts")) return true;
  }
  return false;
}

if (hasTypeScriptFiles("src/renderer")) {
  execFileSync(process.execPath, ["node_modules/typescript/bin/tsc", "-p", "tsconfig.renderer.json"], {
    stdio: "inherit",
  });
} else {
  console.log("No renderer TypeScript files yet -- skipping tsconfig.renderer.json build.");
}
```

Edit `apps/desktop/scripts/copyStaticAssets.mjs` — change `"src/ui"`/`"dist/ui"` to `"src/renderer"`/`"dist/renderer"`:
```js
import { cpSync, existsSync } from "node:fs";

if (existsSync("src/renderer")) {
  cpSync("src/renderer", "dist/renderer", {
    recursive: true,
    filter: (source) => !source.endsWith(".ts"),
  });
}

if (existsSync("assets")) {
  cpSync("assets", "dist/assets", { recursive: true });
}
```

- [ ] **Step 4: Move services (pure relocations first)**

```bash
mkdir -p apps/desktop/src/main/services
git mv src/modules/backendProcess.ts apps/desktop/src/main/services/backendProcess.ts
git mv src/modules/protocol.ts apps/desktop/src/main/services/protocol.ts
git mv src/modules/win32.ts apps/desktop/src/main/services/win32.service.ts
git mv src/modules/trayState.ts apps/desktop/src/main/services/trayState.ts
```

`backendProcess.ts` and `protocol.ts` keep their current names (not `*.service.ts`): both are slated for outright deletion once Task 10-12 of the 19-task port plan lands `engine.service.ts`/`backendServer` equivalents and the stdio child-process plumbing goes away. Renaming code that's about to be deleted is pure churn (see the electron-node-architecture skill's refactoring-discipline guidance: don't mass-rename to match a convention with no correctness payoff).

`backendProcess.ts` imports `from "./protocol"` — already correct, both are siblings in the new `services/` folder, no edit needed.

- [ ] **Step 5: Move and edit config.service.ts, clickLog.service.ts, gestures.service.ts, mouseController.service.ts**

```bash
git mv src/modules/config.ts apps/desktop/src/main/services/config.service.ts
git mv src/modules/clickLog.ts apps/desktop/src/main/services/clickLog.service.ts
git mv src/modules/gestures.ts apps/desktop/src/main/services/gestures.service.ts
git mv src/modules/mouseController.ts apps/desktop/src/main/services/mouseController.service.ts
```

In `apps/desktop/src/main/services/clickLog.service.ts`, change the one import:
```ts
import { foregroundWindowTitle } from "./win32.service";
```

In `apps/desktop/src/main/services/gestures.service.ts`, change both imports:
```ts
import type { AppConfig } from "./config.service";
import type { FaceMetrics } from "@facemesh-mouse/shared";
```

In `apps/desktop/src/main/services/mouseController.service.ts`, change the one import:
```ts
import type { AppConfig } from "./config.service";
```

`config.service.ts` needs no import edits (it declares `GESTURE_NAMES`/`GestureName` locally, unchanged — see the Global Constraints note on why this stays duplicated with `labels.ts` rather than moving to `packages/shared`).

- [ ] **Step 6: Move and edit tray.service.ts**

```bash
git mv src/modules/tray.ts apps/desktop/src/main/services/tray.service.ts
```

Edit the import and both `path.join` calls — the compiled file moves from `dist/modules/tray.js` (one level under `dist/`) to `dist/main/services/tray.service.js` (two levels under `dist/`), so every `__dirname`-relative hop to `dist/assets/` needs one more `".."`:

```ts
import { app, globalShortcut, Menu, nativeImage, Tray } from "electron";
import path from "node:path";
import { BackendProcess } from "./backendProcess";
import { computeTrayState, TrayStatus } from "./trayState";
import { showConfigWindow } from "../windows/configWindow";

const ICON_FILES: Record<string, string> = {
  running: "tray-running.png",
  paused: "tray-paused.png",
  no_face: "tray-no-face.png",
  yielded: "tray-yielded.png",
};

let tray: Tray | null = null;
let lastStatus: TrayStatus = { control_enabled: false, paused: false, no_face: false, yielded: false };

export function createTray(backend: BackendProcess): Tray {
  const iconPath = path.join(__dirname, "..", "..", "assets", ICON_FILES.running);
  tray = new Tray(nativeImage.createFromPath(iconPath));
  tray.setToolTip("FaceMesh Mouse");

  function togglePause(): void {
    backend.send({ type: lastStatus.paused ? "resume" : "pause" });
  }

  const menu = Menu.buildFromTemplate([
    { label: "Pausar/Retomar", click: togglePause },
    { label: "Reabrir Config", click: showConfigWindow },
    { label: "Sair", click: () => app.quit() },
  ]);
  tray.setContextMenu(menu);
  tray.on("click", showConfigWindow);

  backend.on("message", (message: { type: string }) => {
    if (message.type !== "status") return;
    lastStatus = message as unknown as TrayStatus;
    const state = computeTrayState(lastStatus);
    tray?.setImage(nativeImage.createFromPath(path.join(__dirname, "..", "..", "assets", ICON_FILES[state.icon])));
    tray?.setToolTip(state.title);
  });

  globalShortcut.register("Ctrl+Alt+P", togglePause);
  globalShortcut.register("Ctrl+Alt+O", showConfigWindow);

  return tray;
}
```

- [ ] **Step 7: Move and fix backendCommand.ts (signature change)**

```bash
git mv src/modules/backendCommand.ts apps/desktop/src/main/services/backendCommand.ts
```

Replace its content entirely — the dev-mode `run.py` lookup was computed from this module's own `__dirname`, hand-counting `".."` segments; that count silently went stale once already (the comment referenced a `dist/main` depth and an `electron/` folder that hadn't existed since the original flatten) and would go stale again the moment this file moves one folder deeper (`modules/` → `main/services/`). Fix it by taking the app's own root directory as a parameter instead of re-deriving it from this file's compiled location:

```ts
import path from "node:path";

export function resolveBackendCommand(
  isPackaged: boolean,
  resourcesPath: string,
  appPath: string
): { command: string; args: string[] } {
  if (isPackaged) {
    return {
      command: path.join(resourcesPath, "backend", "facemesh-mouse-backend.exe"),
      args: [],
    };
  }
  // Not `python -m facemesh_mouse.backend`: the package lives under src/
  // and the project has no build-system/[project] table in pyproject.toml,
  // so it is not importable from any working directory. run.py does its own
  // sys.path.insert relative to its own __file__, so it works regardless of
  // cwd.
  //
  // appPath (Electron's app.getAppPath(), the directory containing
  // apps/desktop/package.json) is two levels below the repo root
  // (apps/desktop -> apps -> repo root) -- passed in rather than derived
  // from this module's own __dirname, so this stays correct regardless of
  // how deep this file sits inside dist/ once compiled.
  return {
    command: "python",
    args: [path.join(appPath, "..", "..", "run.py")],
  };
}
```

- [ ] **Step 8: Update backendCommand's test for the new signature**

```bash
git mv tests/backendCommand.test.ts apps/desktop/tests/backendCommand.test.ts
```

Replace its content:
```ts
import { describe, expect, it } from "vitest";
import path from "node:path";
import { resolveBackendCommand } from "../src/main/services/backendCommand";

describe("resolveBackendCommand", () => {
  it("uses the bundled exe when packaged", () => {
    const result = resolveBackendCommand(true, "C:/App/resources", "C:/App/resources/app");
    expect(result).toEqual({
      command: path.join("C:/App/resources", "backend", "facemesh-mouse-backend.exe"),
      args: [],
    });
  });

  it("spawns run.py two directories above the app's own directory", () => {
    const result = resolveBackendCommand(false, "", "C:/repo/apps/desktop");
    expect(result).toEqual({
      command: "python",
      args: [path.join("C:/repo/apps/desktop", "..", "..", "run.py")],
    });
  });
});
```

- [ ] **Step 9: Move the remaining service tests**

```bash
git mv tests/backendProcess.test.ts apps/desktop/tests/backendProcess.test.ts
git mv tests/clickLog.test.ts apps/desktop/tests/clickLog.test.ts
git mv tests/config.test.ts apps/desktop/tests/config.test.ts
git mv tests/gestures.test.ts apps/desktop/tests/gestures.test.ts
git mv tests/mouseController.test.ts apps/desktop/tests/mouseController.test.ts
git mv tests/protocol.test.ts apps/desktop/tests/protocol.test.ts
git mv tests/trayState.test.ts apps/desktop/tests/trayState.test.ts
```

In each moved test file, update import paths (mechanical string substitution — `../src/modules/X` becomes the file's new location):

- `backendProcess.test.ts`: `"../src/main/services/backendProcess"`
- `clickLog.test.ts`: `"../src/main/services/clickLog.service"` (and if it imports `win32` for mocking, `"../src/main/services/win32.service"`)
- `config.test.ts`: `"../src/main/services/config.service"`
- `gestures.test.ts`:
  ```ts
  import { GestureEngine, triggerProgress } from "../src/main/services/gestures.service";
  import type { AppConfig, GestureConfig } from "../src/main/services/config.service";
  import type { FaceMetrics } from "@facemesh-mouse/shared";
  ```
- `mouseController.test.ts`:
  ```ts
  import { accelerate, clamp } from "../src/main/services/mouseController.service";
  // ... and further down ...
  import { MouseController, type MouseDriver } from "../src/main/services/mouseController.service";
  import type { AppConfig, CalibrationConfig } from "../src/main/services/config.service";
  ```
- `protocol.test.ts`: `"../src/main/services/protocol"`
- `trayState.test.ts`: `"../src/main/services/trayState"`

- [ ] **Step 10: Move buttonsPosition.ts and overlayWindow.ts (pure relocations)**

```bash
mkdir -p apps/desktop/src/main/windows
git mv src/modules/windows/buttonsPosition.ts apps/desktop/src/main/windows/buttonsPosition.ts
git mv src/modules/windows/overlayWindow.ts apps/desktop/src/main/windows/overlayWindow.ts
```

Edit `apps/desktop/src/main/windows/overlayWindow.ts`'s two `path.join` calls — depth is unchanged (`modules/windows/` and `main/windows/` are both two levels under `dist/`), only the target folder names change:

```ts
webPreferences: {
  preload: path.join(__dirname, "..", "..", "preload", "index.js"),
  contextIsolation: true,
  nodeIntegration: false,
},
```
and
```ts
win.loadFile(path.join(__dirname, "..", "..", "renderer", "overlay", "index.html"));
```

- [ ] **Step 11: Move and split configWindow.ts**

```bash
git mv src/modules/windows/configWindow.ts apps/desktop/src/main/windows/configWindow.ts
```

Replace its content — drops the `ipcMain.on("config:reset-position", ...)` registration (moves to `ipc/config.ipc.ts` in Step 14) and the now-unneeded `ipcMain` import, fixes the preload/renderer path split, keeps the before-quit rationale comment:

```ts
import { app, BrowserWindow } from "electron";
import path from "node:path";
import { BackendProcess } from "../services/backendProcess";

let win: BrowserWindow | null = null;

// The close handler below cancels every close so the X button only hides
// the window (the app lives in the tray). That would also cancel the
// closes app.quit() issues, leaving a zombie app with a dead backend, so
// track quitting here. Listening to before-quit ourselves -- rather than
// importing a flag from index.ts -- keeps the dependency one-way:
// index.ts already imports from this module.
let isQuitting = false;
app.on("before-quit", () => {
  isQuitting = true;
});

export function createConfigWindow(backend: BackendProcess): BrowserWindow {
  win = new BrowserWindow({
    width: 1060,
    height: 680,
    minWidth: 1000,
    minHeight: 620,
    title: "FaceMesh Mouse",
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "..", "..", "preload", "index.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  win.loadFile(path.join(__dirname, "..", "..", "renderer", "config", "index.html"));
  win.on("show", () => backend.send({ type: "set_preview", enabled: true }));
  win.on("hide", () => backend.send({ type: "set_preview", enabled: false }));
  win.on("close", (event) => {
    if (isQuitting) return;
    event.preventDefault();
    win?.hide();
  });
  return win;
}

export function showConfigWindow(): void {
  win?.show();
  win?.focus();
}
```

- [ ] **Step 12: Move and split buttonsWindow.ts**

```bash
git mv src/modules/windows/buttonsWindow.ts apps/desktop/src/main/windows/buttonsWindow.ts
```

Replace its content — the two `ipcMain.on(...)` bodies become exported functions (`moveButtonsWindow`, `endButtonsDrag`) that `ipc/buttons.ipc.ts` calls into (Step 15), which requires capturing `backend` at module scope the same way `configWindow.ts` doesn't need to (it never used `backend` outside `createConfigWindow`'s own closures) but `buttonsWindow.ts` does, since `endButtonsDrag` needs it outside `createButtonsWindow`'s original closure:

```ts
import { BrowserWindow, screen } from "electron";
import path from "node:path";
import { BackendProcess } from "../services/backendProcess";
import { defaultPosition, resolvePosition, WIDTH, SIZE } from "./buttonsPosition";

let win: BrowserWindow | null = null;
let backendRef: BackendProcess | null = null;

export function createButtonsWindow(
  backend: BackendProcess,
  savedX: number | null,
  savedY: number | null
): BrowserWindow {
  backendRef = backend;
  // bounds, not workArea: defaultPosition/resolvePosition subtract the
  // taskbar themselves, so feeding them the already-shrunk workArea height
  // would place the buttons one taskbar-height too high.
  const { width: screenW, height: screenH } = screen.getPrimaryDisplay().bounds;
  const taskbarReservedPx = screenH - screen.getPrimaryDisplay().workArea.height;
  const { x, y } = resolvePosition(savedX, savedY, screenW, screenH, taskbarReservedPx);

  win = new BrowserWindow({
    x: Math.round(x),
    y: Math.round(y),
    width: WIDTH,
    height: SIZE,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    skipTaskbar: true,
    resizable: false,
    focusable: false,
    webPreferences: {
      preload: path.join(__dirname, "..", "..", "preload", "index.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  win.loadFile(path.join(__dirname, "..", "..", "renderer", "buttons", "index.html"));
  win.showInactive();

  return win;
}

// Was an inline ipcMain.on("buttons:drag-move", ...) listener in this file;
// now called from ipc/buttons.ipc.ts so window ownership (this file) and
// IPC routing (ipc/) stay separate, per the main/{windows,ipc} split.
export function moveButtonsWindow(dx: number, dy: number): void {
  if (!win) return;
  const [curX, curY] = win.getPosition();
  win.setPosition(curX + dx, curY + dy);
}

// Was an inline ipcMain.on("buttons:drag-end", ...) listener; now called
// from ipc/buttons.ipc.ts.
export function endButtonsDrag(): void {
  if (!win || !backendRef) return;
  const [curX, curY] = win.getPosition();
  backendRef.send({
    type: "save_config",
    config: { action_buttons: { x: curX, y: curY } },
  });
}

export function resetButtonsPosition(): void {
  // bounds, not workArea: see createButtonsWindow above.
  const { width: screenW, height: screenH } = screen.getPrimaryDisplay().bounds;
  const taskbarReservedPx = screenH - screen.getPrimaryDisplay().workArea.height;
  const { x, y } = defaultPosition(screenW, screenH, taskbarReservedPx);
  win?.setPosition(Math.round(x), Math.round(y));
}
```

- [ ] **Step 13: Move position.test.ts's buttonsPosition half (its clickOrDrag half moves in Task 4)**

`tests/position.test.ts` imports from both `src/ui/buttons/clickOrDrag` (renderer, moves in Task 4) and `src/modules/windows/buttonsPosition` (main, moving now). Leave this file at the repo-root `tests/` for now and finish it in Task 4 once both halves have a home — moving it now would require re-touching it again in Task 4 for the other half. Skip this step's file move; note it for Task 4.

- [ ] **Step 14: Create ipc/relay.ts**

```bash
mkdir -p apps/desktop/src/main/ipc
git mv src/modules/ipcRelay.ts apps/desktop/src/main/ipc/relay.ts
```

Edit the import path and the comment (the window modules it refers to no longer own these listeners themselves — `ipc/config.ipc.ts`/`ipc/buttons.ipc.ts` do):

```ts
import { BrowserWindow, ipcMain } from "electron";
import { BackendProcess } from "../services/backendProcess";

export function wireBackendRelay(backend: BackendProcess): void {
  backend.on("message", (message: { type: string }) => {
    for (const win of BrowserWindow.getAllWindows()) {
      win.webContents.send(`backend:${message.type}`, message);
    }
  });
  ipcMain.on("backend:send", (_event, message: { type: string }) => {
    if (message.type.includes(":")) {
      // Namespaced types (config:*, buttons:*) are main-process-only --
      // re-emit on ipcMain itself so the ipc/*.ipc.ts module that owns
      // that namespace can listen for it directly, instead of every
      // listener filtering the shared channel.
      ipcMain.emit(message.type, undefined, message);
      return;
    }
    backend.send(message);
  });
}
```

Behavior is unchanged from the pre-move version, including the known `ipcMain.emit` fragility with a synthetic second argument — fixing that is out of scope for this move (see the plan's Global Constraints: this is a structural relocation, not a bug-fix pass). Note it as a follow-up: `electron/src/main/ipcRelay.ts` on `master` already has a fix for this (an `EventEmitter`-based `mainRelay` instead of reusing `ipcMain.emit`) that this branch predates and does not yet carry.

- [ ] **Step 15: Create ipc/config.ipc.ts and ipc/buttons.ipc.ts**

`apps/desktop/src/main/ipc/config.ipc.ts`:
```ts
import { ipcMain } from "electron";
import { resetButtonsPosition } from "../windows/buttonsWindow";

export function registerConfigIpc(): void {
  ipcMain.on("config:reset-position", () => {
    resetButtonsPosition();
  });
}
```

`apps/desktop/src/main/ipc/buttons.ipc.ts`:
```ts
import { ipcMain } from "electron";
import { moveButtonsWindow, endButtonsDrag } from "../windows/buttonsWindow";

// These two channels are re-emitted by ipc/relay.ts's wireBackendRelay
// rather than delivered on the shared "backend:send" channel directly -- a
// raw listener there would also see every command meant for Python (start,
// update_config, ...) and would need to filter them back out itself.
export function registerButtonsIpc(): void {
  ipcMain.on("buttons:drag-move", (_event, message: { dx: number; dy: number }) => {
    moveButtonsWindow(message.dx, message.dy);
  });
  ipcMain.on("buttons:drag-end", () => {
    endButtonsDrag();
  });
}
```

- [ ] **Step 16: Create ipc/index.ts**

```ts
import { BackendProcess } from "../services/backendProcess";
import { wireBackendRelay } from "./relay";
import { registerConfigIpc } from "./config.ipc";
import { registerButtonsIpc } from "./buttons.ipc";

export function wireIpc(backend: BackendProcess): void {
  wireBackendRelay(backend);
  registerConfigIpc();
  registerButtonsIpc();
}
```

- [ ] **Step 17: Rename and update the relay test**

```bash
git mv tests/ipcRelay.test.ts apps/desktop/tests/relay.test.ts
```

Update the import inside it: `"../src/main/ipc/relay"` (mock target and `vi.mock` paths unchanged otherwise — the test only mocks `"electron"`, which stays a bare specifier).

- [ ] **Step 18: Add coverage for the two functions extracted out of buttonsWindow.ts**

These were previously only exercised indirectly through inline `ipcMain.on` closures with no dedicated test. Extracting them into standalone exports is the moment to cover them directly:

`apps/desktop/tests/buttonsWindow.test.ts`:
```ts
import { describe, expect, it, vi, beforeEach } from "vitest";

class FakeBrowserWindow {
  static instances: FakeBrowserWindow[] = [];
  on = vi.fn();
  loadFile = vi.fn();
  showInactive = vi.fn();
  getPosition = vi.fn(() => [100, 200]);
  setPosition = vi.fn();

  constructor() {
    FakeBrowserWindow.instances.push(this);
  }
}

vi.mock("electron", () => ({
  BrowserWindow: FakeBrowserWindow,
  screen: {
    getPrimaryDisplay: () => ({
      bounds: { width: 1920, height: 1080 },
      workArea: { height: 1040 },
    }),
  },
}));

describe("buttonsWindow", () => {
  beforeEach(() => {
    vi.resetModules();
    FakeBrowserWindow.instances = [];
  });

  it("moveButtonsWindow adds the delta to the current position", async () => {
    const { createButtonsWindow, moveButtonsWindow } = await import("../src/main/windows/buttonsWindow");
    createButtonsWindow({ send: vi.fn() } as never, null, null);

    moveButtonsWindow(5, -3);

    expect(FakeBrowserWindow.instances[0].setPosition).toHaveBeenCalledWith(105, 197);
  });

  it("endButtonsDrag saves the current position through the backend", async () => {
    const send = vi.fn();
    const { createButtonsWindow, endButtonsDrag } = await import("../src/main/windows/buttonsWindow");
    createButtonsWindow({ send } as never, null, null);

    endButtonsDrag();

    expect(send).toHaveBeenCalledWith({
      type: "save_config",
      config: { action_buttons: { x: 100, y: 200 } },
    });
  });
});
```

This does not include a NaN-guard regression test on `moveButtonsWindow` — the pre-move code never guarded against a non-finite delta either (that guard exists only on `master`'s post-migration version, out of scope here per the Global Constraints note in Step 14).

- [ ] **Step 19: Create config/environment.ts**

```ts
import { app } from "electron";

// App-level runtime config, distinct from services/config.service.ts's
// user-facing calibration/gesture config persistence.
export const isPackaged = app.isPackaged;
export const resourcesPath = process.resourcesPath;
// The directory containing this package's package.json (apps/desktop in
// dev, the packaged app's resources root once packaged) -- used by
// backendCommand.ts to find the repo-root run.py in dev mode. See that
// module for why this replaced a __dirname-relative computation.
export const appPath = app.getAppPath();
export const CONFIG_PATH = "config.json";
```

- [ ] **Step 20: Move and update index.ts**

```bash
git mv src/modules/index.ts apps/desktop/src/main/index.ts
```

Replace its content:
```ts
import { app, dialog, globalShortcut } from "electron";
import fs from "node:fs";
import { BackendProcess } from "./services/backendProcess";
import { resolveBackendCommand } from "./services/backendCommand";
import { wireIpc } from "./ipc";
import { createTray } from "./services/tray.service";
import { isPackaged, resourcesPath, appPath, CONFIG_PATH } from "./config/environment";
import { createConfigWindow, showConfigWindow } from "./windows/configWindow";
import { createOverlayWindow } from "./windows/overlayWindow";
import { createButtonsWindow, resetButtonsPosition } from "./windows/buttonsWindow";

function readSavedButtonsPosition(): { x: number | null; y: number | null } {
  try {
    const raw = JSON.parse(fs.readFileSync(CONFIG_PATH, "utf-8"));
    return { x: raw.action_buttons?.x ?? null, y: raw.action_buttons?.y ?? null };
  } catch {
    return { x: null, y: null };
  }
}

export let backend: BackendProcess;
let quitting = false;

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  // app.quit() is async, so everything below has to sit in the else
  // branch -- otherwise the losing instance would still spawn its own
  // backend and windows before the quit lands.
  app.quit();
} else {
  // Relaunching while a copy is already running reopens the config
  // window instead of starting a second app, replacing the old
  // single_instance.py behaviour.
  app.on("second-instance", () => {
    showConfigWindow();
  });

  app.whenReady().then(() => {
    const { command, args } = resolveBackendCommand(isPackaged, resourcesPath, appPath);
    backend = new BackendProcess(command, args);

    backend.on("message", (message: { type: string; message?: string }) => {
      if (message.type !== "error") return;
      // Today's only real error case: the camera failed to open. The
      // backend sends this once, at startup, then returns without ever
      // starting its push loops -- there is nothing left running to
      // recover, so this is fatal.
      dialog.showErrorBox(
        "FaceMesh Mouse",
        "Não foi possível acessar a webcam. Verifique se ela está conectada e se " +
          "a permissão de câmera do Windows está ativa."
      );
      app.quit();
    });

    backend.on("exit", (code) => {
      if (quitting || code === 0) return;
      // The backend died mid-session (not from our own before-quit) --
      // this failure mode doesn't exist in the old Tkinter app, where
      // engine and UI shared one process and a crash took both down
      // together silently. Here the window would otherwise sit frozen
      // with a dead backend behind it, so ask instead.
      const choice = dialog.showMessageBoxSync({
        type: "error",
        message: "FaceMesh Mouse",
        detail: `O processo de rastreamento parou inesperadamente (código ${code}).`,
        buttons: ["Reiniciar", "Sair"],
        defaultId: 0,
      });
      if (choice === 0) {
        backend.start();
      } else {
        app.quit();
      }
    });

    backend.on("log", (text: string) => console.error(`[backend] ${text}`));
    backend.start();
    wireIpc(backend);
    createConfigWindow(backend);
    createOverlayWindow();
    const saved = readSavedButtonsPosition();
    createButtonsWindow(backend, saved.x, saved.y);
    createTray(backend);

    // Same launch behaviour as the old Tkinter main.py: a first run (no
    // config.json yet) opens the config window and stays stopped, while
    // every later run starts control right away with no window shown.
    if (fs.existsSync(CONFIG_PATH)) {
      backend.send({ type: "start" });
    } else {
      showConfigWindow();
    }
  });
}

export { showConfigWindow, resetButtonsPosition };

app.on("before-quit", () => {
  quitting = true;
  backend?.send({ type: "stop" });
  backend?.stop();
});

app.on("will-quit", () => {
  globalShortcut.unregisterAll();
});

app.on("window-all-closed", () => {
  // Intentionally does not quit -- the app lives in the tray with no
  // window open most of the time, same as today's Tkinter app.
});
```

- [ ] **Step 21: Remove the now-empty src/modules directory**

```bash
rmdir src/modules 2>/dev/null || rm -rf src/modules
```

(Should already be empty — every file under it moved in Steps 4-20. If it isn't empty, something was missed; check `find src/modules -type f` before forcing removal.)

- [ ] **Step 22: Run the full apps/desktop test suite and typecheck**

Run: `pnpm --filter @facemesh-mouse/desktop test`
Expected: every test passes, including the new `buttonsWindow.test.ts` and the updated `relay.test.ts`/`backendCommand.test.ts`.

Run: `pnpm --filter @facemesh-mouse/desktop exec tsc --noEmit -p tsconfig.json`
Expected: no errors. (The renderer half of `tsconfig.renderer.json` isn't checked yet — `src/renderer` doesn't exist until Task 4 — skip that check here.)

- [ ] **Step 23: Commit**

```bash
git add -A apps/desktop packages/shared src/modules pnpm-workspace.yaml package.json tests
git commit -m "$(cat <<'EOF'
refactor: move main/ into apps/desktop, split ipc listeners out of windows/

src/modules -> apps/desktop/src/main/{services,windows,ipc,config}, per
the monorepo layout spec. ipcMain.on registrations that used to live
inline in configWindow.ts/buttonsWindow.ts move into new
ipc/{config,buttons}.ipc.ts files, calling back into the window modules
through new exported functions (moveButtonsWindow, endButtonsDrag,
resetButtonsPosition). backendCommand.ts's dev-mode run.py lookup now
takes the app's root directory as a parameter instead of re-deriving it
from its own __dirname, fixing a path-depth bug this move would have
made worse. Renderer half (src/ui -> apps/desktop/src/renderer) is
next.
EOF
)"
```

---

### Task 4: `preload/` + `renderer/` move

**Files:**
- Move: `src/ui/preload/index.ts` → `apps/desktop/src/preload/index.ts`
- Move: `src/ui/{buttons,config,overlay,tracking}/*` → `apps/desktop/src/renderer/{buttons,config,overlay,tracking}/*`
- Move + edit: `tests/position.test.ts`, `tests/faceMetrics.test.ts`, `tests/pulse.test.ts`, `tests/toggleState.test.ts`
- Delete: `src/ui/` (now empty), `src/` (now empty)

**Interfaces:**
- Consumes: `@facemesh-mouse/shared`'s `FaceMetrics` type (Task 2), `apps/desktop/tsconfig.renderer.json`'s updated `include` (Task 3 Step 2).

- [ ] **Step 1: Move preload (pure relocation, no content change)**

```bash
mkdir -p apps/desktop/src/preload
git mv src/ui/preload/index.ts apps/desktop/src/preload/index.ts
```

- [ ] **Step 2: Move the buttons, config, overlay renderer folders (pure relocations)**

```bash
mkdir -p apps/desktop/src/renderer
git mv src/ui/buttons apps/desktop/src/renderer/buttons
git mv src/ui/config apps/desktop/src/renderer/config
git mv src/ui/overlay apps/desktop/src/renderer/overlay
```

No content edits needed inside these — every import inside them is relative to siblings in the same folder (`"./clickOrDrag.js"`, `"./labels.js"`, `"./pulse.js"`, `"./toggleState.js"`), which the move preserves exactly.

- [ ] **Step 3: Move tracking, fix its shared-types import**

```bash
mkdir -p apps/desktop/src/renderer/tracking
git mv src/ui/tracking/faceMetrics.ts apps/desktop/src/renderer/tracking/faceMetrics.ts
```

Edit the one import (type-only, safe as a bare specifier in both this file's real usage and its test's Node-based vitest run):
```ts
import type { FaceMetrics as SharedFaceMetrics } from "@facemesh-mouse/shared";
```

- [ ] **Step 4: Finish moving position.test.ts (both halves now have a home)**

```bash
git mv tests/position.test.ts apps/desktop/tests/position.test.ts
```

Update its two import lines:
```ts
import { CLICK_DRAG_THRESHOLD_PX, isClick } from "../src/renderer/buttons/clickOrDrag";
import { WIDTH, SIZE, MARGIN, defaultPosition, resolvePosition } from "../src/main/windows/buttonsPosition";
```

- [ ] **Step 5: Move the remaining renderer tests**

```bash
git mv tests/faceMetrics.test.ts apps/desktop/tests/faceMetrics.test.ts
git mv tests/pulse.test.ts apps/desktop/tests/pulse.test.ts
git mv tests/toggleState.test.ts apps/desktop/tests/toggleState.test.ts
```

Update imports:
- `faceMetrics.test.ts`: `"../src/renderer/tracking/faceMetrics"`
- `pulse.test.ts`: `"../src/renderer/overlay/pulse"`
- `toggleState.test.ts`: `"../src/renderer/config/toggleState"`

- [ ] **Step 6: Remove the now-empty src/ui and src directories**

```bash
rmdir src/ui 2>/dev/null || rm -rf src/ui
rmdir src 2>/dev/null || rm -rf src
```

(`src/` at repo root should now contain only `facemesh_mouse/` (Python) after this — confirm with `ls src/` before removing anything forcefully; if `src/ui`/`src` aren't empty, something didn't move.)

- [ ] **Step 7: Full build + test verification**

Run: `pnpm --filter @facemesh-mouse/desktop test`
Expected: all tests pass, including the four just-moved renderer tests.

Run: `pnpm --filter @facemesh-mouse/desktop exec tsc --noEmit -p tsconfig.json`
Expected: no errors.

Run: `pnpm --filter @facemesh-mouse/desktop exec tsc --noEmit -p tsconfig.renderer.json`
Expected: no errors.

Run: `pnpm --filter @facemesh-mouse/desktop build`
Expected: succeeds; `apps/desktop/dist/main/index.js`, `apps/desktop/dist/preload/index.js`, `apps/desktop/dist/renderer/{buttons,config,overlay,tracking}/index.js`, and `apps/desktop/dist/assets/*.png` all exist afterward.

Verify: `ls apps/desktop/dist/main apps/desktop/dist/preload apps/desktop/dist/renderer apps/desktop/dist/assets`

- [ ] **Step 8: Commit**

```bash
git add -A apps/desktop src tests
git commit -m "$(cat <<'EOF'
refactor: move preload/renderer into apps/desktop, complete the monorepo move

src/ui -> apps/desktop/src/{preload,renderer}. faceMetrics.ts's FaceMetrics
import now comes from @facemesh-mouse/shared (type-only, safe under the
renderer's no-bundler <script type="module"> loading). src/ and src/ui/
are gone -- only src/facemesh_mouse/ (Python, untouched) remains under
the repo-root src/.
EOF
)"
```

---

### Task 5: Cleanup, README, and the 19-task plan's path references

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/plans/2026-08-17-node-port.md` (path references in Tasks 9-19 only — Tasks 1-8 are already-completed history and don't need editing)
- Modify: `docs/superpowers/specs/2026-08-18-node-port-monorepo-layout-design.md` (correct the `packages/shared` scope to match what Task 2 actually built)

- [ ] **Step 1: Verify nothing still points at the old paths**

Run: `grep -rn "src/modules\|src/ui/" apps/desktop packages docs/superpowers/specs/2026-08-18-node-port-monorepo-layout-design.md 2>/dev/null`
Expected: no matches in source/config files (the spec file's own historical prose describing what things "were" is fine and expected — check the grep output by hand, don't just require zero total hits).

- [ ] **Step 2: Update README's dev instructions**

Find any `npm install` / `npm run dev` / `npm run build` instructions in `README.md` referring to running commands from a nested `electron/` directory or the old flat root, and update them to the pnpm-workspace equivalents:

```bash
pnpm install
pnpm dev      # equivalent to: pnpm --filter @facemesh-mouse/desktop dev
pnpm test     # equivalent to: pnpm -r test
pnpm build    # equivalent to: pnpm --filter @facemesh-mouse/desktop build
```

(Exact wording depends on what's currently in the README — read it first, edit only the command examples and any file-path references that changed, don't rewrite unrelated sections.)

- [ ] **Step 3: Correct the monorepo-layout spec's packages/shared section**

In `docs/superpowers/specs/2026-08-18-node-port-monorepo-layout-design.md`, under "What moves into `packages/shared`", replace the `constants/gestures.ts` bullet and its rationale with a note matching what Task 2/3 actually built:

```markdown
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
```

Also update the "Tooling" section's "Each workspace package owns its own `package.json`, `vitest.config.ts`, and tests" line — `packages/shared` has no `vitest.config.ts` (nothing to runtime-test in two pure interfaces); it has a `typecheck` script instead. Adjust the sentence to: "Each workspace package owns its own `package.json`. `apps/desktop` also owns `vitest.config.ts` and `tests/`; `packages/shared` owns a `tsconfig.json` and a `typecheck` script, since it currently holds only type-only exports with nothing to runtime-test."

- [ ] **Step 4: Mechanical path-substitution pass over the 19-task plan's remaining tasks**

`docs/superpowers/plans/2026-08-17-node-port.md`'s Tasks 1-8 describe already-completed work — leave them untouched as historical record. In Tasks 9 (its not-yet-done remainder) through 19, replace path references so future execution targets the new layout:

| Old path pattern | New path pattern |
|---|---|
| `src/modules/mouseController.ts` | `apps/desktop/src/main/services/mouseController.service.ts` |
| `src/modules/engine.ts` | `apps/desktop/src/main/services/engine.service.ts` |
| `src/modules/backendServer.ts` | `apps/desktop/src/main/services/backendServer.ts` (or fold into `engine.service.ts` — Task 11's call) |
| `src/modules/trackingEngine.ts` | `apps/desktop/src/main/services/trackingEngine.service.ts` |
| `src/modules/windows/trackingWindow.ts` | `apps/desktop/src/main/windows/trackingWindow.ts` |
| `src/ui/tracking/pointTracker.ts` | `apps/desktop/src/renderer/tracking/pointTracker.ts` |
| `src/modules/index.ts` | `apps/desktop/src/main/index.ts` |
| `tests/*.test.ts` | `apps/desktop/tests/*.test.ts` |
| any bare `electron-builder.yml`/`package.json`/`scripts/` reference | prefixed with `apps/desktop/` |

Read through Tasks 9 (remaining steps)-19 and apply this table by hand — don't blind-`sed` the whole file, since some prose (e.g. historical "was `electron/src/main/...`" notes) should stay as-is.

- [ ] **Step 5: Final full-workspace verification**

Run: `pnpm -r typecheck` (packages/shared) — Expected: passes.
Run: `pnpm --filter @facemesh-mouse/desktop test` — Expected: all pass.
Run: `pnpm --filter @facemesh-mouse/desktop exec tsc --noEmit -p tsconfig.json` — Expected: no errors.
Run: `pnpm --filter @facemesh-mouse/desktop exec tsc --noEmit -p tsconfig.renderer.json` — Expected: no errors.
Run: `pnpm --filter @facemesh-mouse/desktop build` — Expected: succeeds.

- [ ] **Step 6: Commit**

```bash
git add -A README.md docs/superpowers/plans/2026-08-17-node-port.md docs/superpowers/specs/2026-08-18-node-port-monorepo-layout-design.md
git commit -m "$(cat <<'EOF'
docs: update README dev instructions and 19-task plan paths for the monorepo move

Corrects the monorepo-layout spec's packages/shared section to match
what was actually built (types only, not GESTURE_NAMES -- see that
section for why). Tasks 9 (remainder)-19 of the node-port plan now
reference apps/desktop paths; Tasks 1-8 stay as historical record of
already-completed work against the old flat layout.
EOF
)"
```

---

## Self-Review

**Spec coverage:** Every section of `2026-08-18-node-port-monorepo-layout-design.md` maps to a task — top-level layout (Task 3-4), `main/` reorg incl. the `ipc/` split rationale (Task 3), `preload`/`renderer` (Task 4), `packages/shared` (Task 2, with a scope correction written back into the spec in Task 5 Step 3), tooling/pnpm (Task 2), migration mechanics (Task 1 checkpoint, Tasks 3-4 as the path-rewrite pass, Task 5 for the 19-task plan's path update). No section without a task.

**Placeholder scan:** No TBD/TODO. `packages/shared/src/types/` has real, complete content (not a stub). `main/config/environment.ts` has real content (three real values plus a real constant), not an empty placeholder. Task 5 Step 4's substitution table is filled with real, computed paths — the instruction to "apply by hand" is standard for a docs-editing step where blind automation would corrupt prose, not a placeholder for missing content.

**Type consistency:** `resolveBackendCommand`'s three-parameter signature is identical everywhere it's declared (Task 3 Step 7) and called (Task 3 Step 20's `index.ts`, Task 3 Step 8's test). `moveButtonsWindow(dx: number, dy: number)` / `endButtonsDrag()` match between their definition (Step 12) and both consumers (`ipc/buttons.ipc.ts` in Step 15, the new test in Step 18). `wireIpc(backend: BackendProcess)` matches between its definition (Step 16) and its one call site (Step 20).
