#!/usr/bin/env python3
"""Generate deterministic PetroLab test-build icons without external packages."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ICONS = ROOT / "desktop" / "src-tauri" / "icons"
SIZE = 256


def _chunk(kind: bytes, payload: bytes) -> bytes:
    checksum = zlib.crc32(kind + payload) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", checksum)


def _rounded_square(x: int, y: int, inset: int = 12, radius: int = 46) -> bool:
    if inset + radius <= x < SIZE - inset - radius or inset + radius <= y < SIZE - inset - radius:
        return inset <= x < SIZE - inset and inset <= y < SIZE - inset
    cx = inset + radius if x < SIZE // 2 else SIZE - inset - radius - 1
    cy = inset + radius if y < SIZE // 2 else SIZE - inset - radius - 1
    return (x - cx) ** 2 + (y - cy) ** 2 <= radius**2


def _pixel(x: int, y: int) -> tuple[int, int, int, int]:
    transparent = (0, 0, 0, 0)
    green = (0, 91, 59, 255)
    white = (247, 251, 249, 255)
    if not _rounded_square(x, y):
        return transparent
    color = green
    # A compact PetroLab P: a strong stem and a circular analytical-point bowl.
    if 73 <= x <= 98 and 52 <= y <= 207:
        color = white
    outer = (x - 127) ** 2 + (y - 103) ** 2 <= 54**2
    inner = (x - 127) ** 2 + (y - 103) ** 2 < 28**2
    if outer and not inner and x >= 82:
        color = white
    if 93 <= x <= 132 and 151 <= y <= 175 and y - 151 >= (x - 93) // 3:
        color = white
    return color


def _png() -> bytes:
    rows = []
    for y in range(SIZE):
        row = bytearray([0])
        for x in range(SIZE):
            row.extend(_pixel(x, y))
        rows.append(bytes(row))
    header = struct.pack(">IIBBBBB", SIZE, SIZE, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", header) + _chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + _chunk(b"IEND", b"")


def main() -> None:
    ICONS.mkdir(parents=True, exist_ok=True)
    png = _png()
    (ICONS / "icon.png").write_bytes(png)
    directory = struct.pack("<HHH", 0, 1, 1)
    entry = struct.pack("<BBBBHHII", 0, 0, 0, 0, 1, 32, len(png), 22)
    (ICONS / "icon.ico").write_bytes(directory + entry + png)
    print("Generated deterministic PetroLab icons.")


if __name__ == "__main__":
    main()
