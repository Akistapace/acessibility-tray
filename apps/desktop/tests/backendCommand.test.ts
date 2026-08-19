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
