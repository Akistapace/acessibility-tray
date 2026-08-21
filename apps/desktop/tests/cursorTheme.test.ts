import { describe, expect, it, vi } from "vitest";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

// Mock koffi entirely -- this test suite only verifies the stash/no-op
// logic, never real registry access or SystemParametersInfoW. Matches this
// project's established policy for win32.service.ts / NutJsMouseDriver: the
// actual OS integration is manually verified, not unit-tested.
vi.mock("koffi", () => ({
  default: {
    load: () => ({ func: () => vi.fn(() => 0) }),
    as: (v: unknown) => v,
  },
}));

function makeTmpDir(): string {
  return fs.mkdtempSync(path.join(os.tmpdir(), "cursor-test-"));
}

describe("applyCursor no-op guard", () => {
  it("does nothing when size is default and mode is default, with no stash file present", async () => {
    const { applyCursor } = await import("../src/main/services/cursorTheme.service");
    const tmpDir = makeTmpDir();
    applyCursor(32, "default", "#000000", tmpDir);
    // No stash file should have been created -- nothing was ever "applied".
    expect(fs.existsSync(path.join(tmpDir, "original_arrow.json"))).toBe(false);
    // Nor should the cursor directory itself have been created.
    expect(fs.existsSync(path.join(tmpDir, "arrow.cur"))).toBe(false);
    fs.rmSync(tmpDir, { recursive: true, force: true });
  });
});

describe("restoreCursor without a prior apply", () => {
  it("is a pure no-op when no stash file exists", async () => {
    const { restoreCursor } = await import("../src/main/services/cursorTheme.service");
    const tmpDir = makeTmpDir();
    expect(() => restoreCursor(tmpDir)).not.toThrow();
    fs.rmSync(tmpDir, { recursive: true, force: true });
  });
});

describe("applyCursor with a non-default size/mode", () => {
  // A stash file is pre-seeded here so stashOriginalIfNeeded's early-return
  // path is taken -- it never calls into the mocked registry-read path
  // (readArrowRegistryValue), whose koffi.decode() call isn't part of this
  // suite's deliberately minimal koffi mock. Registry *writes* (via
  // writeArrowRegistry, exercised below) never call koffi.decode, so they
  // remain safe under this mock.
  it("writes the .cur file to the cursor directory without disturbing an existing stash", async () => {
    const { applyCursor } = await import("../src/main/services/cursorTheme.service");
    const tmpDir = makeTmpDir();
    const stashPath = path.join(tmpDir, "original_arrow.json");
    const stashContent = JSON.stringify({ value: null });
    fs.writeFileSync(stashPath, stashContent, "utf-8");

    expect(() => applyCursor(40, "white", "#000000", tmpDir)).not.toThrow();

    const curPath = path.join(tmpDir, "arrow.cur");
    expect(fs.existsSync(curPath)).toBe(true);
    expect(fs.statSync(curPath).size).toBeGreaterThan(0);
    // The pre-existing stash must be left untouched by this apply call.
    expect(fs.readFileSync(stashPath, "utf-8")).toBe(stashContent);
    fs.rmSync(tmpDir, { recursive: true, force: true });
  });

  it("falls back to the default color for an unrecognized mode string instead of throwing", async () => {
    const { applyCursor } = await import("../src/main/services/cursorTheme.service");
    const tmpDir = makeTmpDir();
    fs.writeFileSync(path.join(tmpDir, "original_arrow.json"), JSON.stringify({ value: null }), "utf-8");

    expect(() => applyCursor(48, "not-a-real-mode", "#000000", tmpDir)).not.toThrow();
    expect(fs.existsSync(path.join(tmpDir, "arrow.cur"))).toBe(true);
    fs.rmSync(tmpDir, { recursive: true, force: true });
  });
});

describe("restoreCursor with a prior stash", () => {
  it("deletes the stash file after restoring, without throwing", async () => {
    const { restoreCursor } = await import("../src/main/services/cursorTheme.service");
    const tmpDir = makeTmpDir();
    const stashPath = path.join(tmpDir, "original_arrow.json");
    fs.writeFileSync(stashPath, JSON.stringify({ value: "C:\\Windows\\cursors\\aero_arrow.cur" }), "utf-8");

    expect(() => restoreCursor(tmpDir)).not.toThrow();

    expect(fs.existsSync(stashPath)).toBe(false);
    fs.rmSync(tmpDir, { recursive: true, force: true });
  });
});
