import path from "node:path";

export function resolveBackendCommand(
  isPackaged: boolean,
  resourcesPath: string
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
  // cwd. This module runs from dist/main/, three levels below the repo root
  // (dist/main -> dist -> electron -> repo root).
  return {
    command: "python",
    args: [path.join(__dirname, "..", "..", "..", "run.py")],
  };
}
