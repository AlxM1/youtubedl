#!/usr/bin/env python3
"""
Generate PWA icons (192x192 and 512x512) as valid PNG files.
Uses only Python stdlib: struct, zlib, os. No pip packages needed.

Icon design: purple (#6c5ce7) rounded square with a white play triangle.
"""

import struct
import zlib
import os


def make_chunk(chunk_type, data):
    """Build a PNG chunk: length + type + data + CRC."""
    raw = chunk_type + data
    crc = struct.pack(">I", zlib.crc32(raw) & 0xFFFFFFFF)
    return struct.pack(">I", len(data)) + raw + crc


def make_png(width, height, rgba_rows):
    """
    Assemble a complete PNG file from raw RGBA scanline data.
    rgba_rows: list of bytes objects, one per row, each width*4 bytes.
    """
    # PNG signature
    sig = b"\x89PNG\r\n\x1a\n"

    # IHDR: width, height, bit-depth=8, color-type=6 (RGBA), compress=0, filter=0, interlace=0
    ihdr = make_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))

    # IDAT: each scanline is preceded by a filter byte (0 = None)
    raw = bytearray()
    for row in rgba_rows:
        raw.append(0)          # filter: None
        raw.extend(row)
    compressed = zlib.compress(bytes(raw), 9)
    idat = make_chunk(b"IDAT", compressed)

    # IEND
    iend = make_chunk(b"IEND", b"")

    return sig + ihdr + idat + iend


def in_rounded_rect(x, y, size, radius):
    """Return True if (x, y) is inside a rounded rectangle [0, size) with given corner radius."""
    # Interior regions never need a circle check
    if radius <= x <= size - 1 - radius or radius <= y <= size - 1 - radius:
        return True
    # Corner regions
    # Determine which corner center to test against
    if x < radius:
        cx = radius
    else:
        cx = size - 1 - radius
    if y < radius:
        cy = radius
    else:
        cy = size - 1 - radius
    dx = x - cx
    dy = y - cy
    return dx * dx + dy * dy <= radius * radius


def in_play_triangle(nx, ny):
    """
    Return True if normalised coordinate (nx, ny) in [-1, 1] is inside
    the play-button triangle.  The triangle is:
        A = (-0.28, -0.36)   top-left vertex
        B = (-0.28,  0.36)   bottom-left vertex
        C = ( 0.38,  0.00)   right vertex
    Shifted slightly right of center so it looks visually balanced.
    """
    # Pre-baked edge constants (from the three vertices)
    # Using cross-product sign test (same-side method)
    ax, ay = -0.28, -0.36
    bx, by = -0.28,  0.36
    cx, cy =  0.38,  0.00

    # d1 = sign(P, A, B)
    d1 = (nx - bx) * (ay - by) - (ax - bx) * (ny - by)
    # d2 = sign(P, B, C)
    d2 = (nx - cx) * (by - cy) - (bx - cx) * (ny - cy)
    # d3 = sign(P, C, A)
    d3 = (nx - ax) * (cy - ay) - (cx - ax) * (ny - ay)

    has_neg = (d1 < 0) or (d2 < 0) or (d3 < 0)
    has_pos = (d1 > 0) or (d2 > 0) or (d3 > 0)
    return not (has_neg and has_pos)


def generate_icon(size):
    """
    Render one icon and return a list of scanline byte-rows (RGBA).
    """
    purple = bytes((108, 92, 231, 255))   # #6c5ce7
    white  = bytes((255, 255, 255, 255))
    transp = bytes((0, 0, 0, 0))

    radius = size // 8
    half   = size / 2.0
    inv    = 1.0 / half          # multiply is faster than divide in the loop

    rows = []
    for y in range(size):
        row = bytearray()
        ny = (y - half) * inv
        for x in range(size):
            if not in_rounded_rect(x, y, size, radius):
                row.extend(transp)
            else:
                nx = (x - half) * inv
                if in_play_triangle(nx, ny):
                    row.extend(white)
                else:
                    row.extend(purple)
        rows.append(bytes(row))
    return rows


def main():
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "icons")
    os.makedirs(out_dir, exist_ok=True)

    targets = [
        (192, os.path.join(out_dir, "icon-192.png")),
        (512, os.path.join(out_dir, "icon-512.png")),
    ]

    for size, path in targets:
        print(f"Generating {size}x{size} icon ...")
        rows = generate_icon(size)
        data = make_png(size, size, rows)
        with open(path, "wb") as f:
            f.write(data)
        print(f"  -> {path}  ({len(data):,} bytes)")

    print("Done.")


if __name__ == "__main__":
    main()
