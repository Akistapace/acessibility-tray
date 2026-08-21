// Pure cursor bitmap / .cur-file generation -- no filesystem, no registry,
// no native calls. Builds an arrow silhouette and serializes it into the
// classic (non-PNG) .cur container: ICONDIR + one ICONDIRENTRY + a combined
// XOR+AND legacy DIB image, the same layout every .cur file has used since
// Windows 3.1. Ported from cursor_image.py -- see
// docs/superpowers/specs/2026-08-18-cursor-appearance-design.md. No
// PIL/canvas dependency: this needs to run synchronously in the main
// process (cursor theme applies at startup, before any renderer window is
// guaranteed open), so polygon fill/outline are hand-rolled here instead of
// delegated to a renderer's 2D canvas.

export const VALID_CURSOR_MODES = new Set(["default", "white", "black", "custom", "mista"]);

// Arrow silhouette as a fraction of the bitmap's own side length, tip at the
// origin (top-left) -- the polygon's first vertex is always the cursor's
// hotspot. Identical to cursor_image.py's _ARROW_POINTS_FRACTION.
const ARROW_POINTS_FRACTION: Array<[number, number]> = [
  [0.0, 0.0], [0.0, 0.62], [0.18, 0.48],
  [0.29, 0.72], [0.4, 0.67], [0.29, 0.44], [0.5, 0.44],
];

function polygonPoints(sizePx: number): Array<[number, number]> {
  return ARROW_POINTS_FRACTION.map(([x, y]) => [x * sizePx, y * sizePx]);
}

// Point-in-polygon via the standard even-odd ray-casting test, evaluated at
// pixel centers (x+0.5, y+0.5) to match how rasterizers conventionally
// sample -- avoids the fill boundary being sensitive to exact-integer
// vertex coincidences.
function pointInPolygon(px: number, py: number, points: Array<[number, number]>): boolean {
  let inside = false;
  for (let i = 0, j = points.length - 1; i < points.length; j = i++) {
    const [xi, yi] = points[i];
    const [xj, yj] = points[j];
    const intersects = yi > py !== yj > py && px < ((xj - xi) * (py - yi)) / (yj - yi) + xi;
    if (intersects) inside = !inside;
  }
  return inside;
}

// Rasterizes the polygon's edges (not the fill) via a simple DDA line walk
// between consecutive vertices -- gives the 1px outline PIL's
// `ImageDraw.polygon(..., outline=...)` also draws, without needing a real
// stroking algorithm for this small, static 7-point shape.
function polygonEdgePixels(points: Array<[number, number]>, sizePx: number): Set<number> {
  const edgePixels = new Set<number>();
  const mark = (x: number, y: number) => {
    if (x >= 0 && x < sizePx && y >= 0 && y < sizePx) edgePixels.add(y * sizePx + x);
  };
  for (let i = 0; i < points.length; i++) {
    const [x0, y0] = points[i];
    const [x1, y1] = points[(i + 1) % points.length];
    const steps = Math.max(Math.abs(x1 - x0), Math.abs(y1 - y0), 1);
    for (let s = 0; s <= steps; s++) {
      mark(Math.round(x0 + ((x1 - x0) * s) / steps), Math.round(y0 + ((y1 - y0) * s) / steps));
    }
  }
  return edgePixels;
}

function arrowMask(sizePx: number): Uint8Array {
  // 1 where inside the arrow silhouette, 0 outside -- pixel-center sampled.
  const points = polygonPoints(sizePx);
  const mask = new Uint8Array(sizePx * sizePx);
  for (let y = 0; y < sizePx; y++) {
    for (let x = 0; x < sizePx; x++) {
      if (pointInPolygon(x + 0.5, y + 0.5, points)) mask[y * sizePx + x] = 1;
    }
  }
  return mask;
}

function contrastOutlineColor(fill: [number, number, number]): [number, number, number] {
  const [r, g, b] = fill;
  const luminance = 0.299 * r + 0.587 * g + 0.114 * b;
  return luminance > 127 ? [0, 0, 0] : [255, 255, 255];
}

// RGBA buffer (row-major, top-down, 4 bytes/pixel) -- fill inside the arrow
// silhouette, a 1px contrasting outline on the polygon edge, fully
// transparent outside.
function renderColorBitmap(sizePx: number, fill: [number, number, number]): Uint8Array {
  const mask = arrowMask(sizePx);
  const outline = contrastOutlineColor(fill);
  const edges = polygonEdgePixels(polygonPoints(sizePx), sizePx);
  const rgba = new Uint8Array(sizePx * sizePx * 4);
  for (let i = 0; i < sizePx * sizePx; i++) {
    const inside = mask[i] === 1;
    const onEdge = edges.has(i);
    const alpha = inside || onEdge ? 255 : 0;
    // Fully-transparent pixels must be RGB (0,0,0), matching the Python
    // reference's `Image.new("RGBA", ..., (0,0,0,0))` starting canvas --
    // NOT the fill/outline color. The legacy AND/XOR fallback a 32bpp
    // cursor still carries has AND=1, XOR=<this RGB> outside the shape, so
    // `dst = (dst & 1) ^ 0xFFFFFF` must reduce to a no-op (XOR 0) wherever
    // alpha is 0; XOR-ing the fill color there would invert the whole
    // cursor rectangle instead of leaving untouched pixels untouched.
    const [r, g, b] = alpha === 0 ? [0, 0, 0] : onEdge ? outline : fill;
    rgba[i * 4] = r;
    rgba[i * 4 + 1] = g;
    rgba[i * 4 + 2] = b;
    rgba[i * 4 + 3] = alpha;
  }
  return rgba;
}

function packAndMask(sizePx: number, transparentAt: (x: number, y: number) => boolean): Buffer {
  return pack1bppRows(sizePx, transparentAt);
}

// bitIsSet(x, y) for a sizePx x sizePx grid. Returns bottom-up rows (DIB
// convention), each padded to a 4-byte boundary, MSB of each byte = the
// leftmost pixel of that byte's 8-pixel span.
function pack1bppRows(sizePx: number, bitIsSet: (x: number, y: number) => boolean): Buffer {
  const rowBytes = Math.ceil(sizePx / 32) * 4;
  const out = Buffer.alloc(rowBytes * sizePx);
  for (let y = sizePx - 1, outRow = 0; y >= 0; y--, outRow++) {
    for (let x = 0; x < sizePx; x++) {
      if (bitIsSet(x, y)) {
        const byteIndex = outRow * rowBytes + (x >> 3);
        out[byteIndex] |= 0x80 >> (x % 8);
      }
    }
  }
  return out;
}

// Bottom-up BGRA rows -- DIB byte order, not the RGBA buffer's own order.
function pack32bppRows(rgba: Uint8Array, sizePx: number): Buffer {
  const out = Buffer.alloc(sizePx * sizePx * 4);
  let outOffset = 0;
  for (let y = sizePx - 1; y >= 0; y--) {
    for (let x = 0; x < sizePx; x++) {
      const i = (y * sizePx + x) * 4;
      out[outOffset++] = rgba[i + 2]; // B
      out[outOffset++] = rgba[i + 1]; // G
      out[outOffset++] = rgba[i]; // R
      out[outOffset++] = rgba[i + 3]; // A
    }
  }
  return out;
}

function assembleCur(sizePx: number, bitCount: number, xorData: Buffer, andData: Buffer): Buffer {
  const bmi = Buffer.alloc(40);
  bmi.writeInt32LE(40, 0); // biSize
  bmi.writeInt32LE(sizePx, 4); // biWidth
  bmi.writeInt32LE(sizePx * 2, 8); // biHeight -- combined XOR + AND
  bmi.writeUInt16LE(1, 12); // biPlanes
  bmi.writeUInt16LE(bitCount, 14); // biBitCount
  bmi.writeUInt32LE(0, 16); // biCompression (BI_RGB)
  bmi.writeUInt32LE(xorData.length + andData.length, 20); // biSizeImage
  // biXPelsPerMeter, biYPelsPerMeter, biClrUsed, biClrImportant all 0, already zeroed by Buffer.alloc

  // DIB rule: bpp<=8 requires a palette (values irrelevant -- mask bits, not
  // palette indices, drive AND/XOR interpretation -- only presence matters).
  const colorTable = bitCount <= 8 ? Buffer.from([0, 0, 0, 0, 255, 255, 255, 0]) : Buffer.alloc(0);
  const imageData = Buffer.concat([bmi, colorTable, xorData, andData]);

  const icondir = Buffer.alloc(6);
  icondir.writeUInt16LE(0, 0); // reserved
  icondir.writeUInt16LE(2, 2); // type: 2 = cursor
  icondir.writeUInt16LE(1, 4); // count: 1 image

  const side = sizePx < 256 ? sizePx : 0; // 0 means 256 in the ICO/CUR format
  const icondirentry = Buffer.alloc(16);
  icondirentry.writeUInt8(side, 0); // width
  icondirentry.writeUInt8(side, 1); // height
  icondirentry.writeUInt8(0, 2); // color count (0 = no palette limit)
  icondirentry.writeUInt8(0, 3); // reserved
  icondirentry.writeUInt16LE(0, 4); // xHotspot
  icondirentry.writeUInt16LE(0, 6); // yHotspot -- both 0: tip of the arrow, matching ARROW_POINTS_FRACTION's first vertex
  icondirentry.writeUInt32LE(imageData.length, 8); // bytes in image data
  icondirentry.writeUInt32LE(6 + 16, 12); // offset: ICONDIR (6 bytes) + this one ICONDIRENTRY (16 bytes)

  return Buffer.concat([icondir, icondirentry, imageData]);
}

export function buildCurBytesColor(sizePx: number, fillRgb: [number, number, number]): Buffer {
  const rgba = renderColorBitmap(sizePx, fillRgb);
  const xorData = pack32bppRows(rgba, sizePx);
  const andData = packAndMask(sizePx, (x, y) => rgba[(y * sizePx + x) * 4 + 3] === 0);
  return assembleCur(sizePx, 32, xorData, andData);
}

// The classic invert-cursor trick: AND=1 everywhere (nothing is ever fully
// opaque-covered), XOR=1 only inside the arrow silhouette. Where AND=1,XOR=1
// the compositor inverts the destination pixel; where AND=1,XOR=0 it's
// untouched -- so the silhouette inverts the screen under it and everywhere
// else is fully see-through, with zero ongoing cost to this app.
export function buildCurBytesMista(sizePx: number): Buffer {
  const mask = arrowMask(sizePx);
  const andData = pack1bppRows(sizePx, () => true);
  const xorData = pack1bppRows(sizePx, (x, y) => mask[y * sizePx + x] === 1);
  return assembleCur(sizePx, 1, xorData, andData);
}
