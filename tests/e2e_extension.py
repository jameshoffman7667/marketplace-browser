#!/usr/bin/env python3
"""Loads the real extension into Chromium and drives it against fake Facebook/Kijiji pages.

www.facebook.com and www.kijiji.ca are mapped to a local HTTPS server with --host-resolver-rules, so the
extension's real host permissions, tab handling, injected extractor and server calls are all exercised.
The fixture markup is MY MODEL of those sites, not a copy of the live pages: this proves the plumbing and the
extractor logic, not that the live sites still match.

Needs: python3 playwright + Chromium (set CHROMIUM_PATH to override), openssl.
"""
import json
import os
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_PORT, FAKE_PORT = 18100, 18101
BASE = f"http://127.0.0.1:{APP_PORT}"
TOKEN = "e2e-token"
CHROMIUM = os.environ.get("CHROMIUM_PATH") or next(
    (p for p in ["/opt/pw-browsers/chromium-1194/chrome-linux/chrome", "/opt/pw-browsers/chromium/chrome-linux/chrome"]
     if os.path.exists(p)), None)

FB_ITEMS = [
    ("1001", "CA$90", "CA$120", "Standing desk adjustable", "Toronto, ON"),
    ("1002", "CA$250", None, "Standing desk electric dual motor", "Mississauga, ON"),
    ("1003", "Free", None, "Standing desk frame only", "Toronto, ON"),
]


def fb_page(items):
    cards = ""
    for i, price, old, title, loc in items:
        oldspan = f"<span>{old}</span>" if old else ""
        cards += (f'<div class="x9f"><a href="/marketplace/item/{i}/?ref=search&amp;referral_code=abc" class="x1lliihq">'
                  f'<div><img src="https://www.facebook.com/img/{i}.jpg"></div>'
                  f"<div><span>{price}</span>{oldspan}<span>{title}</span><span>{loc}</span></div></a></div>")
    # same card twice (virtualised lists repeat), plus an unrelated link
    return f'<html><body><a href="/marketplace/you">Your listings</a>{cards}{cards}</body></html>'


KIJIJI = """<html><body><ul>
<li data-testid="listing-card"><a href="/v-desks/city-of-toronto/oak-standing-desk/1700000001"><img src="https://www.kijiji.ca/i/1.jpg">
<div data-testid="listing-title">Oak standing desk</div><div data-testid="listing-price">$150.00</div>
<div data-testid="listing-location">Toronto</div></a></li>
<li data-testid="listing-card"><a href="/v-desks/markham-york-region/sit-stand-desk/1700000002">
<p>Sit or standing desk</p><p>$1,200.00</p><p>Markham</p></a></li></ul></body></html>"""

LOGIN = '<html><body><form action="/login/"><input name="email"><input name="pass" type="password"></form></body></html>'

state = {"fb": list(FB_ITEMS[:2]), "hits": []}


class Fake(BaseHTTPRequestHandler):
    def do_GET(self):
        host = (self.headers.get("Host") or "").split(":")[0]
        state["hits"].append(host + self.path)
        if host == "www.kijiji.ca":
            body = KIJIJI
        elif "login-wall" in self.path:
            body = LOGIN
        else:
            body = fb_page(state["fb"])
        data = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


def api(method, path, body=None, headers=None, cookie=None):
    h = {"Content-Type": "application/json", **(headers or {})}
    if cookie:
        h["Cookie"] = cookie
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"{}"), r.headers
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}"), e.headers


failures = []


def wait_text(page, sel, needle, secs=12):
    """Poll an element's text (wait_for_function would be blocked by the extension pages' CSP)."""
    end = time.time() + secs
    while time.time() < end:
        if needle in page.inner_text(sel):
            return True
        time.sleep(0.2)
    raise AssertionError(f"timed out waiting for {needle!r} in {sel}: {page.inner_text(sel)!r}")


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        failures.append(name)


def main():
    if not CHROMIUM:
        print("SKIP: no Chromium found (set CHROMIUM_PATH)")
        return
    tmp = tempfile.mkdtemp()
    # self-signed cert valid for the two mapped hostnames
    key, crt = os.path.join(tmp, "k.pem"), os.path.join(tmp, "c.pem")
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", key, "-out", crt, "-days", "2",
                    "-subj", "/CN=www.facebook.com", "-addext", "subjectAltName=DNS:www.facebook.com,DNS:www.kijiji.ca"],
                   check=True, capture_output=True)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(crt, key)
    fake = HTTPServer(("127.0.0.1", FAKE_PORT), Fake)
    fake.socket = ctx.wrap_socket(fake.socket, server_side=True)
    threading.Thread(target=fake.serve_forever, daemon=True).start()

    env = dict(os.environ, DATA_DIR=os.path.join(tmp, "data"), PORT=str(APP_PORT), APP_PASSWORD="pw", INGEST_TOKEN=TOKEN)
    srv = subprocess.Popen([sys.executable, os.path.join(ROOT, "app", "server.py")], env=env,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        for _ in range(40):
            try:
                if api("GET", "/api/health")[0] == 200:
                    break
            except Exception:
                time.sleep(0.25)
        s, _, hdr = api("POST", "/api/login", {"password": "pw"})
        cookie = hdr["Set-Cookie"].split(";")[0]
        A = lambda m, p, b=None: api(m, p, b, cookie=cookie)[:2]

        A("PUT", "/api/settings", {"location_label": "Toronto, ON", "lat": "43.6532", "lon": "-79.3832", "radius_km": "40"})
        s, fbsrc = A("POST", "/api/sources", {"name": "Facebook Marketplace", "type": "ingest", "config": {
            "url_template": "https://www.facebook.com/marketplace/{city_slug}/search?query={q}&radius={radius_km}&sortBy=creation_time_descend&exact=false"}})
        s, kjsrc = A("POST", "/api/sources", {"name": "Kijiji", "type": "ingest", "config": {}})
        s, srch = A("POST", "/api/searches", {"keywords": "standing desk", "alert_mode": "off"})

        s, tasks, _ = api("GET", "/api/extension/tasks", headers={"X-Ingest-Token": TOKEN})
        check("server queues the Facebook search URL with global location",
              len(tasks["tasks"]) == 1 and "/marketplace/toronto/search?query=standing+desk&radius=40" in tasks["tasks"][0]["url"],
              str(tasks))

        ext = os.path.join(ROOT, "extension")
        with sync_playwright() as p:
            browser = p.chromium.launch_persistent_context(
                os.path.join(tmp, "profile"), executable_path=CHROMIUM, headless=False,
                args=["--headless=new", f"--disable-extensions-except={ext}", f"--load-extension={ext}",
                      f"--host-resolver-rules=MAP www.facebook.com 127.0.0.1:{FAKE_PORT}, MAP www.kijiji.ca 127.0.0.1:{FAKE_PORT}",
                      "--ignore-certificate-errors", "--no-sandbox", "--no-proxy-server"])
            sw = browser.service_workers[0] if browser.service_workers else browser.wait_for_event("serviceworker", timeout=15000)
            ext_id = sw.url.split("/")[2]
            check("extension service worker loaded", sw.url.endswith("/background.js"))

            opts = browser.new_page()
            opts.goto(f"chrome-extension://{ext_id}/options.html")
            opts.fill("#url", BASE)
            opts.fill("#tok", "wrong-token")
            opts.click("#test")
            wait_text(opts, "#msg", "rejected")
            check("options: bad token reported", True)
            opts.fill("#tok", TOKEN)
            opts.click("#test")
            wait_text(opts, "#msg", "Connected")
            msg = opts.inner_text("#msg")
            check("options: connection test passes and counts queued pages", "1 search page" in msg, msg)

            # Run all searches (opens the Facebook search page in a tab, scrolls, extracts, posts)
            r = opts.evaluate("chrome.runtime.sendMessage({type:'run-now'})")
            res = (r.get("results") or [{}])[0]
            check("run-now: no error", not r.get("error") and not res.get("error"), json.dumps(r))
            check("run-now: found the 2 distinct cards (duplicates merged)", res.get("found") == 2, json.dumps(res))
            s, feed = A("GET", "/api/feed?state=all")
            by = {i["title"]: i for i in feed["items"]}
            check("feed has Facebook listings", set(by) == {"Standing desk adjustable", "Standing desk electric dual motor"}, str(list(by)))
            d = by.get("Standing desk adjustable", {})
            check("price parsed, old price ignored", d.get("price") == 90, str(d))
            check("currency not required, location kept", d.get("location") == "Toronto, ON", str(d))
            check("canonical item URL (tracking params stripped)", d.get("url") == "https://www.facebook.com/marketplace/item/1001/", str(d.get("url")))
            check("first run is baseline (nothing flagged new)", not any(i["is_new"] for i in feed["items"]))

            # A new listing appears; the next run should flag exactly that one
            state["fb"] = list(FB_ITEMS)
            r = opts.evaluate("chrome.runtime.sendMessage({type:'run-now'})")
            s, feed = A("GET", "/api/feed?state=all")
            new = [i["title"] for i in feed["items"] if i["is_new"]]
            check("second run flags only the new listing", new == ["Standing desk frame only"], str(new))
            check("free listing has price 0", {i["title"]: i for i in feed["items"]}.get("Standing desk frame only", {}).get("price") == 0)

            # Not-signed-in page produces a clear error and posts nothing
            before = len(feed["items"])
            page = browser.new_page()
            page.goto("https://www.facebook.com/marketplace/login-wall")
            tab_id = opts.evaluate("chrome.tabs.query({url:'https://www.facebook.com/marketplace/login-wall*'}).then(t=>t[0].id)")
            cap = opts.evaluate(f"chrome.runtime.sendMessage({{type:'capture-tab', tabId:{tab_id}, url:'https://www.facebook.com/marketplace/login-wall'}})")
            check("login wall detected", "Not signed in" in (cap.get("error") or ""), json.dumps(cap))
            page.close()

            # Manual capture of a Kijiji page (no task): uses the Kijiji source name
            page = browser.new_page()
            page.goto("https://www.kijiji.ca/b-desks/toronto/standing-desk/k0c0l0")
            tab_id = opts.evaluate("chrome.tabs.query({url:'https://www.kijiji.ca/*'}).then(t=>t[0].id)")
            cap = opts.evaluate(f"chrome.runtime.sendMessage({{type:'capture-tab', tabId:{tab_id}, url:'https://www.kijiji.ca/b-desks/toronto/standing-desk/k0c0l0'}})")
            check("kijiji capture finds 2 listings", cap.get("found") == 2 and cap.get("source") == "Kijiji", json.dumps(cap))
            s, feed = A("GET", "/api/feed?state=all")
            kj = {i["title"]: i for i in feed["items"] if i["source"] == "Kijiji"}
            check("kijiji data-testid card parsed", kj.get("Oak standing desk", {}).get("price") == 150, str(kj))
            check("kijiji fallback (no data-testid) parsed, thousands separator",
                  kj.get("Sit or standing desk", {}).get("price") == 1200 and kj["Sit or standing desk"].get("location") == "Markham", str(kj))
            page.close()

            # Popup renders the last run
            pop = browser.new_page()
            pop.goto(f"chrome-extension://{ext_id}/popup.html")
            pop.wait_for_selector("#last .res")
            check("popup shows last run results", "found" in pop.inner_text("#last"))
            check("popup knows it is configured", BASE in pop.inner_text("#conn"))

            # Auto mode schedules an alarm with the 15 minute floor
            opts.fill("#int", "5")
            opts.check("#auto")
            opts.click("#save")
            time.sleep(1)
            alarm = opts.evaluate("chrome.alarms.get('run')")
            check("auto mode creates an alarm", bool(alarm))
            check("interval floor is 15 minutes", alarm and alarm.get("periodInMinutes") == 15, str(alarm))
            browser.close()
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=5)
        except subprocess.TimeoutExpired:
            srv.kill()
        out = srv.stdout.read() if srv.stdout else ""
        if "Traceback" in out:
            print("SERVER ERRORS:\n" + out[-1500:])
            failures.append("server traceback")
    print("\n" + ("ALL PASSED" if not failures else f"{len(failures)} FAILED: {failures}"))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
