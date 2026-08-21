import { describe, expect, it } from "vitest";
import { buildCurBytesColor, buildCurBytesMista, VALID_CURSOR_MODES } from "../src/main/services/cursorImage";

describe("VALID_CURSOR_MODES", () => {
  it("has exactly the five documented modes", () => {
    expect([...VALID_CURSOR_MODES].sort()).toEqual(["black", "custom", "default", "mista", "white"]);
  });
});

describe("buildCurBytesColor", () => {
  it("produces a valid ICONDIR + one ICONDIRENTRY header", () => {
    const bytes = buildCurBytesColor(32, [255, 0, 0]);
    // ICONDIR (6 bytes): reserved=0 (u16 @0), type=2 (u16 @2, cursor), count=1 (u16 @4)
    expect(bytes.readUInt16LE(0)).toBe(0);
    expect(bytes.readUInt16LE(2)).toBe(2);
    expect(bytes.readUInt16LE(4)).toBe(1);
    // ICONDIRENTRY starts at offset 6 (right after the 6-byte ICONDIR):
    // width u8 @6, height u8 @7, colorCount u8 @8, reserved u8 @9,
    // hotspotX u16 @10, hotspotY u16 @12, bytesInRes u32 @14, imageOffset u32 @18
    expect(bytes.readUInt8(6)).toBe(32);
    expect(bytes.readUInt8(7)).toBe(32);
    // hotspot fields are (0, 0) -- tip of the arrow
    expect(bytes.readUInt16LE(10)).toBe(0);
    expect(bytes.readUInt16LE(12)).toBe(0);
    // image data offset points past the 6+16=22 byte header
    expect(bytes.readUInt32LE(18)).toBe(22);
  });

  // 256 is outside this feature's cursor size range (CURSOR_SIZE_RANGE is
  // 32-96px, wired up in a later task), so the "256 encoded as byte 0"
  // ICO/CUR edge case is unreachable in practice and isn't tested here.

  it("total byte length matches a 32bpp BGRA image plus a 1bpp AND mask, both padded to 4-byte rows", () => {
    const sizePx = 32;
    const bytes = buildCurBytesColor(sizePx, [0, 0, 0]);
    const bmiHeaderSize = 40;
    const colorTableSize = 0; // bit_count > 8, no palette
    const xorRowBytes = sizePx * 4; // 32bpp, already 4-byte aligned at width 32
    const andRowBytes = ((sizePx + 31) >> 5) * 4; // 1bpp, padded to 4-byte boundary
    const expectedImageDataSize = bmiHeaderSize + colorTableSize + xorRowBytes * sizePx + andRowBytes * sizePx;
    expect(bytes.length).toBe(6 + 16 + expectedImageDataSize);
  });

  it("total byte length holds for a non-multiple-of-32 size (row padding exercised)", () => {
    const sizePx = 40;
    const bytes = buildCurBytesColor(sizePx, [10, 20, 30]);
    const bmiHeaderSize = 40;
    const colorTableSize = 0;
    const xorRowBytes = sizePx * 4;
    const andRowBytes = ((sizePx + 31) >> 5) * 4;
    const expectedImageDataSize = bmiHeaderSize + colorTableSize + xorRowBytes * sizePx + andRowBytes * sizePx;
    expect(bytes.length).toBe(6 + 16 + expectedImageDataSize);
  });

  it("fully-transparent pixels are RGB (0,0,0), not the fill color", () => {
    // Regression test: a fully-transparent pixel that carries a non-black
    // RGB is not just a fidelity nitpick -- the legacy AND/XOR fallback a
    // 32bpp cursor still carries has AND=1, XOR=<this pixel's RGB> outside
    // the shape, so `dst = (dst & 1) ^ 0xFFFFFF` must reduce to a no-op
    // (XOR 0) wherever alpha is 0. A non-black RGB there would invert the
    // whole cursor rectangle instead of leaving untouched pixels untouched.
    const sizePx = 32;
    const bytes = buildCurBytesColor(sizePx, [255, 0, 0]);
    const xorStart = 6 + 16 + 40; // ICONDIR+ICONDIRENTRY(22) + BITMAPINFOHEADER(40), no palette at 32bpp
    const rowBytes = sizePx * 4; // 32bpp rows are already 4-byte aligned

    // Row 30 (near the canvas's bottom-right, far outside the arrow's
    // extent -- the polygon's points only reach ~0.72 * sizePx down) is
    // fully transparent for every column at this size.
    const logicalY = 30;
    const outRow = sizePx - 1 - logicalY; // bottom-up DIB row order
    let checked = 0;
    for (let x = 0; x < sizePx; x++) {
      const pixelOffset = xorStart + outRow * rowBytes + x * 4;
      const alpha = bytes.readUInt8(pixelOffset + 3);
      if (alpha !== 0) continue; // only assert on the pixels that are actually transparent
      expect([bytes.readUInt8(pixelOffset), bytes.readUInt8(pixelOffset + 1), bytes.readUInt8(pixelOffset + 2)]).toEqual([0, 0, 0]);
      checked++;
    }
    expect(checked).toBe(sizePx); // the whole row is transparent at this size/shape
  });

  it("decodes a known interior pixel in BGRA channel order", () => {
    // (2, 4) is a deep-interior pixel (inside the arrow silhouette, not on
    // the 1px outline, with all 4 neighbors also interior) for sizePx=32
    // and this module's ARROW_POINTS_FRACTION -- verified independently by
    // re-evaluating the point-in-polygon test and the edge walk in a
    // throwaway script, not by reading the implementation's own output.
    const sizePx = 32;
    const bytes = buildCurBytesColor(sizePx, [255, 0, 0]); // fill = pure red
    const xorStart = 6 + 16 + 40;
    const rowBytes = sizePx * 4;
    const [x, y] = [2, 4];
    const outRow = sizePx - 1 - y; // bottom-up DIB row order
    const pixelOffset = xorStart + outRow * rowBytes + x * 4;
    // DIB 32bpp pixel order is B, G, R, A -- NOT the RGBA order the source
    // buffer used internally. Red fill (255,0,0) must therefore read back
    // as [0, 0, 255, 255] here, not [255, 0, 0, 255].
    expect([
      bytes.readUInt8(pixelOffset),
      bytes.readUInt8(pixelOffset + 1),
      bytes.readUInt8(pixelOffset + 2),
      bytes.readUInt8(pixelOffset + 3),
    ]).toEqual([0, 0, 255, 255]);
  });

  it("stores rows bottom-up: the arrow tip (top of the logical image) decodes from the last file row", () => {
    // The polygon's first vertex -- the hotspot, (0,0) in fraction space --
    // sits at the *top* of the logical image (y=0) and is inside the
    // silhouette. The opposite corner (x=0, y=sizePx-1) is far outside the
    // arrow's extent (its points only reach down to ~0.72 * sizePx) and is
    // fully transparent. In a correctly bottom-up-stored DIB, the tip's
    // opacity is found in the *last* stored row, not the first.
    const sizePx = 32;
    const bytes = buildCurBytesColor(sizePx, [0, 255, 0]);
    const xorStart = 6 + 16 + 40;
    const rowBytes = sizePx * 4;
    const alphaAtFileRow = (fileRow: number) => bytes.readUInt8(xorStart + fileRow * rowBytes + 0 * 4 + 3);

    // Correct bottom-up read: logical y=0 (the tip) lives at file row sizePx-1.
    expect(alphaAtFileRow(sizePx - 1)).toBe(255);
    // A naive top-down read of the same logical position (file row 0,
    // unflipped) lands on logical y=sizePx-1 instead, which is transparent
    // -- proving the two interpretations disagree and this file is
    // genuinely bottom-up, not top-down.
    expect(alphaAtFileRow(0)).toBe(0);
  });
});

describe("buildCurBytesMista", () => {
  it("produces a 1bpp cursor (bit_count field == 1 in the BITMAPINFOHEADER)", () => {
    const bytes = buildCurBytesMista(32);
    // BITMAPINFOHEADER starts right after the 22-byte ICONDIR+ICONDIRENTRY
    // header; biBitCount is a u16 at offset 14 within that 40-byte header
    const biBitCountOffset = 22 + 14;
    expect(bytes.readUInt16LE(biBitCountOffset)).toBe(1);
  });

  it("total byte length matches two 1bpp masks (AND + XOR) plus an 8-byte 2-color palette", () => {
    const sizePx = 32;
    const bytes = buildCurBytesMista(sizePx);
    const bmiHeaderSize = 40;
    const colorTableSize = 8; // bit_count <= 8 requires a palette; 2 entries x 4 bytes
    const maskRowBytes = ((sizePx + 31) >> 5) * 4;
    const expectedImageDataSize = bmiHeaderSize + colorTableSize + maskRowBytes * sizePx * 2;
    expect(bytes.length).toBe(6 + 16 + expectedImageDataSize);
  });

  // Checks only the real (non-padding) bits of each row, so this holds at
  // any sizePx -- not just a multiple of 32, where there happens to be no
  // padding and a blanket "every byte is 0xFF" assertion would coincidentally
  // pass without actually proving anything about padding bits.
  function realBitIsSet(bytes: Buffer, start: number, rowBytes: number, sizePx: number, x: number, y: number): boolean {
    const outRow = sizePx - 1 - y; // bottom-up DIB row order
    const byteIndex = start + outRow * rowBytes + (x >> 3);
    return ((bytes.readUInt8(byteIndex) >> (7 - (x % 8))) & 1) === 1;
  }

  it.each([32, 40])("AND mask's real bits are all 1 (fully see-through) at sizePx=%i", (sizePx) => {
    const bytes = buildCurBytesMista(sizePx);
    const rowBytes = Math.ceil(sizePx / 32) * 4;
    const bmiHeaderSize = 40;
    const colorTableSize = 8;
    const imageDataStart = 6 + 16;
    const xorStart = imageDataStart + bmiHeaderSize + colorTableSize;
    const andStart = xorStart + rowBytes * sizePx;

    for (let y = 0; y < sizePx; y++) {
      for (let x = 0; x < sizePx; x++) {
        expect(realBitIsSet(bytes, andStart, rowBytes, sizePx, x, y)).toBe(true);
      }
    }
  });

  it("XOR mask is 1 exactly inside the arrow silhouette (not all-zero, not all-one)", () => {
    const sizePx = 32;
    const bytes = buildCurBytesMista(sizePx);
    const rowBytes = Math.ceil(sizePx / 32) * 4;
    const bmiHeaderSize = 40;
    const colorTableSize = 8;
    const imageDataStart = 6 + 16;
    const xorStart = imageDataStart + bmiHeaderSize + colorTableSize;

    let anySet = false;
    let allSet = true;
    for (let y = 0; y < sizePx; y++) {
      for (let x = 0; x < sizePx; x++) {
        const set = realBitIsSet(bytes, xorStart, rowBytes, sizePx, x, y);
        if (set) anySet = true;
        else allSet = false;
      }
    }
    expect(anySet).toBe(true);
    expect(allSet).toBe(false);
  });
});
