import { ChildProcessWithoutNullStreams, spawn } from "node:child_process";
import { EventEmitter } from "node:events";
import { BackendMessage, encodeMessage, parseLines } from "./protocol";

export class BackendProcess extends EventEmitter {
  private child: ChildProcessWithoutNullStreams | null = null;
  private leftover = "";

  constructor(
    private readonly command: string,
    private readonly args: string[]
  ) {
    super();
  }

  start(): void {
    this.child = spawn(this.command, this.args, {
      stdio: ["pipe", "pipe", "pipe"],
      windowsHide: true,
    });
    this.child.stdout.setEncoding("utf8");
    this.child.stdout.on("data", (chunk: string) => {
      const { messages, leftover } = parseLines(chunk, this.leftover);
      this.leftover = leftover;
      for (const message of messages) {
        this.emit("message", message as BackendMessage);
      }
    });
    this.child.stderr.setEncoding("utf8");
    this.child.stderr.on("data", (chunk: string) => this.emit("log", chunk));
    this.child.on("exit", (code) => this.emit("exit", code));
  }

  send(message: Record<string, unknown>): void {
    this.child?.stdin.write(encodeMessage(message));
  }

  stop(): void {
    if (!this.child) return;
    const child = this.child;
    child.stdin.end();
    // Give the backend's own `stop`-triggered `engine.stop()` (up to a
    // 2s thread join, see backend.py Task 6) a chance to exit cleanly
    // before forcing it -- mirrors Engine.stop()'s own timeout.
    const forceKillTimer = setTimeout(() => child.kill(), 2000);
    child.once("exit", () => clearTimeout(forceKillTimer));
    this.child = null;
  }
}
