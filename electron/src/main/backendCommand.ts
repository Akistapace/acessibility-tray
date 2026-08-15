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
  return { command: "python", args: ["-m", "facemesh_mouse.backend"] };
}
