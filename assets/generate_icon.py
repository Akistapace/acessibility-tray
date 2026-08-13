"""One-off generator for the FaceMesh Mouse app icon.

Concept: a cursor-pointer silhouette rendered as a small mesh graph (nodes +
edges) instead of a flat shape -- a direct visual pun on "facemesh" driving
a mouse cursor. Brand blue matches the CTk dark theme's button color
(#1F6AA5); the single green node echoes the tray's "running" status color.
Drawn at 4x and downsampled for anti-aliased edges, since PIL has no native
AA for polygons/lines.
"""
from PIL import Image, ImageDraw

SCALE = 4
SIZE = 256 * SCALE

BADGE_BG = (26, 28, 31, 255)          # near the app's #1f1f1f preview bg
BADGE_RADIUS = 58 * SCALE
CURSOR_FILL = (31, 106, 165, 255)     # #1F6AA5 -- CTk dark-blue button color
CURSOR_OUTLINE = (140, 190, 230, 255)
EDGE_COLOR = (170, 210, 240, 220)
NODE_FILL = (220, 235, 245, 255)
ACCENT_NODE = (46, 204, 113, 255)     # #2ecc71 -- tray "running" color


def _cursor_polygon(ox: float, oy: float, s: float) -> list[tuple[float, float]]:
    """Classic arrow-pointer outline, defined on a 100-unit box, scaled by
    `s` and offset by (ox, oy)."""
    pts = [
        (0, 0), (0, 72), (18, 56), (30, 82),
        (42, 77), (31, 51), (56, 51),
    ]
    return [(ox + x * s, oy + y * s) for x, y in pts]


def make_icon() -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle(
        (0, 0, SIZE - 1, SIZE - 1), radius=BADGE_RADIUS, fill=BADGE_BG
    )

    s = SIZE / 100 * 0.62
    ox, oy = SIZE * 0.27, SIZE * 0.20
    poly = _cursor_polygon(ox, oy, s)

    draw.polygon(poly, fill=CURSOR_FILL, outline=CURSOR_OUTLINE, width=max(2, SCALE))

    # Mesh overlay: thin edges between a subset of vertices, echoing a
    # facemesh wireframe traced over the pointer shape.
    mesh_edges = [(0, 2), (2, 4), (4, 6), (6, 1), (1, 0), (2, 3)]
    for a, b in mesh_edges:
        draw.line([poly[a], poly[b]], fill=EDGE_COLOR, width=max(2, SCALE))

    node_radius = 4.2 * SCALE
    for i, (x, y) in enumerate(poly):
        color = ACCENT_NODE if i == 0 else NODE_FILL
        r = node_radius * (1.35 if i == 0 else 1.0)
        draw.ellipse((x - r, y - r, x + r, y + r), fill=color)

    return img.resize((256, 256), Image.LANCZOS)


if __name__ == "__main__":
    icon = make_icon()
    icon.save("icon_preview.png")
    icon.save(
        "icon.ico",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print("wrote icon_preview.png and icon.ico")
