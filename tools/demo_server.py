"""Start a throwaway server with invented demo data (no personal data). Used by screenshots and layout tests."""
import json, os, subprocess, sys, tempfile, time, urllib.request, http.cookiejar

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMO = [
    ("Solid oak dining table with 6 chairs", 450, "Springfield"), ("Mountain bike, 29 inch, barely used", 320, "Riverside"),
    ("Standing desk, electric, 140 cm", 180, "Springfield"), ("Kids bunk bed with mattresses", 250, "Fairview"),
    ("Cast iron skillet set", 40, "Springfield"), ("Gaming monitor 27 inch 144 Hz", 150, "Riverside"),
    ("Snow tires 205/55R16 set of 4", 300, "Fairview"), ("Leather sofa, three seater", 400, "Springfield"),
]


def start(port, password="demo-pass"):
    d = tempfile.mkdtemp()
    env = dict(os.environ, DATA_DIR=d, PORT=str(port), APP_PASSWORD=password, MIN_POLL_MINUTES="1")
    p = subprocess.Popen([sys.executable, os.path.join(ROOT, "app", "server.py")], env=env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            urllib.request.urlopen(base + "/healthz", timeout=1).read(); break
        except Exception:
            time.sleep(.1)
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

    def call(m, path, body=None, headers=None):
        r = urllib.request.Request(base + path, method=m, data=json.dumps(body).encode() if body is not None else None,
                                   headers={"Content-Type": "application/json", **(headers or {})})
        return json.loads(op.open(r, timeout=10).read() or b"{}")
    call("POST", "/api/login", {"password": password})
    call("PUT", "/api/settings", {"location_label": "Springfield", "lat": "40.0", "lon": "-83.0", "radius_km": "50"})
    for nm, kw in (("Tables", "table"), ("Desks", "desk"), ("Bikes", "bike"), ("Sofas", "sofa"), ("Monitors", "monitor"),
                   ("Beds", "bed"), ("Tires", "tires"), ("Cookware", "skillet")):
        call("POST", "/api/searches", {"name": nm, "keywords": kw, "alert_mode": "off"})
    tok = call("GET", "/api/me")["ingest_token"]
    call("POST", "/api/ingest", headers={"X-Ingest-Token": tok}, body={"source": "Demo extension", "baseline": False, "listings": [
        {"id": f"d{i}", "title": t, "price": pr, "location": loc, "url": f"https://example.test/item/{i}",
         "lat": 40.0 + i / 100, "lon": -83.0} for i, (t, pr, loc) in enumerate(DEMO)]})
    return p, base, d, password


if __name__ == "__main__":
    p, base, *_ = start(int(sys.argv[1]) if len(sys.argv) > 1 else 18300)
    print(base); p.wait()
