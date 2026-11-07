#!/usr/bin/env python3
"""PWA checks without a browser: manifest, icons, screenshots, service worker, offline page, caching, SIGTERM."""
import json, os, signal, urllib.error, struct, subprocess, sys, tempfile, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 18400
BASE = f"http://127.0.0.1:{PORT}"
STATIC = os.path.join(ROOT, "app", "static")
fails = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail and not ok else ""))
    if not ok:
        fails.append(name)


def png_size(path):
    with open(path, "rb") as f:
        h = f.read(24)
    return struct.unpack(">II", h[16:24]) if h[:8] == b"\x89PNG\r\n\x1a\n" else None


def get(path):
    r = urllib.request.urlopen(BASE + path, timeout=5)
    return r.status, dict(r.headers), r.read()


m = json.load(open(os.path.join(STATIC, "manifest.webmanifest")))
for k in ("id", "name", "short_name", "start_url", "scope", "display", "theme_color", "background_color", "icons", "screenshots"):
    check(f"manifest has {k}", bool(m.get(k)))
check("manifest display standalone", m.get("display") == "standalone")
sizes = {(i["sizes"], i.get("purpose", "any")) for i in m["icons"]}
check("icon 192 any", ("192x192", "any") in sizes)
check("icon 512 any", ("512x512", "any") in sizes)
check("icon 512 maskable", ("512x512", "maskable") in sizes)
for i in m["icons"]:
    p = os.path.join(STATIC, i["src"].lstrip("/"))
    w, h = i["sizes"].split("x")
    check("icon file " + i["src"], os.path.exists(p) and png_size(p) == (int(w), int(h)), str(png_size(p)) if os.path.exists(p) else "missing")
forms = {s.get("form_factor") for s in m["screenshots"]}
check("wide and narrow screenshots", forms == {"wide", "narrow"}, str(forms))
for s in m["screenshots"]:
    p = os.path.join(STATIC, s["src"].lstrip("/"))
    w, h = s["sizes"].split("x")
    check("screenshot file " + s["src"], os.path.exists(p) and png_size(p) == (int(w), int(h)))
html = open(os.path.join(STATIC, "index.html")).read()
for needle in ('rel="manifest"', 'rel="apple-touch-icon"', "viewport-fit=cover", "serviceWorker", "beforeinstallprompt", "Add to Home Screen", "env(safe-area-inset"):
    check("index.html contains " + needle, needle in html)
sw = open(os.path.join(STATIC, "sw.js")).read()
check("sw uses versioned cache", "__VERSION__" in sw)
check("sw never caches API", "/api/" in sw)
check("sw supports SKIP_WAITING", "SKIP_WAITING" in sw)

d = tempfile.mkdtemp()
env = dict(os.environ, DATA_DIR=d, PORT=str(PORT), APP_PASSWORD="pw", APP_VERSION="9.9.9")
proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "app", "server.py")], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(100):
        try:
            get("/healthz"); break
        except Exception:
            time.sleep(.1)
    s, h, b = get("/manifest.webmanifest")
    check("manifest served, no login", s == 200 and "manifest" in h.get("Content-Type", ""), h.get("Content-Type", ""))
    s, h, b = get("/sw.js")
    check("sw served with version", s == 200 and b"9.9.9" in b and b"__VERSION__" not in b)
    check("sw not cached", "no-cache" in h.get("Cache-Control", "") or "no-store" in h.get("Cache-Control", ""), h.get("Cache-Control", ""))
    check("sw javascript type", "javascript" in h.get("Content-Type", ""))
    s, h, b = get("/offline.html")
    check("offline page served", s == 200 and b"<html" in b.lower())
    s, h, b = get("/icons/icon-192.png")
    check("icon served long cache", s == 200 and "max-age" in h.get("Cache-Control", ""))
    try:
        get("/icons/nope.png"); check("missing static file is 404", False)
    except urllib.error.HTTPError as e:
        check("missing static file is 404", e.code == 404)
    s, h, b = get("/healthz")
    check("healthz exact", b == b'{"status":"ok","version":"9.9.9"}', b.decode())
    t0 = time.time()
    proc.send_signal(signal.SIGTERM)
    try:
        rc = proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        rc = None
    check("SIGTERM exits within 10 s", rc is not None and time.time() - t0 < 10, str(rc))
    check("SIGTERM exit code 0", rc == 0, str(rc))
finally:
    if proc.poll() is None:
        proc.kill()
# fail fast on missing required config
env2 = dict(os.environ, DATA_DIR=tempfile.mkdtemp(), PORT="18401")
env2.pop("APP_PASSWORD", None)
r = subprocess.run([sys.executable, os.path.join(ROOT, "app", "server.py")], env=env2, capture_output=True, timeout=15)
check("missing APP_PASSWORD exits non-zero", r.returncode != 0)
check("missing APP_PASSWORD names the variable", b"APP_PASSWORD" in r.stderr)
print("\n%d failed" % len(fails) if fails else "\nall passed")
sys.exit(1 if fails else 0)
