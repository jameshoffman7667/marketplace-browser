"""Generate manifest screenshots from demo data: app/static/screenshots/wide.png and narrow.png."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import demo_server
from playwright.sync_api import sync_playwright

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "static", "screenshots")
p, base, d, pw = demo_server.start(18301)
try:
    with sync_playwright() as pl:
        b = pl.chromium.launch()
        for name, vp in (("wide", (1280, 720)), ("narrow", (540, 960))):
            ctx = b.new_context(viewport={"width": vp[0], "height": vp[1]}, device_scale_factor=1)
            pg = ctx.new_page(); pg.goto(base)
            pg.fill("input[type=password]", pw); pg.keyboard.press("Enter")
            pg.wait_for_selector("nav button"); pg.wait_for_selector(".item", timeout=5000)
            pg.screenshot(path=os.path.join(OUT, name + ".png")); ctx.close()
        b.close()
finally:
    p.terminate()
print("ok")
