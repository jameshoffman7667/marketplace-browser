"""Apify source test: a fake Apify API stands in for api.apify.com. Run: python3 tests/apify_test.py"""
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
APP_PORT, FAKE_PORT, HOOK_PORT = 18110, 18111, 18112
BASE = f"http://127.0.0.1:{APP_PORT}"
CALLS, HOOKS, ITEMS = [], [], []
MODE = {"status": 200}


def item(i, title, price="65.00", sold=False):
    return {"id": str(i), "listingUrl": f"https://www.facebook.com/marketplace/item/{i}",
            "marketplace_listing_title": title, "is_sold": sold,
            "listing_price": {"amount": price, "formatted_amount": "$" + price.split(".")[0]},
            "primary_listing_photo": {"image": {"uri": f"https://img.test/{i}.jpg"}},
            "location": {"reverse_geocode": {"city": "Toronto", "state": "ON"}}}


class Fake(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        CALLS.append({"path": self.path, "auth": self.headers.get("Authorization"), "body": json.loads(self.rfile.read(n))})
        if MODE["status"] != 200:
            body = json.dumps({"error": {"message": "Monthly usage hard limit exceeded"}}).encode()
            self.send_response(MODE["status"])
        else:
            body = json.dumps(ITEMS).encode()
            self.send_response(201)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


class Hook(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        HOOKS.append(json.loads(self.rfile.read(n)))
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *a):
        pass


jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def call(method, path, body=None):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                                 method=method, headers={"Content-Type": "application/json"})
    try:
        with opener.open(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


failures = []


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        failures.append(name)


def main():
    for port, h in ((FAKE_PORT, Fake), (HOOK_PORT, Hook)):
        srv = HTTPServer(("127.0.0.1", port), h)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
    env = dict(os.environ, DATA_DIR=tempfile.mkdtemp(), PORT=str(APP_PORT), APP_PASSWORD="pw", MIN_POLL_MINUTES="1",
               APIFY_BASE=f"http://127.0.0.1:{FAKE_PORT}")
    proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "app", "server.py")], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        for _ in range(40):
            try:
                urllib.request.urlopen(BASE + "/api/health", timeout=2)
                break
            except Exception:  # noqa: BLE001
                time.sleep(0.25)
        call("POST", "/api/login", {"password": "pw"})
        call("PUT", "/api/settings", {"location_label": "Toronto, ON", "lat": "43.6532", "lon": "-79.3832",
                                      "radius_km": "40", "webhook_url": f"http://127.0.0.1:{HOOK_PORT}/h"})

        s, _ = call("POST", "/api/sources", {"name": "Apify FB", "type": "apify", "config": {}})
        check("token is required", s == 400)
        s, src = call("POST", "/api/sources", {"name": "Apify FB", "type": "apify", "config": {
            "token": "apify_api_SECRET", "interval_minutes": 5, "results_limit": 25, "daily_cap": 3}})
        check("create apify source", s == 200 and src["type"] == "apify", str(src))
        check("token masked in API", src["config"]["token"] == "********")
        check("interval clamped to 15", src["config"]["interval_minutes"] == 15)
        time.sleep(1)
        # adding the source may already trigger a first run (nothing to search yet), so count from here
        s, srch = call("POST", "/api/searches", {"keywords": "standing desk", "alert_mode": "instant", "source_ids": [src["id"]]})
        check("create search", s == 200)

        CALLS.clear()
        ITEMS[:] = [item(1, "Standing desk oak"), item(2, "Standing desk sold", sold=True), item(3, "Office chair")]
        s, r = call("POST", f"/api/sources/{src['id']}/run")
        check("manual run succeeds", s == 200 and r["last_error"] is None, str(r))
        check("one Apify call per search", len(CALLS) == 1, str(CALLS))
        c = CALLS[0] if CALLS else {"path": "", "auth": "", "body": {}}
        check("bearer token sent, not in URL", c["auth"] == "Bearer apify_api_SECRET" and "SECRET" not in c["path"])
        check("actor path uses ~", "/v2/acts/apify~facebook-marketplace-scraper/run-sync-get-dataset-items" in c["path"], c["path"])
        url = (c["body"].get("startUrls") or [{}])[0].get("url", "")
        check("start URL uses global location and keywords",
              "/marketplace/toronto/search/" in url and "query=standing+desk" in url and "radius=40" in url, url)
        check("limits passed", c["body"].get("resultsLimit") == 25 and c["body"].get("includeListingDetails") is False, str(c["body"]))
        s, feed = call("GET", "/api/feed")
        titles = [i["title"] for i in feed["items"]]
        check("matching listing stored; sold and unrelated skipped", titles == ["Standing desk oak"], str(titles))
        li = feed["items"][0] if feed["items"] else {}
        check("fields mapped", li.get("price") == 65.0 and li.get("image") == "https://img.test/1.jpg"
              and li.get("location") == "Toronto, ON" and li.get("url", "").endswith("/item/1"), str(li))
        time.sleep(1.5)
        check("first run is baseline (no alert)", len(HOOKS) == 0, str(HOOKS))

        ITEMS.append(item(4, "Standing desk adjustable", "90.00"))
        s, r = call("POST", f"/api/sources/{src['id']}/run")
        deadline = time.time() + 15
        while time.time() < deadline and not HOOKS:
            call("PUT", "/api/settings", {})
            time.sleep(1)
        check("new listing alerts once", len(HOOKS) == 1 and [l["title"] for l in HOOKS[0]["listings"]] == ["Standing desk adjustable"], str(HOOKS))

        n = len(CALLS)
        call("PUT", "/api/settings", {"radius_km": "30"})
        time.sleep(3)
        check("settings change does not trigger a paid run", len(CALLS) == n, f"{n} -> {len(CALLS)}")

        s, srcs = call("GET", "/api/sources")
        a = [x for x in srcs if x["id"] == src["id"]][0]
        check("usage reported", a["usage"]["runs_24h"] >= 2 and a["usage"]["items_24h"] >= 3, str(a.get("usage")))

        s, r = call("POST", f"/api/sources/{src['id']}/run")  # third counted run (cap = 3 incl. earlier)
        s, r = call("POST", f"/api/sources/{src['id']}/run")
        check("daily cap blocks further runs", "cap reached" in (r.get("last_error") or ""), str(r.get("last_error")))
        capped = len(CALLS)
        call("POST", f"/api/sources/{src['id']}/run")
        check("no calls made once capped", len(CALLS) == capped)

        s, r = call("PUT", f"/api/sources/{src['id']}", {"name": "Apify FB", "type": "apify", "config": {
            "token": "********", "daily_cap": 100}})
        check("editing keeps stored token", s == 200)
        MODE["status"] = 402
        s, r = call("POST", f"/api/sources/{src['id']}/run")
        err = r.get("last_error") or ""
        check("402 reported clearly without leaking the token", "402" in err and "SECRET" not in err, err)
        check("401/402 sent with token from storage", CALLS[-1]["auth"] == "Bearer apify_api_SECRET")
        s, _ = call("DELETE", f"/api/sources/{src['id']}")
        check("delete source", s == 200)
    finally:
        proc.terminate()
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            proc.kill()
    print("\n" + (f"{len(failures)} FAILED: {failures}" if failures else "ALL PASSED"))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
