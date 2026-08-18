"""Pure cursor bitmap / .cur-file generation -- no filesystem, no registry,
no ctypes. Builds an arrow silhouette and serializes it into the classic
(non-PNG) .cur container: ICONDIR + one ICONDIRENTRY + a combined XOR+AND
legacy DIB image, the same layout every .cur file has used since Windows
3.1. See docs/superpowers/specs/2026-08-18-cursor-appearance-design.md.
"""
from __future__ import annotations

import struct

from PIL import Image, ImageDraw

# Arrow silhouette as a fraction of the bitmap's own side length, tip at the
# origin (top-left) -- the polygon's first vertex is always the cursor's
# hotspot.
_ARROW_POINTS_FRACTION = [
    (0.0, 0.0), (0.0, 0.62), (0.18, 0.48),
    (0.29, 0.72), (0.40, 0.67), (0.29, 0.44), (0.5, 0.44),
]

VALID_MODES = {"default", "white", "black", "custom", "mista"}


def _polygon_points(size_px: int) -> list[tuple[float, float]]:
    return [(x * size_px, y * size_px) for x, y in _ARROW_POINTS_FRACTION]


def _arrow_mask(size_px: int) -> Image.Image:
    """1-channel mask, 255 inside the arrow silhouette, 0 outside."""
    mask = Image.new("L", (size_px, size_px), 0)
    ImageDraw.Draw(mask).polygon(_polygon_points(size_px), fill=255)
    return mask


def _contrast_outline_color(fill: tuple[int, int, int]) -> tuple[int, int, int]:
    """Black outline on a light fill, white outline on a dark fill --
    relative luminance (ITU-R BT.601) thresholded at the midpoint. A static
    one-time contrast choice -- "mista" mode is what protects against an
    arbitrary/changing background, this is just so a solid-color arrow
    doesn't disappear against a same-color background at the moment it's
    picked."""
    r, g, b = fill
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    return (0, 0, 0) if luminance > 127 else (255, 255, 255)


def render_color_bitmap(size_px: int, fill: tuple[int, int, int]) -> Image.Image:
    """RGBA arrow: `fill` inside, a contrasting outline traced on the
    silhouette edge, fully transparent outside."""
    mask = _arrow_mask(size_px)
    outline = _contrast_outline_color(fill)
    image = Image.new("RGBA", (size_px, size_px), (0, 0, 0, 0))
    ImageDraw.Draw(image).polygon(
        _polygon_points(size_px), fill=(*fill, 255), outline=(*outline, 255)
    )
    image.putalpha(mask)
    return image


def _pack_1bpp_rows(size_px: int, bit_is_set) -> bytes:
    """`bit_is_set(x, y) -> bool` for a size_px x size_px grid. Returns
    bottom-up rows (DIB convention), each padded to a 4-byte boundary, MSB
    of each byte = the leftmost pixel of that byte's 8-pixel span -- the
    shared row layout both the AND and XOR 1bpp masks use."""
    row_bytes = ((size_px + 31) // 32) * 4
    out = bytearray()
    for y in range(size_px - 1, -1, -1):
        row = bytearray(row_bytes)
        for x in range(size_px):
            if bit_is_set(x, y):
                row[x // 8] |= 0x80 >> (x % 8)
        out += row
    return bytes(out)


def _pack_32bpp_rows(image: Image.Image) -> bytes:
    """Bottom-up BGRA rows -- DIB byte order, not Pillow's RGBA."""
    size_px = image.width
    px = image.load()
    out = bytearray()
    for y in range(size_px - 1, -1, -1):
        for x in range(size_px):
            r, g, b, a = px[x, y]
            out += bytes((b, g, r, a))
    return bytes(out)


def _assemble_cur(
    size_px: int, bit_count: int, xor_data: bytes, and_data: bytes, hotspot: tuple[int, int]
) -> bytes:
    bmi = struct.pack(
        "<IiiHHIIiiII",
        40,  # biSize
        size_px,  # biWidth
        size_px * 2,  # biHeight -- combined XOR + AND
        1,  # biPlanes
        bit_count,  # biBitCount
        0,  # biCompression (BI_RGB)
        len(xor_data) + len(and_data),  # biSizeImage
        0, 0,  # biXPelsPerMeter, biYPelsPerMeter
        0, 0,  # biClrUsed, biClrImportant
    )
    # DIB rule: bpp<=8 requires a palette. The values are irrelevant here
    # (the mask bits, not palette indices, drive AND/XOR interpretation) --
    # only its presence is required for the header to be valid.
    color_table = bytes([0, 0, 0, 0, 255, 255, 255, 0]) if bit_count <= 8 else b""
    image_data = bmi + color_table + xor_data + and_data

    icondir = struct.pack("<HHH", 0, 2, 1)  # idType=2 -> cursor, idCount=1
    side = size_px if size_px < 256 else 0  # 0 means 256 in the ICO/CUR format
    icondirentry = struct.pack(
        "<BBBBHHII",
        side, side, 0, 0,
        hotspot[0], hotspot[1],
        len(image_data),
        6 + 16,  # offset: ICONDIR (6 bytes) + this one ICONDIRENTRY (16 bytes)
    )
    return icondir + icondirentry + image_data


def build_cur_bytes_color(image: Image.Image) -> bytes:
    size_px = image.width
    xor_data = _pack_32bpp_rows(image)
    px = image.load()
    and_data = _pack_1bpp_rows(size_px, lambda x, y: px[x, y][3] == 0)
    return _assemble_cur(size_px, bit_count=32, xor_data=xor_data, and_data=and_data, hotspot=(0, 0))


def build_cur_bytes_mista(size_px: int) -> bytes:
    """The classic invert-cursor trick: AND=1 everywhere (nothing is ever
    fully opaque-covered), XOR=1 only inside the arrow silhouette. Where
    AND=1,XOR=1 the compositor inverts the destination pixel; where
    AND=1,XOR=0 it's untouched -- so the silhouette inverts the screen
    under it and everywhere else is fully see-through, with zero ongoing
    cost to this app."""
    mask = _arrow_mask(size_px)
    mpx = mask.load()
    and_data = _pack_1bpp_rows(size_px, lambda x, y: True)
    xor_data = _pack_1bpp_rows(size_px, lambda x, y: mpx[x, y] > 127)
    return _assemble_cur(size_px, bit_count=1, xor_data=xor_data, and_data=and_data, hotspot=(0, 0))
