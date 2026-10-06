#!/usr/bin/env python3
"""End-to-end smoke test. Uses only a local fake feed and webhook: no internet."""
import http.cookiejar
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_PORT, FEED_PORT, HOOK_PORT = 18080, 18081, 18082
BASE = f"http://127.0.0.1:{APP_PORT}"

# ---- fake feed ---------------------------------------------------------
FEED_ITEMS = []
FEED_REQUESTS = []


def rss():
    items = "".join(
        f"<item><title>{t}</title><link>http://example.test/{i}</link><guid>{i}</guid>"
        f"<description>{t} in good shape</description><georss:point>{lat} {lon}</georss:point></item>"
        for i, t, lat, lon in FEED_ITEMS)
    return ('<?xml version="1.0"?><rss version="2.0" xmlns:georss="http://www.georss.org/georss">'
            f"<channel><title>t</title>{items}</channel></rss>").encode()


class FeedH(BaseHTTPRequestHandler):
    def do_GET(self):
        FEED_REQUESTS.append(self.path)
        body = rss()
        self.send_response(200)
        self.send_header("Content-Type", "application/rss+xml")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


HOOKS = []


class HookH(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        HOOKS.append(json.loads(self.rfile.read(n)))
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *a):
        pass


def serve(port, handler):
    srv = HTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


# ---- client ------------------------------------------------------------
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def call(method, path, body=None, headers=None, use_cookie=True):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json", **(headers or {})})
    op = opener if use_cookie else urllib.request.build_opener()
    try:
        with op.open(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def wait_for(cond, secs=15, what=""):
    end = time.time() + secs
    while time.time() < end:
        try:
            if cond():
                return True
        except (urllib.error.URLError, ConnectionError):
            pass
        time.sleep(0.25)
    raise AssertionError("timed out waiting for " + what)


failures = []


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        failures.append(name)


def main():
    serve(FEED_PORT, FeedH)
    serve(HOOK_PORT, HookH)
    tmp = tempfile.mkdtemp()
    env = dict(os.environ, DATA_DIR=tmp, PORT=str(APP_PORT), APP_PASSWORD="pw123", INGEST_TOKEN="tok123",
               MIN_POLL_MINUTES="1")
    proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "app", "server.py")], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        wait_for(lambda: call("GET", "/api/health")[0] == 200, 10, "server start")

        s, hz = call("GET", "/api/health")
        check("health reports version", hz.get("version") == open(os.path.join(ROOT, "VERSION")).read().strip(), str(hz))
        req = urllib.request.Request(BASE + "/api/ingest", method="OPTIONS", headers={
            "Origin": "chrome-extension://abc", "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-ingest-token"})
        with urllib.request.urlopen(req) as r:
            check("CORS preflight for extension", r.status == 204 and r.headers.get("Access-Control-Allow-Origin") == "*"
                  and "x-ingest-token" in r.headers.get("Access-Control-Allow-Headers", "").lower())
        req = urllib.request.Request(BASE + "/api/settings", method="OPTIONS")
        try:
            urllib.request.urlopen(req)
            check("no CORS on session endpoints", False)
        except urllib.error.HTTPError as e:
            check("no CORS on session endpoints", e.code == 404)
        s, _ = call("GET", "/api/searches")
        check("API requires login", s == 401)
        s, _ = call("POST", "/api/login", {"password": "wrong"})
        check("wrong password rejected", s == 401)
        s, _ = call("POST", "/api/login", {"password": "pw123"})
        check("login works", s == 200)
        with urllib.request.urlopen(BASE + "/") as r:
            check("web UI served", b"Classifieds Tracker" in r.read())

        # Global location: Toronto, 50 km
        s, st = call("PUT", "/api/settings", {"location_label": "Toronto, ON", "lat": "43.6532", "lon": "-79.3832",
                                              "radius_km": "50", "webhook_url": f"http://127.0.0.1:{HOOK_PORT}/h"})
        check("save global location", s == 200 and st["lat"] == "43.6532")

        s, src = call("POST", "/api/sources", {
            "name": "Fake feed", "type": "feed",
            "config": {"url_template": f"http://127.0.0.1:{FEED_PORT}/rss?q={{q}}&lat={{lat}}&lon={{lon}}&r={{radius_km}}"}})
        check("create feed source", s == 200)

        # Existing listings before the search exists
        FEED_ITEMS.extend([(1, "Standing desk oak", 43.70, -79.40), (2, "Standing desk far away", 49.28, -123.12)])
        s, srch = call("POST", "/api/searches", {"keywords": "standing desk", "exclude": "broken", "price_max": 500,
                                                  "alert_mode": "instant", "source_ids": [src["id"]]})
        check("create search", s == 200)
        call("POST", f"/api/sources/{src['id']}/run")
        time.sleep(1)
        s, feed = call("GET", "/api/feed")
        titles = [i["title"] for i in feed["items"]]
        check("baseline lists nearby listing", "Standing desk oak" in titles, str(titles))
        check("out-of-area listing hidden", "Standing desk far away" not in titles, str(titles))
        check("baseline listings are not flagged new", not any(i["is_new"] for i in feed["items"]))
        time.sleep(1.5)
        check("no alerts for baseline", len(HOOKS) == 0, str(HOOKS))
        check("feed URL got location placeholders", any("lat=43.6532" in p and "q=standing+desk" in p for p in FEED_REQUESTS),
              str(FEED_REQUESTS))

        # New listings: one near and matching, one broken (excluded), one far, one unrelated
        FEED_ITEMS.extend([(3, "Standing desk adjustable", 43.66, -79.39), (4, "Standing desk broken frame", 43.66, -79.39),
                           (5, "Standing desk Montreal", 45.50, -73.57), (6, "Bicycle", 43.66, -79.39)])
        call("POST", f"/api/sources/{src['id']}/run")
        call("PUT", "/api/settings", {})  # wakes the poller so it dispatches now
        wait_for(lambda: len(HOOKS) >= 1, 12, "webhook alert")
        time.sleep(1)
        check("exactly one alert", len(HOOKS) == 1, str(HOOKS))
        check("alert is the near, matching listing",
              HOOKS and [l["title"] for l in HOOKS[0]["listings"]] == ["Standing desk adjustable"], str(HOOKS))
        s, feed = call("GET", "/api/feed")
        check("new listing flagged new", any(i["is_new"] and i["title"] == "Standing desk adjustable" for i in feed["items"]))

        # Change the global location: all searches follow, no alert flood
        before = len(HOOKS)
        FEED_REQUESTS.clear()
        call("PUT", "/api/settings", {"location_label": "Vancouver, BC", "lat": "49.2827", "lon": "-123.1207", "radius_km": "50"})
        wait_for(lambda: any("lat=49.2827" in p for p in FEED_REQUESTS), 12, "feed re-query with new location")
        s, feed = call("GET", "/api/feed")
        titles = [i["title"] for i in feed["items"]]
        check("location change swaps results", titles == ["Standing desk far away"], str(titles))
        time.sleep(1.5)
        check("location change causes no alerts", len(HOOKS) == before, str(HOOKS[before:]))

        # Ingest API (browser extension path); let the search cover all sources
        call("PUT", f"/api/searches/{srch['id']}", {"keywords": "standing desk", "exclude": "broken", "price_max": 500,
                                                     "alert_mode": "instant", "source_ids": []})
        s, _ = call("POST", "/api/ingest", {"source": "FB", "listings": []}, use_cookie=False)
        check("ingest needs token", s == 401)
        hdr = {"X-Ingest-Token": "tok123"}
        s, r = call("POST", "/api/ingest", {"source": "Facebook Marketplace", "listings": [
            {"id": "a1", "url": "https://fb.test/a1", "title": "Standing desk old", "price": "$120", "lat": 49.27, "lon": -123.1}]},
            headers=hdr, use_cookie=False)
        check("first ingest is baseline", s == 200 and r["stored"] == 1, str(r))
        before = len(HOOKS)
        s, r = call("POST", "/api/ingest", {"source": "Facebook Marketplace", "listings": [
            {"id": "a2", "url": "https://fb.test/a2", "title": "Standing desk new", "price": 90, "lat": 49.27, "lon": -123.1}]},
            headers=hdr, use_cookie=False)
        wait_for(lambda: len(HOOKS) > before, 12, "ingest alert")
        check("second ingest alerts once", len(HOOKS) == before + 1 and HOOKS[-1]["count"] == 1, str(HOOKS[-1]))
        s, tasks = call("GET", "/api/extension/tasks", headers=hdr, use_cookie=False)
        check("extension tasks endpoint", s == 200 and "tasks" in tasks)

        # Settings secrets are masked
        s, st = call("PUT", "/api/settings", {"smtp_password": "secret"})
        check("secret masked", st["smtp_password"] == "********")

        # Email alert parsing (unit)
        os.environ["DATA_DIR"] = tempfile.mkdtemp()
        sys.path.insert(0, os.path.join(ROOT, "app"))
        import server  # noqa: E402
        raw = (b"From: alerts@kijiji.ca\r\nSubject: New ads\r\nContent-Type: text/html; charset=utf-8\r\n\r\n"
               b"<html><body><a href='https://www.kijiji.ca/v-desks/toronto/oak-desk/123?x=1'><img src='http://i/1.jpg' alt='Oak desk'>"
               b"Oak desk</a> $150.00 Toronto <a href='https://www.kijiji.ca/v-desks/toronto/oak-desk/123?x=2'>again</a>"
               b"<a href='https://example.com/unsub'>Unsubscribe</a></body></html>")
        items = server.parse_alert_email(raw, None)
        check("email parser finds one deduped listing", len(items) == 1, str(items))
        check("email parser extracts title, price and image",
              items and items[0]["title"].startswith("Oak desk") and items[0]["price"] == 150.0 and items[0]["image"] == "http://i/1.jpg",
              str(items))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        out = proc.stdout.read() if proc.stdout else ""
        if "Traceback" in out:
            print("SERVER ERRORS:\n" + out[-2000:])
            failures.append("server traceback")
    print("\n" + ("ALL PASSED" if not failures else f"{len(failures)} FAILED: {failures}"))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
