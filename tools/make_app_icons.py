#!/usr/bin/env python3
"""Generate the web app icons into app/static/icons (needs Pillow): teal rounded square with a white magnifier.
icon-maskable-512 is full-bleed with the artwork inside the central safe zone; apple-touch-icon is full-bleed."""
import os
from PIL import Image, ImageDraw

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "static", "icons")
TEAL, WHITE = (31, 111, 92, 255), (255, 255, 255, 255)


def draw(size, rounded=True, scale=1.0):
    k = 4  # supersample
    n = size * k
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if rounded:
        d.rounded_rectangle([0, 0, n - 1, n - 1], radius=int(n * 0.22), fill=TEAL)
    else:
        d.rectangle([0, 0, n, n], fill=TEAL)

    def p(v):  # artwork coordinate (0..1) to pixels, scaled around the centre
        return (0.5 + (v - 0.5) * scale) * n

    cx = cy = 0.44
    r, ring_w, hw = 0.22, 0.075, 0.09
    ring = [p(cx - r), p(cy - r), p(cx + r), p(cy + r)]
    d.ellipse(ring, outline=WHITE, width=max(2, int(ring_w * scale * n)))
    x0, y0 = cx + r * 0.72, cy + r * 0.72
    d.line([p(x0), p(y0), p(0.80), p(0.80)], fill=WHITE, width=max(2, int(hw * scale * n)))
    return img.resize((size, size), Image.LANCZOS)


os.makedirs(OUT, exist_ok=True)
draw(192).save(os.path.join(OUT, "icon-192.png"))
draw(512).save(os.path.join(OUT, "icon-512.png"))
draw(512, rounded=False, scale=0.72).save(os.path.join(OUT, "icon-maskable-512.png"))
draw(180, rounded=False, scale=0.86).save(os.path.join(OUT, "apple-touch-icon.png"))
draw(32).save(os.path.join(OUT, "favicon-32.png"))
print("icons written to", OUT)
