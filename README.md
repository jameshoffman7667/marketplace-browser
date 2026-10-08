# Classifieds Tracker v0.3

Self-hosted server with a web UI. Watch several classifieds sites from one place, keep saved searches, and get alerts when new listings match. **One global location and radius applies to every saved search**: change it once in Settings and all searches follow.

The server is Python standard library only (no third-party packages) with a SQLite database in `/data`. A Chrome/Edge companion extension feeds it from your own signed-in browser.

```
.
├── app/                 server + web UI
├── extension/           Chrome/Edge companion extension (Manifest V3)
├── stack/compose.yml    Dockhand stack (image from Docker Hub)
├── stack/.env.example   variables for the stack
├── .github/workflows/   test, build, push to Docker Hub, package extension
├── docs/                versioned functional spec, per-release commit messages, research notes
├── tests/               server smoke test, Apify source test, real-Chromium extension test
├── tools/package.py     builds the versioned delivery zip
├── CHANGELOG.md         what changed in each version
└── VERSION              single source of the version (0.3.0)
```

## 1. Publish the image (GitHub Action)

1. Create a GitHub repo and push this folder to `main`.
2. Create a Docker Hub **access token** (Account settings, Security, Read & Write).
3. In the repo: Settings, Secrets and variables, Actions, add secrets `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN`.
4. Push to `main`: the workflow runs the tests, then builds `linux/amd64` + `linux/arm64` and pushes `yourname/classifieds-tracker:edge`.
5. Release: set `VERSION` and `extension/manifest.json` to the new version (the workflow fails if they differ), then
   ```bash
   git tag v0.3.0 && git push origin v0.3.0
   ```
   This pushes `0.3.0`, `0.3` and `latest`, and attaches `classifieds-tracker-extension-0.3.0.zip` to a GitHub release.

Pull requests run the tests and a build but never push or need secrets. There is no local-build compose file: the only way to run the server is the Docker Hub image (the Dockerfile exists for CI to build).

## 2. Deploy with Dockhand

Dockhand stacks can be pasted compose YAML or a Git repo, and support `${VAR}` substitution. Use `stack/compose.yml`, which pulls the image (no `build:`) and keeps data in a named volume, so there are no host-path or permission issues.

1. In Dockhand create a stack named `classifieds-tracker`, either by pasting `stack/compose.yml` or by pointing a Git stack at your repo and the file `stack/compose.yml`.
2. Set the stack's environment variables (see `stack/.env.example`):
   | Variable | Required | Meaning |
   | --- | --- | --- |
   | `TRACKER_IMAGE` | yes | e.g. `yourname/classifieds-tracker:0.3.0` (pin a version for repeatable deploys) |
   | `APP_PASSWORD` | yes | web UI password |
   | `INGEST_TOKEN` | no | fixed extension token; generated and shown in Settings if empty |
   | `TRACKER_PORT` | no | host port, default 3501 |
   | `TZ` | no | quiet hours and digests, default America/Toronto |
   | `MIN_POLL_MINUTES` | no | lowest allowed check interval, default 5 |
3. Deploy, then open `http://<host>:3501`.

Put it behind HTTPS (reverse proxy, Tailscale or a VPN) before exposing it beyond your home network. Back up by backing up the `tracker-data` volume. To update, change the tag and redeploy.

If you would rather bind-mount a host folder, the container runs as uid 10001, so the folder must be writable by it (or add `user:` to the service).

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

1. Unzip `classifieds-tracker-extension-0.3.0.zip` (or use the `extension/` folder).
2. Open `chrome://extensions`, enable Developer mode, "Load unpacked", pick the folder.
3. Open the extension's **Options**: enter the server URL (e.g. `http://192.168.1.20:3501`) and the ingest token from the tracker's Settings. "Test connection" should report the version.
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
curl -X POST http://localhost:3501/api/ingest \
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
python3 tests/smoke.py            # server: login, global location, baselining, alerts, ingest, CORS, email parsing
python3 tests/apify_test.py       # Apify source against a fake Apify API
python3 tests/e2e_extension.py    # loads the extension in Chromium against fake Facebook/Kijiji pages
```

The second needs Python Playwright and Chromium (`CHROMIUM_PATH` to point at a binary). CI runs the first.

## Versioning and releases

Each iteration is labelled `vMAJOR.MINOR` (v0.1, v0.2, ...); v0.3 is `0.3.0` in `VERSION`, the Docker tag and the extension manifest. A release consists of:

| File | Purpose |
| --- | --- |
| `classifieds-tracker-vX.Y.zip` | the repo contents at the zip root, ready to extract and upload to GitHub |
| `docs/functional-spec-vX.Y.md` | functional spec for that version |
| `docs/releases/vX.Y-commit-message.txt` | short change comment to use as the commit message |
| `CHANGELOG.md` | one entry per version, newest first |

`python3 tools/package.py` builds the zip and refuses to if `VERSION`, the extension manifest, the changelog entry or the versioned files disagree; CI runs the same checks. To publish: extract the zip over your repo, commit with the message from the commit-message file, push, then tag `vX.Y.0`. Older versioned spec and commit-message files stay in the repo as history.

## Third-party Facebook scrapers

v0.3 integrates the Apify Facebook Marketplace actor as an optional source (section 4a). Bright Data and Secondhand MCP are researched but not integrated. See `docs/research/third-party-facebook-marketplace-options.md`.

## Not included yet

Price-drop alerts (prices are recorded), cross-source duplicate grouping, a store-published extension, Firefox support, multi-user accounts.
