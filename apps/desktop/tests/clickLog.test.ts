import { describe, expect, it, beforeEach, afterEach } from "vitest";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import * as clickLog from "../src/main/services/clickLog.service";

let tmpDir: string;
beforeEach(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "facemesh-clicklog-"));
  clickLog.disable();
});
afterEach(() => {
  clickLog.disable();
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

describe("clickLog", () => {
  it("writes nothing before enable()", () => {
    const file = path.join(tmpDir, "clicks.log");
    clickLog.record("blink_a", "left_click", [0, 0]);
    expect(fs.existsSync(file)).toBe(false);
  });

  it("writes one parseable line after enable()", () => {
    const file = path.join(tmpDir, "clicks.log");
    clickLog.enable(file);

    clickLog.record("blink_a", "left_click", [842, 511], () => "Notepad");

    const lines = fs.readFileSync(file, "utf-8").trim().split("\n");
    expect(lines).toHaveLength(1);
    expect(lines[0]).toContain("blink_a");
    expect(lines[0]).toContain("left_click");
    expect(lines[0]).toContain("(842, 511)");
    expect(lines[0]).toContain('"Notepad"');
  });

  it("does not duplicate writes when enabled twice", () => {
    const file = path.join(tmpDir, "clicks.log");
    clickLog.enable(file);
    clickLog.enable(file);

    clickLog.record("blink_a", "left_click", [0, 0], () => "X");

    expect(fs.readFileSync(file, "utf-8").trim().split("\n")).toHaveLength(1);
  });

  it("stops writing after disable()", () => {
    const file = path.join(tmpDir, "clicks.log");
    clickLog.enable(file);
    clickLog.record("blink_a", "left_click", [0, 0], () => "X");
    clickLog.disable();

    clickLog.record("blink_a", "left_click", [0, 0], () => "X");

    expect(fs.readFileSync(file, "utf-8").trim().split("\n")).toHaveLength(1);
  });

  it("rotates to a .1 backup past maxBytes", () => {
    const file = path.join(tmpDir, "clicks.log");
    clickLog.enable(file, 500, 2);

    for (let i = 0; i < 50; i++) {
      clickLog.record("blink_a", "left_click", [i, i], () => "x".repeat(40));
    }

    expect(fs.existsSync(`${file}.1`)).toBe(true);
  });
});
