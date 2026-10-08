#!/usr/bin/env python3
"""Classifieds Tracker: self-hosted server with web UI.

Standard library only. Sources: RSS/Atom feeds, IMAP alert mailboxes, and an
ingest API (for a browser extension). One global location applies to all
saved searches. Matching, baselining and alerts (ntfy, webhook, email)
are handled here.
"""
import base64
import hashlib
import hmac
import imaplib
import json
import math
import os
import re
import secrets
import smtplib
import sqlite3
import sys
import threading
import time
import traceback
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from email import message_from_bytes
from email.header import decode_header, make_header
from email.message import EmailMessage
from html import unescape
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DATA_DIR = os.environ.get("DATA_DIR", "/data")
PORT = int(os.environ.get("PORT", "3501"))
MIN_POLL_MINUTES = float(os.environ.get("MIN_POLL_MINUTES", "5"))
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
VERSION = os.environ.get("APP_VERSION", "0.3.0")
APIFY_BASE = os.environ.get("APIFY_BASE", "https://api.apify.com").rstrip("/")
UA = f"ClassifiedsTracker/{VERSION} (+self-hosted personal use)"
# Used by the browser extension (ingest and tasks are token-authenticated; health only reports the version).
CORS_PATHS = ("/api/ingest", "/api/extension/tasks", "/api/health")

os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "tracker.db")
_lock = threading.RLock()
_conn = sqlite3.connect(DB_PATH, check_same_thread=False)
_conn.row_factory = sqlite3.Row
_force_run = threading.Event()

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS sources (
  id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, type TEXT NOT NULL,
  config TEXT NOT NULL DEFAULT '{}', enabled INTEGER NOT NULL DEFAULT 1,
  last_run REAL, last_ok REAL, last_error TEXT, fail_count INTEGER NOT NULL DEFAULT 0,
  degraded_notified INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS searches (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, keywords TEXT NOT NULL,
  exclude TEXT NOT NULL DEFAULT '', price_min REAL, price_max REAL,
  source_ids TEXT NOT NULL DEFAULT '[]', alert_mode TEXT NOT NULL DEFAULT 'instant',
  channels TEXT NOT NULL DEFAULT '[]', enabled INTEGER NOT NULL DEFAULT 1,
  created REAL NOT NULL, last_digest REAL NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS listings (
  id INTEGER PRIMARY KEY, source_id INTEGER NOT NULL, ext_id TEXT NOT NULL,
  url TEXT, title TEXT, price REAL, currency TEXT, image TEXT, description TEXT,
  location TEXT, lat REAL, lon REAL, posted TEXT, first_seen REAL, last_seen REAL,
  status TEXT NOT NULL DEFAULT 'active', UNIQUE(source_id, ext_id));
CREATE TABLE IF NOT EXISTS price_history (listing_id INTEGER, price REAL, seen REAL);
CREATE TABLE IF NOT EXISTS matches (
  search_id INTEGER NOT NULL, listing_id INTEGER NOT NULL, found REAL NOT NULL,
  baseline INTEGER NOT NULL DEFAULT 0, alerted REAL, state TEXT NOT NULL DEFAULT 'new',
  PRIMARY KEY (search_id, listing_id));
CREATE TABLE IF NOT EXISTS apify_usage (source_id INTEGER NOT NULL, ts REAL NOT NULL, items INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS feed_runs (
  search_id INTEGER NOT NULL, source_id INTEGER NOT NULL, last_run REAL,
  PRIMARY KEY (search_id, source_id));
CREATE TABLE IF NOT EXISTS alerts (
  id INTEGER PRIMARY KEY, ts REAL, search_id INTEGER, channel TEXT, title TEXT,
  body TEXT, ok INTEGER, error TEXT);
"""
with _lock:
    _conn.executescript(SCHEMA)
    _conn.commit()


def q(sql, args=()):
    with _lock:
        return [dict(r) for r in _conn.execute(sql, args).fetchall()]


def ex(sql, args=()):
    with _lock:
        cur = _conn.execute(sql, args)
        _conn.commit()
        return cur.lastrowid


# ---------------------------------------------------------------- settings
DEFAULTS = {
    "location_label": "", "lat": "", "lon": "", "radius_km": "50",
    "poll_minutes": "10", "ntfy_url": "", "webhook_url": "",
    "smtp_host": "", "smtp_port": "587", "smtp_user": "", "smtp_password": "",
    "smtp_from": "", "smtp_to": "", "smtp_tls": "starttls",
    "quiet_start": "", "quiet_end": "", "base_url": "",
}
SECRET_KEYS = {"smtp_password"}
MASK = "********"


def get_settings():
    s = dict(DEFAULTS)
    for r in q("SELECT key, value FROM settings"):
        if r["key"] in DEFAULTS:
            s[r["key"]] = r["value"]
    return s


def set_setting(key, value):
    ex("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
       (key, value))


def internal_secret(name):
    rows = q("SELECT value FROM settings WHERE key=?", (name,))
    if rows:
        return rows[0]["value"]
    val = secrets.token_urlsafe(32)
    set_setting(name, val)
    return val


def app_password():
    pw = os.environ.get("APP_PASSWORD", "")
    if pw:
        return pw
    pw = internal_secret("generated_password")
    return pw


def ingest_token():
    return os.environ.get("INGEST_TOKEN") or internal_secret("ingest_token")


def session_token():
    key = internal_secret("session_key").encode()
    return hmac.new(key, app_password().encode(), hashlib.sha256).hexdigest()


# ---------------------------------------------------------------- helpers
def now():
    return time.time()


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def global_location(settings=None):
    s = settings or get_settings()
    try:
        return float(s["lat"]), float(s["lon"]), float(s["radius_km"] or 0)
    except (TypeError, ValueError):
        return None


def distance_km(listing, loc):
    if not loc or listing.get("lat") is None or listing.get("lon") is None:
        return None
    return haversine_km(loc[0], loc[1], listing["lat"], listing["lon"])


def in_range(listing, loc):
    d = distance_km(listing, loc)
    if d is None or not loc[2]:
        return True
    return d <= loc[2]


PRICE_RE = re.compile(r"(?:CA?D?\s?\$|US?D?\s?\$|\$)\s?(\d{1,3}(?:[,\s]\d{3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)")


def parse_price(v):
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = PRICE_RE.search(str(v))
    s = m.group(1) if m else str(v)
    s = re.sub(r"[,\s]", "", s)
    try:
        return float(s)
    except ValueError:
        return None


def strip_html(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", unescape(s)).strip()


def render_url(template, search, settings):
    label = settings.get("location_label", "")
    city = label.split(",")[0].strip()
    slug = re.sub(r"[^a-z0-9]+", "-", city.lower()).strip("-")
    mapping = {
        "q": urllib.parse.quote_plus(search["keywords"]),
        "lat": settings.get("lat", ""), "lon": settings.get("lon", ""),
        "radius_km": settings.get("radius_km", ""),
        "city": urllib.parse.quote_plus(city), "city_slug": slug,
        "location": urllib.parse.quote_plus(label),
    }
    return re.sub(r"\{(\w+)\}", lambda m: str(mapping.get(m.group(1), m.group(0))), template)


# ---------------------------------------------------------------- listings
def upsert_listing(source_id, d):
    url = (d.get("url") or "").strip()
    ext_id = str(d.get("id") or url or d.get("title") or "")
    if not ext_id:
        return None
    title = (d.get("title") or "").strip()[:300]
    desc = (d.get("description") or "").strip()[:2000]
    price = parse_price(d.get("price"))
    if price is None:
        price = parse_price(title) or parse_price(desc)
    try:
        lat = float(d["lat"]) if d.get("lat") not in (None, "") else None
        lon = float(d["lon"]) if d.get("lon") not in (None, "") else None
    except (TypeError, ValueError):
        lat = lon = None
    t = now()
    rows = q("SELECT * FROM listings WHERE source_id=? AND ext_id=?", (source_id, ext_id))
    if rows:
        old = rows[0]
        ex("""UPDATE listings SET url=?, title=?, price=?, currency=?, image=?, description=?,
              location=?, lat=?, lon=?, posted=?, last_seen=?, status='active' WHERE id=?""",
           (url or old["url"], title or old["title"], price if price is not None else old["price"],
            d.get("currency") or old["currency"], d.get("image") or old["image"],
            desc or old["description"], d.get("location") or old["location"],
            lat if lat is not None else old["lat"], lon if lon is not None else old["lon"],
            d.get("posted") or old["posted"], t, old["id"]))
        if price is not None and old["price"] is not None and price != old["price"]:
            ex("INSERT INTO price_history VALUES(?,?,?)", (old["id"], price, t))
        return q("SELECT * FROM listings WHERE id=?", (old["id"],))[0], False
    lid = ex("""INSERT INTO listings(source_id, ext_id, url, title, price, currency, image, description,
                location, lat, lon, posted, first_seen, last_seen) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
             (source_id, ext_id, url, title, price, d.get("currency") or "", d.get("image") or "",
              desc, d.get("location") or "", lat, lon, d.get("posted") or "", t, t))
    if price is not None:
        ex("INSERT INTO price_history VALUES(?,?,?)", (lid, price, t))
    return q("SELECT * FROM listings WHERE id=?", (lid,))[0], True


def words(s):
    return [w for w in re.split(r"\s+", (s or "").lower().strip()) if w]


def matches_filters(listing, search):
    hay = f"{listing.get('title') or ''} {listing.get('description') or ''}".lower()
    for w in words(search["keywords"]):
        if w not in hay:
            return False
    for w in words(search["exclude"]):
        if w in hay:
            return False
    p = listing.get("price")
    if p is not None:
        if search["price_min"] is not None and p < search["price_min"]:
            return False
        if search["price_max"] is not None and p > search["price_max"]:
            return False
    return True


def search_sources(search):
    ids = json.loads(search["source_ids"] or "[]")
    return ids


def search_covers(search, source_id):
    ids = search_sources(search)
    return not ids or source_id in ids


def record_match(search, listing, baseline, loc):
    if not baseline and not in_range(listing, loc):
        baseline = True  # out of area right now: keep silent, visible if area grows
    with _lock:
        cur = _conn.execute(
            "INSERT OR IGNORE INTO matches(search_id, listing_id, found, baseline) VALUES(?,?,?,?)",
            (search["id"], listing["id"], now(), 1 if baseline else 0))
        _conn.commit()
        return cur.rowcount > 0


def rematch_search_silent(search):
    loc = global_location()
    for l in q("SELECT * FROM listings WHERE status='active'"):
        if search_covers(search, l["source_id"]) and matches_filters(l, search):
            record_match(search, l, True, loc)


def active_searches():
    return q("SELECT * FROM searches WHERE enabled=1")


def ingest_listings(source, items, search=None, baseline=None):
    """Store listings and create matches. Returns (stored, new_matches)."""
    loc = global_location()
    settings = get_settings()
    run_key = search["id"] if search else 0
    first = not q("SELECT 1 FROM feed_runs WHERE search_id=? AND source_id=?", (run_key, source["id"]))
    if baseline is None:
        baseline = first
    targets = [search] if search else [s for s in active_searches() if search_covers(s, source["id"])]
    stored = created = 0
    for d in items:
        res = upsert_listing(source["id"], d)
        if not res:
            continue
        l, _new = res
        stored += 1
        for s in targets:
            if matches_filters(l, s) and record_match(s, l, baseline, loc):
                created += 1
    ex("INSERT INTO feed_runs(search_id, source_id, last_run) VALUES(?,?,?) "
       "ON CONFLICT(search_id, source_id) DO UPDATE SET last_run=excluded.last_run",
       (run_key, source["id"], now()))
    return stored, created


# ---------------------------------------------------------------- feed source
def http_get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def local(tag):
    return tag.rsplit("}", 1)[-1].lower() if isinstance(tag, str) else ""


def parse_feed(data):
    root = ET.fromstring(data)
    out = []
    for el in root.iter():
        if local(el.tag) not in ("item", "entry"):
            continue
        d = {"title": "", "url": "", "description": "", "image": "", "posted": "", "id": ""}
        lat = lon = None
        for c in el:
            n = local(c.tag)
            txt = (c.text or "").strip()
            if n == "title":
                d["title"] = strip_html(txt)
            elif n == "link":
                d["url"] = c.get("href") or txt or d["url"]
            elif n in ("description", "summary", "content", "encoded"):
                if not d["description"]:
                    d["description"] = strip_html(txt)
                m = re.search(r"<img[^>]+src=[\"']([^\"']+)", unescape(txt))
                if m and not d["image"]:
                    d["image"] = m.group(1)
            elif n in ("guid", "id"):
                d["id"] = txt
            elif n in ("pubdate", "published", "updated", "date"):
                d["posted"] = d["posted"] or txt
            elif n in ("enclosure", "content", "thumbnail") and c.get("url"):
                if (c.get("type") or "image").startswith("image") and not d["image"]:
                    d["image"] = c.get("url")
            elif n == "point" and txt:
                parts = txt.replace(",", " ").split()
                if len(parts) == 2:
                    lat, lon = parts
            elif n == "lat":
                lat = txt
            elif n in ("long", "lon"):
                lon = txt
        if lat is not None and lon is not None:
            d["lat"], d["lon"] = lat, lon
        if d["url"] or d["title"]:
            out.append(d)
    return out


def run_feed_source(source):
    cfg = json.loads(source["config"] or "{}")
    template = cfg.get("url_template", "").strip()
    if not template:
        raise ValueError("Feed source has no URL template")
    settings = get_settings()
    total = 0
    for s in active_searches():
        if not search_covers(s, source["id"]):
            continue
        url = render_url(template, s, settings)
        items = parse_feed(http_get(url))
        stored, _ = ingest_listings(source, items, search=s)
        total += stored
        time.sleep(1.5)  # politeness between requests
    return total



# ---------------------------------------------------------------- Apify source
APIFY_ACTOR = "apify/facebook-marketplace-scraper"
APIFY_FB_TEMPLATE = ("https://www.facebook.com/marketplace/{city_slug}/search/"
                     "?query={q}&radius={radius_km}&sortBy=creation_time_descend&exact=false")
APIFY_MIN_INTERVAL = 15  # minutes; every run costs money


def dig(d, *path):
    for k in path:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def apify_to_listing(it):
    """Map one dataset item from the Facebook Marketplace actor to the ingest format.
    Field names follow the actor's published sample output; every lookup is defensive."""
    if not isinstance(it, dict) or it.get("is_sold"):
        return None
    lid = str(it.get("id") or "")
    url = it.get("listingUrl") or (f"https://www.facebook.com/marketplace/item/{lid}/" if lid else "")
    title = it.get("marketplace_listing_title") or it.get("custom_title") or ""
    if not (lid or url) or not title:
        return None
    price = dig(it, "listing_price", "amount")
    if price in (None, ""):
        price = dig(it, "listing_price", "formatted_amount")
    img = (dig(it, "primary_listing_photo", "image", "uri") or dig(it, "primary_listing_photo", "listing_image", "uri")
           or dig(it, "primary_listing_photo", "uri") or "")
    city = dig(it, "location", "reverse_geocode", "city") or ""
    state = dig(it, "location", "reverse_geocode", "state") or ""
    desc = it.get("description")
    if isinstance(desc, dict):
        desc = desc.get("text")
    desc = desc or dig(it, "redacted_description", "text") or ""
    posted = it.get("creation_time") or it.get("creationTime") or ""
    if isinstance(posted, (int, float)) and posted > 1e9:
        posted = datetime.utcfromtimestamp(posted).strftime("%Y-%m-%d %H:%M")
    out = {"id": lid or url, "url": url, "title": title, "price": price,
           "currency": dig(it, "listing_price", "currency") or "", "image": img,
           "location": ", ".join(x for x in (city, state) if x), "description": desc, "posted": str(posted)}
    lat, lon = dig(it, "location", "latitude"), dig(it, "location", "longitude")
    if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
        out["lat"], out["lon"] = lat, lon
    return out


def apify_interval(source):
    cfg = json.loads(source["config"] or "{}")
    try:
        return max(float(cfg.get("interval_minutes") or 60), APIFY_MIN_INTERVAL) * 60
    except (TypeError, ValueError):
        return 3600


def apify_usage(source_id):
    r = q("SELECT COUNT(*) AS runs, COALESCE(SUM(items),0) AS items FROM apify_usage WHERE source_id=? AND ts>?",
          (source_id, now() - 86400))[0]
    return {"runs_24h": r["runs"], "items_24h": r["items"]}


def apify_call(cfg, start_url):
    actor = urllib.parse.quote((cfg.get("actor") or APIFY_ACTOR).strip().replace("/", "~"), safe="~")
    params = {"timeout": "280"}
    if cfg.get("max_charge_usd"):
        params["maxTotalChargeUsd"] = str(cfg["max_charge_usd"])
    endpoint = f"{APIFY_BASE}/v2/acts/{actor}/run-sync-get-dataset-items?" + urllib.parse.urlencode(params)
    payload = {"startUrls": [{"url": start_url}],
               "resultsLimit": int(cfg.get("results_limit") or 30),
               "includeListingDetails": bool(cfg.get("details"))}
    req = urllib.request.Request(endpoint, data=json.dumps(payload).encode(), method="POST", headers={
        "Authorization": "Bearer " + cfg["token"], "Content-Type": "application/json", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            data = json.loads(r.read() or b"[]")
    except urllib.error.HTTPError as e:
        msg = ""
        try:
            msg = (json.loads(e.read()).get("error") or {}).get("message", "")
        except Exception:  # noqa: BLE001
            pass
        hint = {401: "token rejected", 402: "Apify credit or spending limit reached", 408: "run took too long"}.get(e.code, "")
        raise ValueError(f"Apify HTTP {e.code} {hint or msg}".strip())
    if not isinstance(data, list):
        raise ValueError("Apify returned an unexpected response")
    return data


def run_apify_source(source):
    cfg = json.loads(source["config"] or "{}")
    if not cfg.get("token"):
        raise ValueError("Apify source has no API token")
    template = (cfg.get("url_template") or APIFY_FB_TEMPLATE).strip()
    cap = int(cfg.get("daily_cap") or 24)
    settings = get_settings()
    total = 0
    for s in active_searches():
        if not search_covers(s, source["id"]):
            continue
        if apify_usage(source["id"])["runs_24h"] >= cap:
            raise ValueError(f"Daily run cap reached ({cap} runs per 24 h). Raise it in the source settings.")
        ex("INSERT INTO apify_usage(source_id, ts, items) VALUES(?,?,0)", (source["id"], now()))
        ts = q("SELECT MAX(ts) AS t FROM apify_usage WHERE source_id=?", (source["id"],))[0]["t"]
        raw = apify_call(cfg, render_url(template, s, settings))
        items = [x for x in (apify_to_listing(i) for i in raw) if x]
        ex("UPDATE apify_usage SET items=? WHERE source_id=? AND ts=?", (len(raw), source["id"], ts))
        stored, _ = ingest_listings(source, items, search=s)
        total += stored
    return total

# ---------------------------------------------------------------- email source
class LinkCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self._cur = None
        self._after = None
        self._text = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "a" and a.get("href"):
            self._cur = {"url": a["href"], "text": "", "image": "", "context": ""}
            self.links.append(self._cur)
            self._after = self._cur
        elif tag == "img" and a.get("src"):
            if self._cur is not None:
                self._cur["image"] = self._cur["image"] or a["src"]
                self._cur["text"] += " " + (a.get("alt") or "")
            elif self.links:
                self.links[-1]["image"] = self.links[-1]["image"] or a["src"]

    def handle_endtag(self, tag):
        if tag == "a":
            self._cur = None

    def handle_data(self, data):
        if self._cur is not None:
            self._cur["text"] += " " + data
        elif self._after is not None and len(self._after["context"]) < 160:
            self._after["context"] += " " + data


def parse_alert_email(raw, link_pattern):
    msg = message_from_bytes(raw)
    html = ""
    text = ""
    for part in msg.walk():
        ctype = part.get_content_type()
        if ctype in ("text/html", "text/plain"):
            payload = part.get_payload(decode=True) or b""
            body = payload.decode(part.get_content_charset() or "utf-8", "replace")
            if ctype == "text/html":
                html += body
            else:
                text += body
    items, seen = [], set()
    pat = re.compile(link_pattern or r"kijiji\.ca/v-|facebook\.com/marketplace/item", re.I)
    if html:
        col = LinkCollector()
        col.feed(html)
        cands = col.links
    else:
        cands = [{"url": u, "text": "", "image": "", "context": ""} for u in re.findall(r"https?://\S+", text)]
    for c in cands:
        url = c["url"].strip()
        if not pat.search(url):
            continue
        key = url.split("?")[0]
        if key in seen:
            continue
        title = re.sub(r"\s+", " ", unescape(c["text"])).strip()
        if not title and not seen_has_title(items, key):
            title = ""
        seen.add(key)
        context = re.sub(r"\s+", " ", unescape(c["context"])).strip()
        items.append({"id": key, "url": url, "title": title or key, "image": c["image"],
                      "description": context, "price": parse_price(title) or parse_price(context)})
    return items


def seen_has_title(items, key):
    return any(i["id"] == key and i["title"] for i in items)


def run_email_source(source):
    cfg = json.loads(source["config"] or "{}")
    host = cfg.get("host", "")
    if not host:
        raise ValueError("Email source has no IMAP host")
    port = int(cfg.get("port") or 993)
    M = imaplib.IMAP4_SSL(host, port, timeout=30) if cfg.get("ssl", True) else imaplib.IMAP4(host, port, timeout=30)
    try:
        M.login(cfg.get("user", ""), cfg.get("password", ""))
        M.select(cfg.get("folder") or "INBOX")
        crit = ["UNSEEN"]
        if cfg.get("from_filter"):
            crit += ["FROM", f'"{cfg["from_filter"]}"']
        typ, data = M.search(None, *crit)
        ids = data[0].split() if data and data[0] else []
        items = []
        for mid in ids[:50]:
            typ, msgdata = M.fetch(mid, "(RFC822)")
            if msgdata and msgdata[0]:
                items += parse_alert_email(msgdata[0][1], cfg.get("link_pattern"))
            M.store(mid, "+FLAGS", "\\Seen")
    finally:
        try:
            M.logout()
        except Exception:
            pass
    stored, _ = ingest_listings(source, items)
    return stored


# ---------------------------------------------------------------- alerts
def send_ntfy(settings, title, body, click):
    headers = {"Title": title.encode("ascii", "replace").decode(), "User-Agent": UA}
    if click:
        headers["Click"] = click
    req = urllib.request.Request(settings["ntfy_url"], data=body.encode(), headers=headers, method="POST")
    urllib.request.urlopen(req, timeout=15).read()


def send_webhook(settings, payload):
    req = urllib.request.Request(settings["webhook_url"], data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json", "User-Agent": UA}, method="POST")
    urllib.request.urlopen(req, timeout=15).read()


def send_email(settings, title, body):
    m = EmailMessage()
    m["Subject"], m["From"], m["To"] = title, settings["smtp_from"] or settings["smtp_user"], settings["smtp_to"]
    m.set_content(body)
    port = int(settings["smtp_port"] or 587)
    if settings["smtp_tls"] == "ssl":
        s = smtplib.SMTP_SSL(settings["smtp_host"], port, timeout=20)
    else:
        s = smtplib.SMTP(settings["smtp_host"], port, timeout=20)
        if settings["smtp_tls"] == "starttls":
            s.starttls()
    try:
        if settings["smtp_user"]:
            s.login(settings["smtp_user"], settings["smtp_password"])
        s.send_message(m)
    finally:
        s.quit()


def configured_channels(settings):
    ch = []
    if settings["ntfy_url"]:
        ch.append("ntfy")
    if settings["webhook_url"]:
        ch.append("webhook")
    if settings["smtp_host"] and settings["smtp_to"]:
        ch.append("email")
    return ch


def deliver(settings, channels, title, body, click, search_id=None, payload=None):
    """Send to channels; returns True if at least one succeeded."""
    ok_any = False
    for ch in channels:
        err = None
        try:
            if ch == "ntfy":
                send_ntfy(settings, title, body, click)
            elif ch == "webhook":
                send_webhook(settings, payload or {"title": title, "body": body, "url": click})
            elif ch == "email":
                send_email(settings, title, body)
        except Exception as e:  # noqa: BLE001
            err = str(e)[:300]
        ex("INSERT INTO alerts(ts, search_id, channel, title, body, ok, error) VALUES(?,?,?,?,?,?,?)",
           (now(), search_id, ch, title, body, 0 if err else 1, err))
        ok_any = ok_any or err is None
    return ok_any


def in_quiet_hours(settings):
    a, b = settings["quiet_start"], settings["quiet_end"]
    if not a or not b:
        return False
    try:
        cur = datetime.now().strftime("%H:%M")
        return (a <= cur < b) if a <= b else (cur >= a or cur < b)
    except Exception:
        return False


def fmt_price(p):
    return "" if p is None else (f"${p:,.0f}" if p == int(p) else f"${p:,.2f}")


def dispatch_alerts():
    settings = get_settings()
    if in_quiet_hours(settings):
        return
    loc = global_location(settings)
    for s in active_searches():
        mode = s["alert_mode"]
        if mode == "off":
            continue
        if mode in ("hourly", "daily"):
            interval = 3600 if mode == "hourly" else 86400
            if now() - s["last_digest"] < interval:
                continue
        pending = q("""SELECT m.listing_id, l.* FROM matches m JOIN listings l ON l.id=m.listing_id
                       WHERE m.search_id=? AND m.alerted IS NULL AND m.baseline=0 AND m.state='new'
                       ORDER BY m.found""", (s["id"],))
        pending = [p for p in pending if in_range(p, loc)]
        if not pending:
            continue
        chans = [c for c in (json.loads(s["channels"] or "[]") or configured_channels(settings))
                 if c in configured_channels(settings)]
        src = {r["id"]: r["name"] for r in q("SELECT id, name FROM sources")}
        if len(pending) == 1:
            p = pending[0]
            title = f"{s['name']}: {p['title'][:80]}"
            body = " | ".join(x for x in [fmt_price(p["price"]), src.get(p["source_id"], ""), p["location"]] if x)
            click = p["url"]
        else:
            title = f"{len(pending)} new for {s['name']}"
            body = "\n".join(f"{fmt_price(p['price'])} {p['title'][:70]} ({src.get(p['source_id'], '')}) {p['url']}"
                             for p in pending[:10])
            click = (settings["base_url"] or None)
        payload = {"search": s["name"], "count": len(pending), "listings": [
            {"title": p["title"], "price": p["price"], "url": p["url"], "source": src.get(p["source_id"])}
            for p in pending[:25]]}
        ok = deliver(settings, chans, title, body, click, s["id"], payload) if chans else True
        if ok:
            with _lock:
                _conn.executemany("UPDATE matches SET alerted=? WHERE search_id=? AND listing_id=?",
                                  [(now(), s["id"], p["listing_id"]) for p in pending])
                _conn.execute("UPDATE searches SET last_digest=? WHERE id=?", (now(), s["id"]))
                _conn.commit()


# ---------------------------------------------------------------- poller
def run_source(source):
    t = now()
    try:
        if source["type"] == "feed":
            run_feed_source(source)
        elif source["type"] == "email":
            run_email_source(source)
        elif source["type"] == "apify":
            run_apify_source(source)
        else:
            return
        ex("UPDATE sources SET last_run=?, last_ok=?, last_error=NULL, fail_count=0, degraded_notified=0 WHERE id=?",
           (t, t, source["id"]))
    except Exception as e:  # noqa: BLE001
        fails = source["fail_count"] + 1
        ex("UPDATE sources SET last_run=?, last_error=?, fail_count=? WHERE id=?",
           (t, str(e)[:300], fails, source["id"]))
        if fails >= 3 and not source["degraded_notified"]:
            ex("UPDATE sources SET degraded_notified=1 WHERE id=?", (source["id"],))
            st = get_settings()
            deliver(st, configured_channels(st), f"Source needs attention: {source['name']}",
                    f"{fails} failed checks in a row. Last error: {str(e)[:200]}", None)


def poller():
    while True:
        try:
            settings = get_settings()
            interval = max(float(settings["poll_minutes"] or 10), MIN_POLL_MINUTES) * 60
            forced = _force_run.is_set()
            _force_run.clear()
            for src in q("SELECT * FROM sources WHERE enabled=1 AND type IN ('feed','email','apify')"):
                if src["type"] == "apify":  # paid per run: own interval, never triggered by settings changes
                    due = not src["last_run"] or now() - src["last_run"] >= apify_interval(src)
                else:
                    due = forced or not src["last_run"] or now() - src["last_run"] >= interval
                if due:
                    run_source(src)
            dispatch_alerts()
        except Exception:  # noqa: BLE001
            traceback.print_exc()
        _force_run.wait(timeout=20)


# ---------------------------------------------------------------- API logic
def mask_source(src):
    cfg = json.loads(src["config"] or "{}")
    for k in ("password", "token"):
        if cfg.get(k):
            cfg[k] = MASK
    src = dict(src)
    if src["type"] == "apify":
        src["usage"] = apify_usage(src["id"])
    src["config"] = cfg
    return src


def listing_view(l, loc):
    d = distance_km(l, loc)
    return {k: l[k] for k in ("id", "url", "title", "price", "currency", "image", "description",
                              "location", "posted", "first_seen", "status")} | {
        "distance_km": None if d is None else round(d, 1)}


def api_feed(params):
    loc = global_location()
    where, args = ["1=1"], []
    if params.get("search_id"):
        where.append("m.search_id=?")
        args.append(int(params["search_id"]))
    if params.get("source_id"):
        where.append("l.source_id=?")
        args.append(int(params["source_id"]))
    state = params.get("state", "active")
    if state == "active":
        where.append("m.state IN ('new','seen')")
    elif state != "all":
        where.append("m.state=?")
        args.append(state)
    rows = q(f"""SELECT m.search_id, m.state, m.baseline, m.found, s.name AS search_name,
                        src.name AS source_name, l.*
                 FROM matches m JOIN listings l ON l.id=m.listing_id
                 JOIN searches s ON s.id=m.search_id JOIN sources src ON src.id=l.source_id
                 WHERE {' AND '.join(where)} ORDER BY m.found DESC LIMIT 1000""", args)
    merged, order = {}, []
    needle = (params.get("q") or "").lower()
    for r in rows:
        if not in_range(r, loc):
            continue
        if needle and needle not in (r["title"] or "").lower():
            continue
        e = merged.get(r["id"])
        if e is None:
            e = listing_view(r, loc) | {"state": r["state"], "is_new": r["state"] == "new" and not r["baseline"],
                                        "found": r["found"], "searches": [], "source": r["source_name"]}
            merged[r["id"]] = e
            order.append(r["id"])
        else:
            e["is_new"] = e["is_new"] or (r["state"] == "new" and not r["baseline"])
        e["searches"].append(r["search_name"])
    limit = int(params.get("limit", 100))
    offset = int(params.get("offset", 0))
    return {"total": len(order), "items": [merged[i] for i in order][offset:offset + limit]}


def clean_search(body, existing=None):
    kw = (body.get("keywords") or "").strip()
    if not kw:
        raise ValueError("Keywords are required")
    def num(k):
        v = body.get(k)
        return None if v in (None, "") else float(v)
    mode = body.get("alert_mode", "instant")
    if mode not in ("instant", "hourly", "daily", "off"):
        raise ValueError("Bad alert mode")
    return {
        "name": (body.get("name") or kw).strip()[:80], "keywords": kw,
        "exclude": (body.get("exclude") or "").strip(),
        "price_min": num("price_min"), "price_max": num("price_max"),
        "source_ids": json.dumps([int(x) for x in body.get("source_ids", [])]),
        "alert_mode": mode, "channels": json.dumps(body.get("channels", [])),
        "enabled": 1 if body.get("enabled", True) else 0,
    }


def search_out(s):
    s = dict(s)
    s["source_ids"] = json.loads(s["source_ids"] or "[]")
    s["channels"] = json.loads(s["channels"] or "[]")
    s["new_count"] = q("""SELECT COUNT(*) c FROM matches WHERE search_id=? AND state='new' AND baseline=0""",
                       (s["id"],))[0]["c"]
    s["total_count"] = q("SELECT COUNT(*) c FROM matches WHERE search_id=? AND state!='hidden'", (s["id"],))[0]["c"]
    return s


def geocode(query):
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
        {"q": query, "format": "json", "limit": 5})
    data = json.loads(http_get(url))
    return [{"label": r["display_name"], "lat": float(r["lat"]), "lon": float(r["lon"])} for r in data]


# ---------------------------------------------------------------- HTTP layer
class ApiError(Exception):
    def __init__(self, status, msg):
        super().__init__(msg)
        self.status, self.msg = status, msg


ROUTES = []


def route(method, pattern, auth="session"):
    def deco(fn):
        ROUTES.append((method, re.compile("^" + pattern + "$"), fn, auth))
        return fn
    return deco


@route("GET", "/api/health", auth="none")
def r_health(h, body, params):
    return {"ok": True, "version": VERSION}


@route("POST", "/api/login", auth="none")
def r_login(h, body, params):
    if not hmac.compare_digest(str(body.get("password", "")), app_password()):
        raise ApiError(401, "Wrong password")
    h.extra_headers.append(("Set-Cookie", f"session={session_token()}; HttpOnly; SameSite=Strict; Path=/; Max-Age=2592000"))
    return {"ok": True}


@route("POST", "/api/logout", auth="none")
def r_logout(h, body, params):
    h.extra_headers.append(("Set-Cookie", "session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"))
    return {"ok": True}


@route("GET", "/api/me")
def r_me(h, body, params):
    return {"ok": True, "version": VERSION, "ingest_token": ingest_token(),
            "channels": configured_channels(get_settings())}


@route("GET", "/api/settings")
def r_get_settings(h, body, params):
    s = get_settings()
    for k in SECRET_KEYS:
        if s[k]:
            s[k] = MASK
    return s


@route("PUT", "/api/settings")
def r_put_settings(h, body, params):
    for k, v in body.items():
        if k not in DEFAULTS or (k in SECRET_KEYS and v == MASK):
            continue
        set_setting(k, str(v).strip())
    _force_run.set()  # location or poll changes apply to every search on the next cycle
    return r_get_settings(h, {}, {})


@route("POST", "/api/geocode")
def r_geocode(h, body, params):
    query = (body.get("q") or "").strip()
    if not query:
        raise ApiError(400, "Enter a place name or postal code")
    try:
        return {"results": geocode(query)}
    except Exception as e:  # noqa: BLE001
        raise ApiError(502, f"Lookup failed: {e}. Enter latitude and longitude manually.")


@route("GET", "/api/sources")
def r_sources(h, body, params):
    return [mask_source(s) for s in q("SELECT * FROM sources ORDER BY id")]


def clean_source(body, existing=None):
    typ = body.get("type") or (existing or {}).get("type")
    if typ not in ("feed", "email", "ingest", "apify"):
        raise ApiError(400, "Type must be feed, email, ingest or apify")
    name = (body.get("name") or "").strip()
    if not name:
        raise ApiError(400, "Name is required")
    cfg = body.get("config") or {}
    if existing and cfg.get("password") == MASK:
        cfg["password"] = json.loads(existing["config"]).get("password", "")
    if typ == "apify":
        if existing and cfg.get("token") in (MASK, "", None):
            cfg["token"] = json.loads(existing["config"]).get("token", "")
        if not cfg.get("token"):
            raise ApiError(400, "Apify API token is required")
        try:
            cfg["interval_minutes"] = max(int(cfg.get("interval_minutes") or 60), int(APIFY_MIN_INTERVAL))
            cfg["results_limit"] = min(max(int(cfg.get("results_limit") or 30), 1), 500)
            cfg["daily_cap"] = min(max(int(cfg.get("daily_cap") or 24), 1), 1000)
        except (TypeError, ValueError):
            raise ApiError(400, "Interval, results limit and daily cap must be whole numbers")
    return name, typ, json.dumps(cfg), 1 if body.get("enabled", True) else 0


@route("POST", "/api/sources")
def r_source_add(h, body, params):
    name, typ, cfg, en = clean_source(body)
    try:
        sid = ex("INSERT INTO sources(name, type, config, enabled) VALUES(?,?,?,?)", (name, typ, cfg, en))
    except sqlite3.IntegrityError:
        raise ApiError(409, "A source with that name already exists")
    _force_run.set()
    return mask_source(q("SELECT * FROM sources WHERE id=?", (sid,))[0])


@route("PUT", r"/api/sources/(\d+)")
def r_source_put(h, body, params, sid):
    rows = q("SELECT * FROM sources WHERE id=?", (sid,))
    if not rows:
        raise ApiError(404, "No such source")
    name, typ, cfg, en = clean_source(body, rows[0])
    ex("UPDATE sources SET name=?, type=?, config=?, enabled=?, fail_count=0, degraded_notified=0 WHERE id=?",
       (name, typ, cfg, en, sid))
    _force_run.set()
    return mask_source(q("SELECT * FROM sources WHERE id=?", (sid,))[0])


@route("DELETE", r"/api/sources/(\d+)")
def r_source_del(h, body, params, sid):
    ex("DELETE FROM matches WHERE listing_id IN (SELECT id FROM listings WHERE source_id=?)", (sid,))
    ex("DELETE FROM listings WHERE source_id=?", (sid,))
    ex("DELETE FROM feed_runs WHERE source_id=?", (sid,))
    ex("DELETE FROM apify_usage WHERE source_id=?", (sid,))
    ex("DELETE FROM sources WHERE id=?", (sid,))
    return {"ok": True}


@route("POST", r"/api/sources/(\d+)/run")
def r_source_run(h, body, params, sid):
    rows = q("SELECT * FROM sources WHERE id=?", (sid,))
    if not rows:
        raise ApiError(404, "No such source")
    run_source(rows[0])
    return mask_source(q("SELECT * FROM sources WHERE id=?", (sid,))[0])


@route("GET", "/api/searches")
def r_searches(h, body, params):
    return [search_out(s) for s in q("SELECT * FROM searches ORDER BY id")]


@route("POST", "/api/searches")
def r_search_add(h, body, params):
    try:
        c = clean_search(body)
    except (ValueError, TypeError) as e:
        raise ApiError(400, str(e))
    sid = ex("""INSERT INTO searches(name, keywords, exclude, price_min, price_max, source_ids, alert_mode,
                channels, enabled, created) VALUES(?,?,?,?,?,?,?,?,?,?)""",
             (c["name"], c["keywords"], c["exclude"], c["price_min"], c["price_max"], c["source_ids"],
              c["alert_mode"], c["channels"], c["enabled"], now()))
    s = q("SELECT * FROM searches WHERE id=?", (sid,))[0]
    rematch_search_silent(s)  # baseline: existing listings appear but never alert
    _force_run.set()
    return search_out(s)


@route("PUT", r"/api/searches/(\d+)")
def r_search_put(h, body, params, sid):
    if not q("SELECT 1 FROM searches WHERE id=?", (sid,)):
        raise ApiError(404, "No such search")
    try:
        c = clean_search(body)
    except (ValueError, TypeError) as e:
        raise ApiError(400, str(e))
    ex("""UPDATE searches SET name=?, keywords=?, exclude=?, price_min=?, price_max=?, source_ids=?,
          alert_mode=?, channels=?, enabled=? WHERE id=?""",
       (c["name"], c["keywords"], c["exclude"], c["price_min"], c["price_max"], c["source_ids"],
        c["alert_mode"], c["channels"], c["enabled"], sid))
    s = q("SELECT * FROM searches WHERE id=?", (sid,))[0]
    rematch_search_silent(s)
    _force_run.set()
    return search_out(s)


@route("DELETE", r"/api/searches/(\d+)")
def r_search_del(h, body, params, sid):
    ex("DELETE FROM matches WHERE search_id=?", (sid,))
    ex("DELETE FROM feed_runs WHERE search_id=?", (sid,))
    ex("DELETE FROM searches WHERE id=?", (sid,))
    return {"ok": True}


@route("GET", "/api/feed")
def r_feed(h, body, params):
    return api_feed(params)


@route("POST", r"/api/listings/(\d+)/state")
def r_listing_state(h, body, params, lid):
    st = body.get("state")
    if st not in ("new", "seen", "saved", "hidden"):
        raise ApiError(400, "Bad state")
    ex("UPDATE matches SET state=? WHERE listing_id=?", (st, lid))
    return {"ok": True}


@route("POST", "/api/feed/mark-seen")
def r_mark_seen(h, body, params):
    ex("UPDATE matches SET state='seen' WHERE state='new'")
    return {"ok": True}


@route("GET", "/api/alerts")
def r_alerts(h, body, params):
    return q("SELECT * FROM alerts ORDER BY id DESC LIMIT 50")


@route("POST", "/api/test-alert")
def r_test_alert(h, body, params):
    st = get_settings()
    chans = configured_channels(st)
    if not chans:
        raise ApiError(400, "No alert channel is configured yet")
    ok = deliver(st, chans, "Classifieds Tracker test", "Alerts are working.", st["base_url"] or None)
    return {"ok": ok, "channels": chans, "log": q("SELECT * FROM alerts ORDER BY id DESC LIMIT %d" % len(chans))}


@route("POST", "/api/ingest", auth="ingest")
def r_ingest(h, body, params):
    name = (body.get("source") or "").strip()
    items = body.get("listings")
    if not name or not isinstance(items, list):
        raise ApiError(400, "Body needs 'source' (name) and 'listings' (array)")
    rows = q("SELECT * FROM sources WHERE name=?", (name,))
    if rows:
        src = rows[0]
        if src["type"] != "ingest":
            raise ApiError(400, "That source is not an ingest source")
    else:
        sid = ex("INSERT INTO sources(name, type, config) VALUES(?,?,?)", (name, "ingest", "{}"))
        src = q("SELECT * FROM sources WHERE id=?", (sid,))[0]
    search = None
    if body.get("search_id"):
        r = q("SELECT * FROM searches WHERE id=?", (int(body["search_id"]),))
        search = r[0] if r else None
    stored, created = ingest_listings(src, items[:500], search=search, baseline=body.get("baseline"))
    t = now()
    ex("UPDATE sources SET last_run=?, last_ok=?, last_error=NULL, fail_count=0 WHERE id=?", (t, t, src["id"]))
    _force_run.set()
    return {"stored": stored, "new_matches": created}


@route("GET", "/api/extension/tasks", auth="ingest")
def r_ext_tasks(h, body, params):
    settings = get_settings()
    tasks = []
    for src in q("SELECT * FROM sources WHERE enabled=1 AND type='ingest'"):
        tpl = json.loads(src["config"] or "{}").get("url_template", "").strip()
        if not tpl:
            continue
        for s in active_searches():
            if search_covers(s, src["id"]):
                tasks.append({"source": src["name"], "search_id": s["id"], "search": s["name"],
                              "url": render_url(tpl, s, settings)})
    return {"tasks": tasks}


class Handler(BaseHTTPRequestHandler):
    server_version = "ClassifiedsTracker"

    def log_message(self, fmt, *args):
        if os.environ.get("ACCESS_LOG"):
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def cookie(self, name):
        for part in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == name:
                return v
        return ""

    def authed(self, mode):
        if mode == "none":
            return True
        if mode == "ingest":
            tok = self.headers.get("X-Ingest-Token") or (self.headers.get("Authorization") or "").replace("Bearer ", "")
            return hmac.compare_digest(tok, ingest_token())
        return hmac.compare_digest(self.cookie("session"), session_token())

    def send(self, status, payload, ctype="application/json"):
        data = payload if isinstance(payload, bytes) else json.dumps(payload, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        if urllib.parse.urlparse(self.path).path in CORS_PATHS:
            self.send_header("Access-Control-Allow-Origin", "*")
        for k, v in self.extra_headers:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        # CORS preflight for the browser extension (token header, no cookies involved)
        path = urllib.parse.urlparse(self.path).path
        self.send_response(204 if path in CORS_PATHS else 404)
        if path in CORS_PATHS:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Ingest-Token, Authorization")
            self.send_header("Access-Control-Allow-Private-Network", "true")
            self.send_header("Access-Control-Max-Age", "600")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def handle_any(self, method):
        self.extra_headers = []
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if method == "GET" and not path.startswith("/api/"):
            return self.static(path)
        params = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}
        try:
            for m, pat, fn, auth in ROUTES:
                if m != method:
                    continue
                mt = pat.match(path)
                if not mt:
                    continue
                if not self.authed(auth):
                    raise ApiError(401, "Not signed in")
                body = {}
                if method in ("POST", "PUT"):
                    n = int(self.headers.get("Content-Length") or 0)
                    if n > 5_000_000:
                        raise ApiError(413, "Body too large")
                    raw = self.rfile.read(n) if n else b""
                    if raw:
                        try:
                            body = json.loads(raw)
                        except ValueError:
                            raise ApiError(400, "Invalid JSON")
                        if not isinstance(body, dict):
                            raise ApiError(400, "JSON object expected")
                args = [int(g) if g.isdigit() else g for g in mt.groups()]
                return self.send(200, fn(self, body, params, *args))
            raise ApiError(404, "Not found")
        except ApiError as e:
            self.send(e.status, {"error": e.msg})
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self.send(500, {"error": "Server error: %s" % e})

    def static(self, path):
        name = "index.html" if path in ("/", "") else path.lstrip("/")
        full = os.path.normpath(os.path.join(STATIC_DIR, name))
        if not full.startswith(STATIC_DIR) or not os.path.isfile(full):
            full = os.path.join(STATIC_DIR, "index.html")
        types = {".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css",
                 ".svg": "image/svg+xml", ".json": "application/json", ".png": "image/png"}
        with open(full, "rb") as f:
            self.send(200, f.read(), types.get(os.path.splitext(full)[1], "application/octet-stream"))

    def do_GET(self):
        self.handle_any("GET")

    def do_POST(self):
        self.handle_any("POST")

    def do_PUT(self):
        self.handle_any("PUT")

    def do_DELETE(self):
        self.handle_any("DELETE")


def main():
    if not os.environ.get("APP_PASSWORD"):
        print(f"APP_PASSWORD not set. Generated password: {app_password()}", flush=True)
    threading.Thread(target=poller, daemon=True).start()
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Classifieds Tracker listening on :{PORT}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
