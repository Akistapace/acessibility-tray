import { describe, expect, it } from "vitest";
import { LETTER_ROWS, ACCENT_ROW, FULL_EXTRA_ROWS, keyOutput } from "../src/renderer/keyboard/layout";

describe("keyboard layout data", () => {
  it("has three QWERTY letter rows", () => {
    expect(LETTER_ROWS).toEqual([
      [..."QWERTYUIOP"],
      [..."ASDFGHJKL"],
      [..."ZXCVBNM"],
    ]);
  });

  it("accent row has the Portuguese accented characters", () => {
    expect(ACCENT_ROW).toEqual([..."ÁÃÂÀÉÊÍÓÔÕÚ", "Ç"]);
  });

  it("full-mode extra rows are numbers then punctuation", () => {
    expect(FULL_EXTRA_ROWS).toEqual([[..."1234567890"], [",", ".", "-", "?"]]);
  });
});

describe("keyOutput", () => {
  it("lowercases when shift is not active", () => {
    expect(keyOutput("Q", false)).toBe("q");
  });

  it("uppercases when shift is active", () => {
    expect(keyOutput("q", true)).toBe("Q");
  });

  it("uppercases an accented character when shift is active", () => {
    expect(keyOutput("á", true)).toBe("Á");
  });
});
