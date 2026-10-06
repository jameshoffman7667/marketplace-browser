#!/usr/bin/env python3
"""Generate the extension's PNG icons (stdlib only): teal rounded square with a white magnifier."""
import math, struct, sys, zlib

def png(size):
    rows = []
    r_corner = size * 0.22
    cx, cy, ring_r, ring_w = size * 0.44, size * 0.44, size * 0.22, max(1.2, size * 0.075)
    hx0, hy0, hx1, hy1, hw = cx + ring_r * 0.72, cy + ring_r * 0.72, size * 0.80, size * 0.80, max(1.4, size * 0.09)
    for y in range(size):
        row = bytearray([0])
        for x in range(size):
            px, py = x + 0.5, y + 0.5
            # rounded-square mask
            dx = max(r_corner - px, 0, px - (size - r_corner)); dy = max(r_corner - py, 0, py - (size - r_corner))
            inside = math.hypot(dx, dy) <= r_corner
            if not inside:
                row += bytes([0, 0, 0, 0]); continue
            d = abs(math.hypot(px - cx, py - cy) - ring_r)
            # distance to handle segment
            vx, vy = hx1 - hx0, hy1 - hy0
            t = max(0, min(1, ((px - hx0) * vx + (py - hy0) * vy) / (vx * vx + vy * vy)))
            dh = math.hypot(px - (hx0 + t * vx), py - (hy0 + t * vy))
            white = d <= ring_w / 2 or dh <= hw / 2
            row += bytes([255, 255, 255, 255]) if white else bytes([31, 111, 92, 255])
        rows.append(bytes(row))
    raw = b"".join(rows)
    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))

out = sys.argv[1] if len(sys.argv) > 1 else "extension/icons"
for s in (16, 32, 48, 128):
    open(f"{out}/icon{s}.png", "wb").write(png(s))
print("icons written")
