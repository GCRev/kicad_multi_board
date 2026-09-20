#!/usr/bin/env python3
"""Regenerate the toolbar icons in plugins/icons/ (light and dark, 24 px and 48 px). The PNGs are committed.

    python scripts/make_icons.py
"""
from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "plugins" / "icons"
SIZES = (24, 48)
SAMPLES = 8  # per axis, per pixel

THEMES = {
    "light": {"board": (0x37, 0x47, 0x4F), "arrow": (0x00, 0x89, 0x7B)},
    "dark": {"board": (0xCF, 0xD8, 0xDC), "arrow": (0x4D, 0xB6, 0xAC)},
}

# Unit-square geometry: a board outline with an arrow leaving it.
BOARD = (0.06, 0.16, 0.66, 0.84)  # x0, y0, x1, y1
BOARD_RADIUS = 0.08
BOARD_STROKE = 0.09
ARROW = [(0.38, 0.42), (0.70, 0.42), (0.70, 0.26), (0.96, 0.50), (0.70, 0.74), (0.70, 0.58), (0.38, 0.58)]


def _board_hit(x: float, y: float) -> bool:
    x0, y0, x1, y1 = BOARD
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    hx, hy = (x1 - x0) / 2 - BOARD_RADIUS, (y1 - y0) / 2 - BOARD_RADIUS
    qx, qy = abs(x - cx) - hx, abs(y - cy) - hy
    sdf = math.hypot(max(qx, 0), max(qy, 0)) + min(max(qx, qy), 0) - BOARD_RADIUS
    return abs(sdf) <= BOARD_STROKE / 2


def _inside(poly, x: float, y: float) -> bool:
    hit = False
    for (ax, ay), (bx, by) in zip(poly, poly[1:] + poly[:1]):
        if (ay > y) != (by > y) and x < ax + (y - ay) * (bx - ax) / (by - ay):
            hit = not hit
    return hit


def render(size: int, colors: dict) -> bytes:
    """RGBA rows, board under arrow, antialiased by supersampling."""
    rows = bytearray()
    for py in range(size):
        rows.append(0)  # PNG filter type: none
        for px in range(size):
            acc = [0.0, 0.0, 0.0, 0.0]  # premultiplied r, g, b and coverage
            for sy in range(SAMPLES):
                for sx in range(SAMPLES):
                    x = (px + (sx + 0.5) / SAMPLES) / size
                    y = (py + (sy + 0.5) / SAMPLES) / size
                    if _inside(ARROW, x, y):
                        color = colors["arrow"]
                    elif _board_hit(x, y):
                        color = colors["board"]
                    else:
                        continue
                    acc[0] += color[0]
                    acc[1] += color[1]
                    acc[2] += color[2]
                    acc[3] += 1
            n = acc[3]
            if n:
                rows += bytes([round(acc[0] / n), round(acc[1] / n), round(acc[2] / n), round(255 * n / SAMPLES**2)])
            else:
                rows += bytes(4)
    return bytes(rows)


def png(size: int, rgba_rows: bytes) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(rgba_rows, 9)) + chunk(b"IEND", b"")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for theme, colors in THEMES.items():
        for size in SIZES:
            path = OUT / f"export-{theme}-{size}.png"
            path.write_bytes(png(size, render(size, colors)))
            print("wrote", path.relative_to(OUT.parent.parent))


if __name__ == "__main__":
    main()
