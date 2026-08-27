import { describe, expect, it, vi } from "vitest";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

// Mock koffi entirely -- this test suite only verifies the stash/no-op
// logic, never real registry access or SystemParametersInfoW. Matches this
// project's established policy for win32.service.ts / NutJsMouseDriver: the
// actual OS integration is manually verified, not unit-tested.
//
// Every mocked function returns 0 (success) by default, driven off
// `mockReturnCodes` (keyed by the win32 function name parsed out of the
// koffi signature string). Individual tests mutate `mockReturnCodes` to
// simulate a specific registry call failing, then restore it -- the
// service module itself is loaded once (dynamic `import()` is cached), so
// this indirection is what lets return codes vary per test.
const mockReturnCodes: Record<string, number> = vi.hoisted(() => ({}));

vi.mock("koffi", () => ({
  default: {
    load: () => ({
      func: (signature: string) => {
        const name = signature.match(/\s([A-Za-z0-9_]+)\(/)?.[1] ?? signature;
        return vi.fn((...args: unknown[]) => {
          if (name === "RegCreateKeyExW") {
            const phkResult = args[7];
            if (Array.isArray(phkResult)) phkResult[0] = {};
          }
          return mockReturnCodes[name] ?? 0;
        });
      },
    }),
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

  // Regression test: dragging the size slider back down to 32/"default"
  // after having applied some other size used to call restoreCursor(),
  // which puts back whatever the user's cursor looked like BEFORE this app
  // ever touched it -- not this app's own 32px black default. For a user
  // who already had a larger system cursor configured before installing
  // this app (common for this app's own target audience), that meant the
  // slider's minimum silently restored their old large size instead of
  // shrinking to 32, and consumed (deleted) the stash file the running
  // session still needs for its real cleanup point (quit / camera error).
  it("applies a real 32px default cursor instead of restoring the pre-app original when a stash already exists", async () => {
    const { applyCursor } = await import("../src/main/services/cursorTheme.service");
    const tmpDir = makeTmpDir();
    const stashPath = path.join(tmpDir, "original_arrow.json");
    const stashContent = JSON.stringify({ value: null, baseSize: 64 });
    fs.writeFileSync(stashPath, stashContent, "utf-8");

    applyCursor(32, "default", "#000000", tmpDir);

    // The stash is this session's only record of the true pre-app state --
    // it must survive untouched until an actual app-lifecycle restore
    // (quit / camera error), not get consumed by an ordinary slider value.
    expect(fs.readFileSync(stashPath, "utf-8")).toBe(stashContent);
    // A real 32px cursor file must have been written, exactly like any
    // other slider value would produce.
    const curPath = path.join(tmpDir, "arrow.cur");
    expect(fs.existsSync(curPath)).toBe(true);
    expect(fs.statSync(curPath).size).toBeGreaterThan(0);
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

describe("CursorBaseSize (Windows' own pointer-size scaling, applied alongside the .cur)", () => {
  // Regression test: the .cur file's own declared width/height alone had no
  // visible effect -- Windows scales every loaded cursor (including a
  // custom per-role override) to this separate registry DWORD at render
  // time, the same one Ease of Access's "Change pointer size" slider
  // writes. Only exercises the write path (never readCursorBaseSize's
  // registry read), matching this suite's existing koffi-mock boundary.
  it("restores CursorBaseSize from the stash alongside the Arrow value, without throwing", async () => {
    const { restoreCursor } = await import("../src/main/services/cursorTheme.service");
    const tmpDir = makeTmpDir();
    const stashPath = path.join(tmpDir, "original_arrow.json");
    fs.writeFileSync(stashPath, JSON.stringify({ value: null, baseSize: 32 }), "utf-8");

    expect(() => restoreCursor(tmpDir)).not.toThrow();

    expect(fs.existsSync(stashPath)).toBe(false);
    fs.rmSync(tmpDir, { recursive: true, force: true });
  });

  // A stash file written before this fix has no `baseSize` key at all --
  // restoring one of those must not throw, and must still fully succeed
  // (delete the value rather than leave a stray CursorBaseSize behind).
  it("treats a missing baseSize in an old-format stash as 'delete the value', not a failure", async () => {
    const { restoreCursor } = await import("../src/main/services/cursorTheme.service");
    const tmpDir = makeTmpDir();
    const stashPath = path.join(tmpDir, "original_arrow.json");
    fs.writeFileSync(stashPath, JSON.stringify({ value: null }), "utf-8");

    expect(() => restoreCursor(tmpDir)).not.toThrow();

    expect(fs.existsSync(stashPath)).toBe(false);
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

  // Regression test: koffi's return-code API means a failed registry write
  // no longer *throws* the way the Python reference's winreg calls do (they
  // raise OSError, which propagates past stash_path.unlink() so the stash
  // survives). writeArrowRegistry must surface that same failure via its
  // boolean return so restoreCursor can skip the unlink instead of silently
  // losing the user's real original cursor.
  it("keeps the stash file when the registry write-back fails, instead of deleting it", async () => {
    const { restoreCursor } = await import("../src/main/services/cursorTheme.service");
    const tmpDir = makeTmpDir();
    const stashPath = path.join(tmpDir, "original_arrow.json");
    fs.writeFileSync(stashPath, JSON.stringify({ value: "C:\\Windows\\cursors\\aero_arrow.cur" }), "utf-8");

    const consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    mockReturnCodes.RegSetValueExW = 5; // ERROR_ACCESS_DENIED
    try {
      expect(() => restoreCursor(tmpDir)).not.toThrow();
      // The stash must survive so a later restore attempt can retry.
      expect(fs.existsSync(stashPath)).toBe(true);
      expect(consoleErrorSpy).toHaveBeenCalled();
    } finally {
      delete mockReturnCodes.RegSetValueExW;
      consoleErrorSpy.mockRestore();
      fs.rmSync(tmpDir, { recursive: true, force: true });
    }
  });

  // The Python reference explicitly swallows FileNotFoundError when
  // deleting an already-gone registry value (`except FileNotFoundError:
  // pass`) -- ERROR_FILE_NOT_FOUND (2) from RegDeleteValueW must be treated
  // as success too, not as a failure that keeps the stash around forever.
  it("still deletes the stash when restoring a null value and RegDeleteValueW reports ERROR_FILE_NOT_FOUND", async () => {
    const { restoreCursor } = await import("../src/main/services/cursorTheme.service");
    const tmpDir = makeTmpDir();
    const stashPath = path.join(tmpDir, "original_arrow.json");
    fs.writeFileSync(stashPath, JSON.stringify({ value: null }), "utf-8");

    mockReturnCodes.RegDeleteValueW = 2; // ERROR_FILE_NOT_FOUND
    try {
      expect(() => restoreCursor(tmpDir)).not.toThrow();
      expect(fs.existsSync(stashPath)).toBe(false);
    } finally {
      delete mockReturnCodes.RegDeleteValueW;
      fs.rmSync(tmpDir, { recursive: true, force: true });
    }
  });
});
