"""Generate a minimal 16×16 placeholder .ico file for build-time use.

Replaced by a proper icon in production.  This ensures the PyInstaller
spec and Inno Setup script can always find an icon file.
"""

from __future__ import annotations

import struct
from pathlib import Path


def make_placeholder_ico(path: str | Path = "assets/icon.ico") -> None:
    """Create a simple solid-blue 16×16 ICO file at *path*."""
    width, height = 16, 16

    # RGBA pixel data (32 BPP)
    pixels = b""
    for _ in range(height):
        for _ in range(width):
            pixels += bytes([0, 0, 255, 255])  # B, G, R, A

    mask_row_size = ((width + 31) // 32) * 4
    xor_data = pixels
    and_data = b"\x00" * (mask_row_size * height)

    # BMP info header (40 bytes)
    biSize = struct.pack("<I", 40)
    biWidth = struct.pack("<i", width)
    biHeight = struct.pack("<i", height * 2)  # doubled for ICO
    biPlanes = struct.pack("<H", 1)
    biBitCount = struct.pack("<H", 32)
    biCompression = struct.pack("<I", 0)
    biSizeImage = struct.pack("<I", len(xor_data) + len(and_data))
    biXPelsPerMeter = struct.pack("<i", 0)
    biYPelsPerMeter = struct.pack("<i", 0)
    biClrUsed = struct.pack("<I", 0)
    biClrImportant = struct.pack("<I", 0)

    bmp_header = (
        biSize + biWidth + biHeight + biPlanes + biBitCount
        + biCompression + biSizeImage
        + biXPelsPerMeter + biYPelsPerMeter + biClrUsed + biClrImportant
    )
    image_data = bmp_header + xor_data + and_data

    # ICO directory entry (16 bytes)
    ico_dir = b""
    ico_dir += struct.pack("<B", width if width < 256 else 0)
    ico_dir += struct.pack("<B", height if height < 256 else 0)
    ico_dir += struct.pack("<B", 0)   # colours
    ico_dir += struct.pack("<B", 0)   # reserved
    ico_dir += struct.pack("<H", 1)   # planes
    ico_dir += struct.pack("<H", 32)  # bit count
    ico_dir += struct.pack("<I", len(image_data))
    ico_dir += struct.pack("<I", 22)  # offset

    # ICO header
    header = struct.pack("<H", 0)  # reserved
    header += struct.pack("<H", 1)  # ICO type
    header += struct.pack("<H", 1)  # count

    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(header + ico_dir + image_data)
    print(f"Placeholder icon created at {output.resolve()}")


if __name__ == "__main__":
    make_placeholder_ico()
