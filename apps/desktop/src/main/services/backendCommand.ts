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
