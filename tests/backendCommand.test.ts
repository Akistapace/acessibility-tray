import { describe, expect, it } from "vitest";
import path from "node:path";
import { resolveBackendCommand } from "../src/modules/backendCommand";

describe("resolveBackendCommand", () => {
  it("uses the bundled exe when packaged", () => {
    const result = resolveBackendCommand(true, "C:/App/resources");
    expect(result).toEqual({
      command: path.join("C:/App/resources", "backend", "facemesh-mouse-backend.exe"),
      args: [],
    });
  });

  it("spawns the repo-root run.py otherwise", () => {
    // Both this test file (electron/tests) and the module under test
    // (electron/src/main, electron/dist/main once compiled) sit exactly
    // that many levels below the repo root.
    expect(resolveBackendCommand(false, "")).toEqual({
      command: "python",
      args: [path.join(__dirname, "..", "..", "run.py")],
    });
  });
});
