#!/usr/bin/env python3
"""Browser layout and PWA test (Playwright/Chromium): phone, tablet, desktop, 320 px, service worker, offline, Apify test dialog."""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import json, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import demo_server
from playwright.sync_api import sync_playwright

fails = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail and not ok else ""))
    if not ok:
        fails.append(name)


class FakeApify(BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        body = json.dumps([{"id": "1", "listingUrl": "https://www.facebook.com/marketplace/item/1", "marketplace_listing_title": "Standing desk demo",
                            "listing_price": {"amount": "65.00"}, "location": {"reverse_geocode": {"city": "Springfield", "state": "OH"}}}]).encode()
        self.send_response(201); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body)))
        self.end_headers(); self.wfile.write(body)

    def log_message(self, *a):
        pass


threading.Thread(target=HTTPServer(("127.0.0.1", 18311), FakeApify).serve_forever, daemon=True).start()
os.environ["APIFY_BASE"] = "http://127.0.0.1:18311"
p, base, d, pw = demo_server.start(18310)
try:
    with sync_playwright() as pl:
        b = pl.chromium.launch()
        errors = []

        def login(ctx, vp=None):
            pg = ctx.new_page()
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.on("console", lambda m: errors.append(m.text) if m.type == "error" and "Failed to load resource" not in m.text else None)
            pg.goto(base)
            pg.fill("input[type=password]", pw); pg.keyboard.press("Enter")
            pg.wait_for_selector("nav button"); pg.wait_for_selector(".item")
            return pg

        for label, w, h in (("phone 390x844", 390, 844), ("narrow 320x640", 320, 640), ("tablet 768x1024", 768, 1024),
                            ("desktop 1440x900", 1440, 900)):
            ctx = b.new_context(viewport={"width": w, "height": h}, has_touch=w < 768, is_mobile=w < 768)
            pg = login(ctx)
            for tab in ("feed", "searches", "sources", "settings"):
                pg.click(f'nav button[data-t="{tab}"]'); pg.wait_for_timeout(250)
                sw_ = pg.evaluate("document.documentElement.scrollWidth")
                check(f"{label} {tab}: no horizontal scroll", sw_ <= w, f"scrollWidth {sw_}")
            nav = pg.eval_on_selector(".side", "e => { const r = e.getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; }")
            if w < 768:
                check(f"{label}: bottom navigation", nav[1] > h / 2 and nav[2] >= w - 1, str(nav))
                pg.click('nav button[data-t="feed"]'); pg.wait_for_selector(".item")
                small = pg.evaluate("""() => [...document.querySelectorAll('nav button, #main button, #main a.btn, #main select')]
                    .filter(e => e.offsetParent).map(e => e.getBoundingClientRect()).filter(r => r.height < 43.5).length""")
                check(f"{label}: touch targets at least 44 px", small == 0, f"{small} too small")
            else:
                check(f"{label}: side navigation", nav[0] == 0 and nav[3] >= h - 1, str(nav))
            ctx.close()

        # service worker, offline page, install affordance, back navigation, Apify test dialog
        ctx = b.new_context(viewport={"width": 1280, "height": 800}, service_workers="allow")
        pg = login(ctx)
        pg.wait_for_function("navigator.serviceWorker.getRegistration().then(r => !!(r && r.active))", timeout=10000)
        check("service worker registered and active", True)
        check("manifest link present", pg.evaluate("!!document.querySelector('link[rel=manifest]')"))
        pg.click('nav button[data-t="settings"]'); pg.wait_for_timeout(300)
        check("install card shown in settings", "Install as an app" in pg.inner_text("#main"))
        pg.click('nav button[data-t="searches"]'); pg.wait_for_timeout(200)
        pg.go_back(); pg.wait_for_timeout(300)
        check("browser back returns to previous tab", "Install as an app" in pg.inner_text("#main"))
        pg.keyboard.press("1"); pg.wait_for_timeout(300)
        check("keyboard shortcut 1 opens feed", pg.locator(".item").count() > 0)
        ctx.set_offline(True)
        pg2 = ctx.new_page(); pg2.goto(base + "/")
        pg2.wait_for_timeout(500)
        txt = pg2.inner_text("body").lower()
        check("offline: app shell or offline page shown", len(txt) > 0 and ("offline" in txt or "marketplace" in txt), txt[:80])
        ctx.set_offline(False)

        pg.click('nav button[data-t="sources"]'); pg.wait_for_timeout(300)
        # Apify test dialog (add a source through the API, test it from the UI)
        pg.evaluate("""() => fetch('/api/sources', {method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name: 'Apify demo', type: 'apify', config: {token: 'x', daily_cap: 100}})})""")
        pg.reload(); pg.wait_for_selector("nav button"); pg.click('nav button[data-t="sources"]'); pg.wait_for_selector("[data-test]")
        pg.click("[data-test]")
        pg.wait_for_selector("dialog[open] .raw, dialog[open] h2", timeout=8000)
        dtxt = pg.inner_text("dialog[open]")
        check("Apify test dialog shows result", "Apify test" in dtxt and "Standing desk demo" in dtxt and "Nothing was saved" in dtxt, dtxt[:120])
        check("Apify test dialog lists raw fields", "marketplace_listing_title" in dtxt)
        ctx.close()
        b.close()
    check("no console or page errors", not errors, "; ".join(errors)[:300])
finally:
    p.terminate()
print("\n%d failed" % len(fails) if fails else "\nall passed")
sys.exit(1 if fails else 0)
