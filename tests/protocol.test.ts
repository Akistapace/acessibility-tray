import { describe, expect, it } from "vitest";
import { encodeMessage, parseLines } from "../src/main/protocol";

describe("encodeMessage", () => {
  it("serializes to one newline-terminated JSON line", () => {
    expect(encodeMessage({ type: "start" })).toBe('{"type":"start"}\n');
  });
});

describe("parseLines", () => {
  it("parses complete lines and returns no leftover", () => {
    const { messages, leftover } = parseLines('{"type":"start"}\n{"type":"stop"}\n', "");
    expect(messages).toEqual([{ type: "start" }, { type: "stop" }]);
    expect(leftover).toBe("");
  });

  it("buffers a partial line across chunks", () => {
    const first = parseLines('{"type":"sta', "");
    expect(first.messages).toEqual([]);
    expect(first.leftover).toBe('{"type":"sta');

    const second = parseLines('rt"}\n', first.leftover);
    expect(second.messages).toEqual([{ type: "start" }]);
    expect(second.leftover).toBe("");
  });

  it("skips blank and malformed lines", () => {
    const { messages } = parseLines('{"type":"start"}\n\nnot json\n{"type":"stop"}\n', "");
    expect(messages).toEqual([{ type: "start" }, { type: "stop" }]);
  });
});
