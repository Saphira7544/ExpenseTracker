"""Draws the app icon (blue rounded square with white rising bars) as a multi-size
.ico of PNG images. Pure Python, so no image library is needed."""
import struct
import zlib
from pathlib import Path

SIZES = [16, 24, 32, 48, 64, 256]
TOP, BOTTOM = (79, 142, 247), (99, 102, 241)   # #4f8ef7 -> #6366f1, the app's blue


def _inside_rounded(x, y, size, radius):
    cx = min(max(x, radius), size - radius)
    cy = min(max(y, radius), size - radius)
    return (x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2


def _pixel(x, y, s):
    """RGBA for a point in a unit-size canvas scaled to s."""
    if not _inside_rounded(x, y, s, s * 0.22):
        return None
    # three rising bars, bottom-aligned
    bars = [(0.20, 0.36, 0.58), (0.42, 0.58, 0.40), (0.64, 0.80, 0.22)]   # x0, x1, top (fraction)
    for x0, x1, top in bars:
        if x0 * s <= x <= x1 * s and top * s <= y <= 0.80 * s:
            return (255, 255, 255)
    t = y / s
    return tuple(round(a + (b - a) * t) for a, b in zip(TOP, BOTTOM))


def _render(size, samples=4):
    rows = []
    for py in range(size):
        row = bytearray([0])                         # PNG filter: none
        for px in range(size):
            acc, hits = [0, 0, 0], 0
            for sy in range(samples):
                for sx in range(samples):
                    c = _pixel((px + (sx + 0.5) / samples) / size * 1000, (py + (sy + 0.5) / samples) / size * 1000, 1000)
                    if c:
                        hits += 1
                        acc = [a + v for a, v in zip(acc, c)]
            if hits:
                row += bytes([round(a / hits) for a in acc] + [round(255 * hits / samples ** 2)])
            else:
                row += b"\x00\x00\x00\x00"
        rows.append(bytes(row))
    return b"".join(rows)


def _png(size):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)          # 8-bit RGBA
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(_render(size), 9)) + chunk(b"IEND", b"")


def write_icon(path: Path) -> None:
    if path.exists():
        return
    images = [_png(s) for s in SIZES]
    out = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    for size, data in zip(SIZES, images):
        out += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    path.write_bytes(out + b"".join(images))


def write_png(path: Path, size: int = 64) -> None:
    path.write_bytes(_png(size))
