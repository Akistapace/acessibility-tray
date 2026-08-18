---
name: electron-node-architecture
description: Enforces Electron Main/Preload/Renderer runtime boundaries and (when present) Node backend layering. Use whenever writing, reviewing, or refactoring code in an electron/ directory (main, preload, renderer), IPC handlers, or a Node/HTTP backend paired with an Electron app — even if the request doesn't mention "architecture" explicitly. Also applies to apps where the "backend" is an external process (e.g. Python) talked to over stdio/IPC instead of HTTP. Triggers on: adding an IPC channel, exposing a preload API, importing fs/child_process/electron in renderer code, adding a BrowserWindow, or any refactor request in an Electron codebase.
---

# Electron + Node Architecture

## Why this exists

Electron apps have up to four separate runtime contexts (Main, Preload, Renderer, and
optionally a Node/HTTP backend or external process). Code that ignores these boundaries —
`fs` in a renderer, business logic stuffed into an IPC handler, a preload that exposes raw
`ipcRenderer` — works today and becomes a security hole or an untestable tangle later.
This skill exists to catch that at write-time, not in a later cleanup pass.

## The boundaries

| Context | Location | May use | Must NOT do |
|---|---|---|---|
| **Main** | `src/main/` | Node APIs, Electron APIs, shared types | Import React/renderer code; become a second backend with sprawling business logic |
| **Preload** | `src/preload/` | `contextBridge`, `ipcRenderer` (internally only) | Expose raw `ipcRenderer`; expose unrestricted fs/shell/process APIs |
| **Renderer** | `src/renderer/` | DOM, the API the preload exposes on `window` | Import `fs`, `child_process`, `electron`, `ipcMain`, `BrowserWindow`, DB clients |
| **Backend** (if present) | `apps/backend/` or an external process | HTTP/WS, DB, business logic | Import `electron`, React, or renderer code |

Check which context a file lives in **before** writing code in it. If a change would cross
a boundary (e.g. a renderer needs file access), the fix is a new preload-exposed API backed
by an IPC handler in Main — never reaching around the boundary.

## Preload rule: expose intent, not mechanism

Preload is the security boundary. Always expose a small, named, typed surface via
`contextBridge.exposeInMainWorld`. Never hand the renderer `ipcRenderer` itself — that gives
it access to every channel, present and future, not just the ones it should have.

Good — narrow, named, typed:
```ts
contextBridge.exposeInMainWorld("backend", {
  send: (message: Record<string, unknown>) => ipcRenderer.send("backend:send", message),
  on: (channel: string, callback: (message: unknown) => void) => {
    const listener = (_e: IpcRendererEvent, message: unknown) => callback(message);
    ipcRenderer.on(`backend:${channel}`, listener);
    return () => ipcRenderer.removeListener(`backend:${channel}`, listener);
  },
});
```

Bad — hands over the whole channel space:
```ts
contextBridge.exposeInMainWorld("electronAPI", { ipcRenderer });
```

If the same `Window.<api>` global type is declared in more than one renderer entry file,
that's a signal the type belongs in one shared `.d.ts` next to the renderer sources, not
copy-pasted per entry point — the copies will drift the next time the API changes.

## Security invariants

Every `BrowserWindow` that loads app UI must set:
```ts
webPreferences: {
  nodeIntegration: false,
  contextIsolation: true,
  preload: preloadPath,
}
```
Treat a window missing these as a bug, not a style nit — it silently reopens the boundary
this whole skill exists to enforce.

## IPC handlers stay thin

An IPC handler's job is: receive, delegate, respond. Business logic (validation, multi-step
orchestration, persistence) belongs in a plain function/module Main calls into — that module
is what you unit-test, not the handler.

```ts
// good
ipcMain.handle("files:read", (_e, path) => fileService.read(path));

// bad — logic trapped inside the handler, untestable without electron
ipcMain.handle("files:read", async (_e, path) => {
  // validation, fs calls, transformation all inline here
});
```

## When the "backend" is an external process, not HTTP

Not every Electron app has a Node HTTP backend — some pair the Electron shell with an
external process (Python, Go, etc.) speaking newline-delimited JSON or similar over stdio.
The same boundary logic applies, just relabeled:

- The process wrapper (spawn/kill/parse-lines) lives in Main, isolated in its own module —
  never inline in `index.ts`'s startup code.
- Renderer never talks to the process directly; it goes through the same
  preload-exposed `send`/`on` shape as any other IPC.
- A relay/dispatch module in Main may fan messages out to multiple windows or re-route
  namespaced commands (e.g. `"config:*"` staying in Main vs. everything else forwarded to
  the process) — that module should stay a pure router, not grow business logic of its own.

## Full Node backend layering (when present)

If the project does have a proper Node/HTTP backend, layer it the standard way:

```
Route → Controller → Service → Repository → DB/external API
```

- **Routes**: method + URL + middleware + controller. No logic.
- **Controllers**: parse request, call service, shape response/status. No business rules.
- **Services**: business logic, validation, orchestration, calls into repositories.
- **Repositories**: persistence only (query/insert/update/delete). No business rules.

Renderer talks to this backend through a typed API client package, never raw `fetch()`
scattered through components/pages.

## Shared code

Types/schemas/constants used by more than one runtime go in a shared package/folder that
imports nothing from Electron, React, DOM, or a DB client — it must stay usable from every
context that needs it. Don't let a "shared" file quietly gain an Electron or React import;
that's how one context's code leaks into another's build.

## Naming

```
*.service.ts   *.repository.ts   *.ipc.ts   *.schema.ts   *.store.ts   *.hook.ts
```
React/UI components: PascalCase (`ProjectCard.tsx`). Existing filenames that don't follow
this (e.g. a legacy `ipcRelay.ts`) are not automatically violations — see Refactoring below.

## Forbidden imports (grep for these before approving a renderer change)

```
renderer  → fs, node:fs, child_process, electron, ipcMain, BrowserWindow, raw ipcRenderer, DB client
backend   → electron, react
shared    → electron, react, DB client
```

## Refactoring discipline

When fixing a violation found while touching a file: fix it. When auditing a whole codebase:
only change what's an actual boundary violation or unsafe pattern (missing
`contextIsolation`, raw `ipcRenderer` exposure, forbidden import, duplicated type/logic
across contexts, business logic trapped in an IPC handler). Do not mass-rename files to
match the naming convention or reorganize working, boundary-clean code just to match the
reference folder layout — that's churn without a safety or correctness payoff. Preserve
behavior; verify with the project's typecheck/test/build commands after any change.

## Validation and errors

Validate external input (renderer→Main IPC payloads, HTTP requests) at the boundary that
receives it — never assume the sender is well-behaved. Don't propagate internal detail
(stack traces, file paths, SQL) across a boundary in an error payload; map to a small
`{ code, message }` shape instead.
