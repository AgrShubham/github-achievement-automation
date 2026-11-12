"""Generate a crisp multi-resolution Windows application icon (packaging/icon.ico)."""

from __future__ import annotations

import math
from pathlib import Path
from PIL import Image, ImageDraw


def render_badge_icon(size: int = 512) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    pad = int(size * 0.06)
    radius = int(size * 0.22)
    draw.rounded_rectangle(
        [pad, pad, size - pad, size - pad],
        radius=radius,
        fill=(13, 17, 23, 255),
        outline=(48, 54, 61, 255),
        width=max(2, int(size * 0.025)),
    )

    # Outer emerald/blue achievement ring
    ring_pad = int(size * 0.14)
    draw.ellipse(
        [ring_pad, ring_pad, size - ring_pad, size - ring_pad],
        fill=(22, 27, 34, 255),
        outline=(47, 129, 247, 255),
        width=max(3, int(size * 0.035)),
    )

    # Inner golden achievement hexagon/shield medallion
    cx, cy = size / 2.0, size / 2.0
    hex_r = size * 0.27
    hex_pts = []
    for i in range(6):
        ang = math.radians(60 * i - 90)
        hex_pts.append((cx + hex_r * math.cos(ang), cy + hex_r * math.sin(ang)))
    draw.polygon(hex_pts, fill=(35, 134, 54, 255), outline=(63, 185, 80, 255))

    # Crisp 5-point star in the center
    star_pts = []
    outer_r = size * 0.165
    inner_r = size * 0.072
    for i in range(10):
        ang = math.radians(36 * i - 90)
        r = outer_r if i % 2 == 0 else inner_r
        star_pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    draw.polygon(star_pts, fill=(247, 201, 72, 255))

    return img


def main() -> None:
    out_path = Path(__file__).resolve().parent / "icon.ico"
    base = render_badge_icon(512)
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    base.save(out_path, format="ICO", sizes=sizes)
    print(f"Generated {out_path}")


if __name__ == "__main__":
    main()

