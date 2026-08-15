import { describe, expect, it } from "vitest";
import path from "node:path";
import { resolveBackendCommand } from "../src/main/backendCommand";

describe("resolveBackendCommand", () => {
  it("uses the bundled exe when packaged", () => {
    const result = resolveBackendCommand(true, "C:/App/resources");
    expect(result).toEqual({
      command: path.join("C:/App/resources", "backend", "facemesh-mouse-backend.exe"),
      args: [],
    });
  });

  it("uses the dev python module otherwise", () => {
    expect(resolveBackendCommand(false, "")).toEqual({
      command: "python",
      args: ["-m", "facemesh_mouse.backend"],
    });
  });
});
