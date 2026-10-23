# Marketplace Browser (classifieds tracker)

Self-hosted server with a web UI. Watch several classifieds sites from one place, keep saved searches, and get alerts when new listings match. **One global location and radius applies to every saved search**: change it once in Settings and all searches follow.

The server is Python standard library only (no third-party packages) with a SQLite database in `/data`. A Chrome/Edge companion extension feeds it from your own signed-in browser.

```
.
├── app/                 server + web UI
├── extension/           Chrome/Edge companion extension (Manifest V3)
├── deploy/              compose.yaml, .env.example and RELEASE.md for the home server (image from Docker Hub)
├── .github/workflows/   release.yml (tag: build, push, GitHub release) and test.yml
├── docs/                functional spec, pending changes log, research notes
├── tests/               server smoke test, Apify source test, real-Chromium extension test
├── CHANGELOG.md         what changed in each version
└── VERSION              single source of the version (0.3.3)
```

## 1. Release flow (GitHub Action)

Images are built only from tags. Pushing a tag `vMAJOR.MINOR.PATCH` (for example `v0.3.1`) runs `.github/workflows/release.yml`, which checks that `VERSION` equals the tag and that `CHANGELOG.md` has an entry for it (Short 50 characters or fewer, Long 250 or fewer), builds `linux/amd64`, pushes `mybadreligon/marketplace-browser:X.Y.Z`, `X.Y` and `latest`, and creates the GitHub release as its last step. Plain pushes to `main` only run the tests (`test.yml`).

1. The repo needs the Actions secrets `DOCKERHUB_USERNAME` (`mybadreligon`) and `DOCKERHUB_TOKEN`.
2. Each release updates `VERSION` and `extension/manifest.json` (they must match), `CHANGELOG.md`, `docs/functional-spec.md`, and `deploy/compose.yaml`, `deploy/.env.example` and `deploy/RELEASE.md` (`python3 tests/release_check.py` verifies this).
3. Tag and push: `git tag -a vX.Y.Z -m "<short>" -m "<long>" && git push origin vX.Y.Z`.

`deploy/RELEASE.md` carries `Update: now` (deploy right away; only for a "build, push and update" request) or `Update: later` (deployed in the regular daily update run).

Versions: patch for fixes and small tweaks, minor for new features, major only on explicit decision. Requests are logged in `docs/pending-changes.md` and built on request. If a workflow step fails, fix it with a new patch release instead of moving the tag.

## 2. Deploy on the home server

Use `deploy/compose.yaml`: it pulls the pinned image (no `build:`), runs as user 1000:100 and keeps the SQLite database in `<FAST_STORAGE>/marketplace-browser`. Details for each release (port, data folder, checks, rollback) are in `deploy/RELEASE.md`.

Variables (see `deploy/.env.example`):

| Variable | Required | Meaning |
| --- | --- | --- |
| `PORT_HOST` | yes | host and container port (same number), from the port register |
| `APP_PASSWORD` | yes | web UI password |
| `INGEST_TOKEN` | no | fixed extension token; generated and shown in Settings if empty |
| `MIN_POLL_MINUTES` | no | lowest allowed check interval, default 5 |
| `FAST_STORAGE` | no | data root; default is the server's SSD appdata path |

Open `http://<host>:<PORT_HOST>`. Put it behind HTTPS (reverse proxy, Tailscale or a VPN) before exposing it beyond your home network. Back up by stopping the container and copying the data folder (`tracker.db`, `-wal` and `-shm` together). To update, change the pinned tag and redeploy.

## 3. First-time setup (web UI)

1. **Settings, Location:** search for a place or postal code (OpenStreetMap Nominatim, so the server needs internet access) or type latitude/longitude, then set a radius in km.
2. **Settings, Alerts:** add an [ntfy](https://ntfy.sh) topic URL (push to your phone), a webhook, or SMTP. Press "Send test alert".
3. **Sources:** add sources (below).
4. **Searches:** create saved searches. Existing listings are added silently; only listings found afterwards alert.

## 4. Sources

Facebook Marketplace and Kijiji have no public search API, and automated server-side scraping goes against their terms and gets blocked. So the server never scrapes them. Ways in:

| Type | How it works | Good for |
| --- | --- | --- |
| Browser extension / API | The extension opens your search pages in **your own signed-in browser**, reads the results and posts them to `/api/ingest` | Facebook Marketplace, Kijiji |
| Alert mailbox (IMAP) | Turn on the site's saved-search email alerts, deliver them to a mailbox the server can read, and it parses the listing links | Kijiji; Facebook if its emails carry listing links |
| Apify scraper (paid, optional) | The server asks an Apify actor to run each saved search and reads the results. Needs an Apify account and API token | Facebook Marketplace with no browser needed; see section 4a |
| RSS/Atom feed | URL template with `{q}`, `{lat}`, `{lon}`, `{radius_km}`, `{city}`, `{city_slug}`, `{location}` | any site that offers a feed |

### 4a. Apify source (Facebook Marketplace without the browser)

1. Create an Apify account and copy your API token (Settings, API and integrations). Set a monthly spending limit in Apify's billing settings as a second safety net.
2. In Sources choose **Apify scraper (paid)**, paste the token and save. The defaults use the actor `apify/facebook-marketplace-scraper` and a Facebook search URL built from your global location.
3. Each active search that covers the source becomes one actor run per check. Defaults: every 60 minutes (minimum 15), 30 results per search, at most 24 runs per rolling 24 hours, each run stopped at 0.25 USD. Changing the location in Settings does **not** start a paid run; the next scheduled check uses it. "Check now" runs immediately and counts toward the daily cap.
4. The first check for a search is baseline and never alerts. The source card shows runs and results in the last 24 hours.

Cost is roughly: searches x checks per day x results per search x the actor's per-listing price (about 0.005 USD per listing at the time of research; confirm on the actor page, which showed several different prices). Ten searches checked hourly at 30 results is about 7,200 results a day, which is far more than the free monthly credit. Keep the search count and interval low, or lower the results limit.

Limits: without "Fetch listing details" results carry no coordinates, so the server cannot distance-filter them and relies on Facebook's own radius from the URL. The field mapping follows the actor's published sample output and has been tested against a fake Apify API, not a live run. Using a third party does not change Facebook's terms on automated collection; keep it to personal use.

## 5. The browser extension

Chrome or Edge (version 116+). Not published to a store: load it unpacked.

1. Unzip `the `extension/` folder from the repo` (or use the `extension/` folder).
2. Open `chrome://extensions`, enable Developer mode, "Load unpacked", pick the folder.
3. Open the extension's **Options**: enter the server URL (e.g. `http://192.168.1.20:<PORT_HOST>`) and the ingest token from the tracker's Settings. "Test connection" should report the version.
4. In the tracker, add a source of type **Browser extension / API** named `Facebook Marketplace` and press "Use Facebook Marketplace preset" (fills the search URL template from your global location). Do the same for `Kijiji` if you want Kijiji searches run automatically (you must supply its URL template; the default is empty).
5. Use it:
   - **Run all searches now**: opens each saved search's page one at a time in a background tab, scrolls, reads the listings, closes the tab and posts the results.
   - **Capture this page**: send whatever Facebook Marketplace or Kijiji results page you are looking at (no saved search needed).
   - **Automatic mode** (Options): runs in the background on an interval, at least 15 minutes.

Politeness limits are built in: one page at a time, 8-20 second random gaps, at most 10 pages per run by default, 15 minute floor. This is automated browsing in your own account; Facebook can restrict accounts for it, so keep the interval modest. The browser must be open and signed in for runs to work.

The first batch for a search is baseline and never alerts; later batches alert on anything new.

### Honest limits of v0.3

- The Facebook and Kijiji extractors read what a results page shows, using stable hooks (item URLs, Kijiji `data-testid` attributes) and visible text. **They have been tested against fixture pages that model those sites, not against the live sites**, which change often. If listings stop appearing, the popup reports "No listings recognised"; the extractor is one self-contained function in `extension/extractor.js`.
- The Facebook URL template (`/marketplace/{city_slug}/search?query=...&radius=...`) is from memory and unverified. Open a search on Facebook yourself, compare the address, and edit the template in Sources if needed. City slugs are derived from the first part of your location name.
- Facebook listings carry no coordinates, so they are not distance-filtered by the server; the radius is applied through Facebook's own search URL.
- The Docker image has not been built here (no Docker daemon in the build environment). The first GitHub Action run is its first real build.

## 6. API (for your own scripts)

```bash
curl -X POST http://localhost:<PORT_HOST>/api/ingest \
  -H "X-Ingest-Token: <token>" -H "Content-Type: application/json" \
  -d '{"source":"My source","search_id":1,
       "listings":[{"id":"123","url":"https://...","title":"Standing desk","price":"$90",
                    "image":"https://...","location":"Toronto","lat":43.66,"lon":-79.39}]}'
```

`GET /api/extension/tasks` (same token) returns the search URLs the extension should visit.

## 7. How location works

The global location is stored once. Feed and extension URL templates are rebuilt from it on every check, and listings that carry coordinates are filtered by distance when shown and before alerting. Changing the location updates the feed immediately; listings that newly fall inside the area appear without alerting, and only listings found afterwards alert.

## 8. Tests

```bash
python3 tests/release_check.py    # release files, version agreement, changelog lengths
python3 tests/smoke.py            # server: login, global location, baselining, alerts, ingest, CORS, email parsing
python3 tests/apify_test.py       # Apify source against a fake Apify API
python3 tests/e2e_extension.py    # loads the extension in Chromium against fake Facebook/Kijiji pages
```

The second needs Python Playwright and Chromium (`CHROMIUM_PATH` to point at a binary). CI runs the first.

## Third-party Facebook scrapers

v0.3 integrates the Apify Facebook Marketplace actor as an optional source (section 4a). Bright Data and Secondhand MCP are researched but not integrated. See `docs/research/third-party-facebook-marketplace-options.md`.

## Not included yet

Price-drop alerts (prices are recorded), cross-source duplicate grouping, a store-published extension, Firefox support, multi-user accounts.
