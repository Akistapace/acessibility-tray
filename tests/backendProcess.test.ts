import { describe, expect, it } from "vitest";
import path from "node:path";
import { BackendProcess } from "../src/modules/backendProcess";

const FIXTURE = path.join(__dirname, "fixtures", "echoBackend.mjs");

describe("BackendProcess", () => {
  it("round-trips a sent command through the child's stdout", async () => {
    const proc = new BackendProcess("node", [FIXTURE]);
    const received = new Promise((resolve) => proc.once("message", resolve));

    proc.start();
    proc.send({ type: "start" });

    expect(await received).toEqual({ type: "echo", received: { type: "start" } });
    proc.stop();
  });

  it("emits exit when the child process ends", async () => {
    const proc = new BackendProcess("node", ["-e", "process.exit(0)"]);
    const exited = new Promise((resolve) => proc.once("exit", resolve));

    proc.start();

    expect(await exited).toBe(0);
  });

  it("emits exit instead of crashing when the command can't be spawned", async () => {
    const proc = new BackendProcess("this-command-does-not-exist-12345", []);
    const exited = new Promise((resolve) => proc.once("exit", resolve));

    proc.start();

    expect(await exited).toBeNull();
  });
});
