# Classifieds Tracker: Functional Specification v0.1

Version: v0.1 (internal 0.1.0) · Date: 2026-10-06 · Status: released, describes what v0.1 actually does

Status key used in the requirement tables: **Done** built and tested · **Partial** built with a gap noted · **Planned** not in v0.1.

## 1. Summary

Classifieds Tracker is a self-hosted server with a web UI. One person watches several classifieds sites from one place, keeps saved searches, and is alerted when new listings match. Facebook Marketplace is the primary source; Kijiji and other sites are added as sources. A single global location and radius applies to every saved search.

It ships as one Docker image (Python standard library, SQLite) plus a Chrome/Edge companion extension that reads results from the user's own signed-in browser.

## 2. Goals and non-goals

**Goals**

- One feed of listings across sources.
- Saved searches with their own keywords and filters, all using one global location and radius that can be changed in one place.
- Alerts when a new listing matches, without flooding the user when a search or the location changes.
- New sources added without changing the core app.
- Deployable as a Dockhand stack from an image published to Docker Hub by a GitHub Action.

**Non-goals (v0.1)**

- Posting listings, messaging sellers or negotiating.
- Price analytics or valuation.
- Multiple users or sharing searches.
- Bypassing logins, CAPTCHAs or rate limits on any site, and server-side scraping of Facebook or Kijiji.

**User:** one individual hunting for deals in one area, on phone and desktop. Assumed Canadian: km, Toronto-area default.

## 3. Feasibility position and source access

Facebook Marketplace has no public search API and automated collection is against Meta's terms. Kijiji has no public search API for third parties and its terms restrict scraping. The app therefore never scrapes either site from the server. Sources are reached in the ways below, ranked by how clearly they are permitted and how stable they are.

| Mode | How it works | v0.1 status |
| --- | --- | --- |
| A. Feed | Server fetches an RSS/Atom URL built from a template with the global location | Done |
| B. Alert mailbox | The site's own saved-search emails are read over IMAP and listing links parsed | Done (parser is heuristic, tested on a synthetic email only) |
| C. Browser extension | Extension reads results in the user's own signed-in browser and posts them to the ingest API | Done (tested on fixture pages, not live sites) |
| D. Server-side scraping | Backend fetches site pages with its own account | Excluded by design |

Default sources: Facebook Marketplace via mode C; Kijiji via mode B or C.

## 4. Core user flows

**First-time setup.** Sign in with the shared password. In Settings set the global location (place search or latitude/longitude) and radius, configure at least one alert channel and press Send test alert. Add sources. For the extension: install it, enter server URL and ingest token, add a "Browser extension / API" source and use the Facebook preset for its URL template.

**Create a saved search.** Enter keywords; optionally excluded words, minimum and maximum price, the sources to query, alert mode (instant, hourly digest, daily digest, off) and channels. The search uses the global location. Existing matching listings are added silently as baseline.

**Receive an alert.** A new matching listing in range triggers a message (title, price, source, location, link) on each configured channel. In the app it is marked NEW; the user can open it, Save it, mark it Seen, or mark it Not interested (hides it).

**Change the location.** One edit in Settings. Every search's URLs are rebuilt on the next check, listings are re-filtered by distance, listings that newly fall inside the area appear without alerting, and only listings found afterwards alert.

**Manage.** Edit, pause or delete searches and sources; see per-source last check, errors and a "needs attention" flag after three consecutive failures.

## 5. Functional requirements

### 5.1 Saved searches and location

| ID | Requirement | v0.1 |
| --- | --- | --- |
| SS-1 | Create, edit, pause and delete saved searches | Done (no duplicate action) |
| SS-2 | One global location (label, latitude, longitude) and radius in km applies to all searches; changing it applies everywhere | Done |
| SS-3 | A search holds keywords (all must match), excluded words, min and max price, and the list of sources | Done (category and condition not included) |
| SS-4 | A new or edited search is baselined: current matches stored silently, never alerted | Done |
| SS-5 | Per-search alert mode (instant, hourly, daily, off) and channel selection | Done |
| SS-6 | Quiet hours: alerts are held and sent when they end | Done (one global window) |

### 5.2 Sources and polling

| ID | Requirement | v0.1 |
| --- | --- | --- |
| SRC-1 | Source types: feed, alert mailbox, ingest (browser extension or API) | Done (three fixed types, not a plugin API) |
| SRC-2 | Poll active sources on an interval (default 10 min, floor 5 min) with politeness between requests | Done (no exponential backoff) |
| SRC-3 | Source health visible; three consecutive failures raise one "needs attention" notice | Done |
| SRC-4 | Place names are geocoded once; templates expose `{q}`, `{lat}`, `{lon}`, `{radius_km}`, `{city}`, `{city_slug}`, `{location}` | Done (geocoding uses OpenStreetMap Nominatim) |

### 5.3 Listings

| ID | Requirement | v0.1 |
| --- | --- | --- |
| LST-1 | Normalised listing: title, price, currency, image, description, location, coordinates, posted, URL, source | Done |
| LST-2 | Same listing seen again is one record per source; cross-source grouping | Partial (per-source only) |
| LST-3 | Price changes recorded; price-drop alerts | Partial (recorded, no alert) |
| LST-4 | Save, mark seen, hide ("Not interested"); hidden listings stay hidden | Done |
| LST-5 | Listings that disappear are marked gone | Planned (status column exists, never set) |
| LST-6 | Listings with coordinates are filtered to the radius in the feed and before alerting; listings without coordinates are kept | Done |

### 5.4 Alerts

| ID | Requirement | v0.1 |
| --- | --- | --- |
| ALR-1 | Channels: ntfy (phone push), webhook (JSON), email (SMTP); test button and alert log | Done (browser web push not included) |
| ALR-2 | At most one alert per listing per search | Done |
| ALR-3 | Digest modes batch matches into one message (first ten listed) | Done |
| ALR-4 | Act on an alert from the notification (hide, pause) | Planned |

### 5.5 Web UI and access

| ID | Requirement | v0.1 |
| --- | --- | --- |
| UI-1 | Feed with filters for search, source and state (active, saved, hidden, all), NEW badge, mark all seen | Done |
| UI-2 | Pages for searches, sources and settings; location shown in the header | Done |
| UI-3 | Phone and desktop layout; dark mode follows the system | Done |
| ACC-1 | Access control | Partial (one shared password for a single user, no accounts) |
| ACC-2 | Export and delete all data | Planned |

### 5.6 Browser extension

| ID | Requirement | v0.1 |
| --- | --- | --- |
| EXT-1 | Chrome or Edge 116+, Manifest V3, loaded unpacked; options for server URL and ingest token with a connection test | Done |
| EXT-2 | "Run all searches now": fetch queued search URLs from the server, open each in a tab one at a time, scroll, extract, close the tab, post to the server | Done |
| EXT-3 | "Capture this page": send the current Facebook Marketplace or Kijiji results page without a saved search | Done |
| EXT-4 | Automatic runs on an interval, minimum 15 minutes, max pages per run (default 10), random 8-20 s gap between pages | Done |
| EXT-5 | Clear errors: not signed in, nothing recognised, server unreachable, token rejected; popup shows last run | Done |
| EXT-6 | Extractors for Facebook Marketplace and Kijiji using item URLs, `data-testid` hooks and visible text | Done on fixtures; unverified against live sites |
| EXT-7 | Firefox support, store publishing | Planned |

## 6. Data model (SQLite, `/data/tracker.db`)

| Table | Purpose | Key fields |
| --- | --- | --- |
| settings | Key/value: global location, radius, alert channels, quiet hours, generated secrets | key, value |
| sources | One row per source | name, type (feed, email, ingest), config JSON, enabled, last run/ok, last error, fail count |
| searches | Saved searches (no location fields) | name, keywords, exclude, price min/max, source ids, alert mode, channels, enabled, last digest |
| listings | One row per source listing | source, external id (unique together), url, title, price, currency, image, description, location, lat, lon, posted, first/last seen, status |
| price_history | Price changes | listing, price, seen |
| matches | A listing matched by a search | search + listing (primary key), found, baseline flag, alerted time, state (new, seen, saved, hidden) |
| feed_runs | Whether a (search, source) pair has run before, to decide baseline | search, source, last run |
| alerts | Log of every notification attempt | time, search, channel, title, ok, error |

## 7. Architecture

```
 Facebook / Kijiji pages          Kijiji / FB alert emails        RSS/Atom feeds
        (your browser)                    (IMAP mailbox)
              |                                 |                        |
   Companion extension  ---- POST /api/ingest   |                        |
              |                                 v                        v
              +-------------------->   Docker container: Python server + SQLite (/data volume)
                                       poller thread: feed + email sources, match engine, alert dispatcher
                                       HTTP: JSON API + static web UI
                                                |
                                +---------------+----------------+
                                v                                v
                          Web UI (browser)          ntfy / webhook / SMTP alerts
```

- One process: HTTP server (threaded) plus a background poller. SQLite with a lock; designed for one user and tens of searches.
- Matching: a listing matches a search when all keywords appear in title or description, no excluded word does, price is in range, and the source is selected. Distance is checked at display and alert time.
- Image: `python:3.12-slim`, non-root uid 10001, `/data` volume, health check on `/api/health`, multi-arch (amd64, arm64) in CI.

## 8. API summary

Session cookie required unless noted. The ingest token goes in the `X-Ingest-Token` header.

| Endpoint | Purpose |
| --- | --- |
| `GET /api/health` (open, CORS) | Status and version |
| `POST /api/login`, `/api/logout`; `GET /api/me` | Session |
| `GET/PUT /api/settings`; `POST /api/geocode` | Global location, alerts, quiet hours, polling (secrets masked) |
| `GET/POST /api/sources`, `PUT/DELETE /api/sources/{id}`, `POST /api/sources/{id}/run` | Sources |
| `GET/POST /api/searches`, `PUT/DELETE /api/searches/{id}` | Saved searches |
| `GET /api/feed`; `POST /api/listings/{id}/state`; `POST /api/feed/mark-seen` | Feed and per-listing state |
| `GET /api/alerts`; `POST /api/test-alert` | Alert log and test |
| `POST /api/ingest` (token, CORS) | Post listings; creates the ingest source if new; first batch for a search/source is baseline |
| `GET /api/extension/tasks` (token, CORS) | Search page URLs for the extension, built from the global location |

## 9. Deployment and release

- **Dockhand:** `stack/compose.yml` pulls `${TRACKER_IMAGE}`, requires `APP_PASSWORD`, stores data in a named volume. Variables: `TRACKER_IMAGE`, `APP_PASSWORD`, `INGEST_TOKEN`, `TRACKER_PORT`, `TZ`, `MIN_POLL_MINUTES`.
- **GitHub Action:** tests, then builds multi-arch and pushes to Docker Hub (`edge` from `main`; `X.Y.Z`, `X.Y` and `latest` from a `vX.Y.Z` tag) and attaches the extension zip to the GitHub release. Needs secrets `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN`. Fails if `VERSION`, the extension manifest, the changelog or the versioned spec file disagree.
- **Versioning:** each iteration is labelled `vMAJOR.MINOR` (v0.1, v0.2, ...); the delivery zip, the spec file and the commit message file carry the label.

## 10. Non-functional requirements and security

| Area | v0.1 behaviour |
| --- | --- |
| Alert latency | Within one poll interval (default 10 min) for feeds and mail; extension runs at its own interval (minimum 15 min) |
| Politeness | 1.5 s between feed requests; extension opens one page at a time with 8-20 s random gaps; no CAPTCHA or bot-detection evasion |
| Authentication | One shared password; session cookie is HttpOnly and SameSite=Strict |
| Extension access | Ingest token; the ingest, tasks and health endpoints allow cross-origin requests so the extension can reach them; no session cookies involved |
| Data at rest | SMTP and IMAP passwords are stored in plain text in the SQLite file (masked in the API); protect the volume |
| Transport | HTTP only; run behind an HTTPS proxy, Tailscale or a VPN |

Known security gaps: no login rate limiting, session cookie lacks the `Secure` flag, secrets not encrypted at rest.

## 11. Risks

| Risk | Mitigation or status |
| --- | --- |
| Facebook or Kijiji change markup and break the extractors | Extractor is one self-contained function; popup reports "No listings recognised"; alert mailbox is an alternative |
| Facebook restricts an account for automated browsing | Own session only, one page at a time, random gaps, 15 minute floor; user warned in the README |
| Site terms prohibit automated collection | No server-side scraping; personal use only; check terms before offering it to others |
| Facebook search URL template is wrong | From memory and unverified; editable in Sources |
| Alert emails lack listing detail | Unverified against real emails |
| Docker image build untested outside CI | First GitHub Action run is the first real build |

## 12. Open questions

- Personal use only, or might it be offered to others later (changes terms exposure and the need for accounts)?
- Which machine runs the container, and how does the phone reach it?
- Which Kijiji region and Facebook categories matter most?
- Do Facebook's saved-search notification emails reach you, and do they carry listing links?
- Preferred alert channel on the phone?
- Priorities for v0.2.
