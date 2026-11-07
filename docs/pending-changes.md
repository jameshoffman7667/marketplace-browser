# Pending changes

## Pending

(nothing pending except the P-10 live trial, listed under Done)

## Done

### P-2 - Bring the app up to the full app spec (audit gaps)
Requested: 2026-10-22; scope decided 2026-11-07 (James: "all")
Type: minor        Status: Built in v0.4.0
Notes / questions: build all of: installable PWA (manifest with wide and narrow screenshots and maskable icon, service worker that never caches API or sign-in pages, offline page, update prompt, install button, no reload on first install); distinct phone and desktop layouts checked at 390x844, 768x1024, 1440x900 and 320 px, light and dark mode; clean SIGTERM shutdown within 10 s (tested); fail-fast on missing required config with a test (APP_PASSWORD is currently enforced only by compose); one-command tests for the PWA files; a real Docker build run if the authoring environment allows. Public hostname decided: marketplace.hoffmanhouse.ca (needs a Caddy route, a Cloudflare tunnel hostname and a Cloudflare Access application with a bypass for /manifest.webmanifest, /sw.js and /icons/*; Claude Code and James do those). The browser extension talks to the server, so keep CORS working on the new hostname. Open: which home page group the tile goes in, and whether it also goes on the public home page (homelab rule: ask).

### P-8 - Switch release.yml to the canonical v1.9 workflow
Requested: 2026-11-07 (found while reading spec v1.9 section 6: "Use it exactly")
Type: patch (release process)        Status: Built in v0.4.0
Notes / questions: my workflow differs from the canonical one. Canonical has a prepare job that compares the version before and after the push (a push that touches VERSION without changing it builds nothing, mine would fail red), a per-version concurrency group (mine is one global group), a tag-path release with --verify-tag, and image tags via type=semver with value=v$VERSION. Replace it with the canonical file (only the version-file paths stay). A workflow change releases nothing on its own, so this must ship together with a version bump and CHANGELOG entry. Also update tests/release_check.py, which currently looks for strings from my workflow.

### P-9 - Move the port to 8045 (register plan)
Requested: 2026-11-07 (James: "move to register")
Type: patch (deploy files); breaking for anyone using http://<host>:3501        Status: Built in v0.4.0
Notes / questions: host and container port both become 8045 (PORT_HOST in the stack .env). In this repo: deploy/.env.example, deploy/RELEASE.md, README and functional spec examples (the Dockerfile default PORT stays a neutral dev default). The extension's saved server URL must be changed to the new port (or to https://marketplace.hoffmanhouse.ca once P-2 has the hostname). The server side of the move (stack .env, port register, Caddy, homepage links) is Claude Code's, one stack at a time outside 02:55 to 05:30. Do both together with the hostname if possible, to change the extension URL only once.

### P-10 - Try the Apify source without spending
Requested: 2026-11-07 (James: "test it if it can be done with no spending")
Type: minor (Test button)        Status: Test button built in v0.4.0; live trial still blocked (needs an Apify token from James)
Notes / questions: the authoring sandbox cannot reach api.apify.com (connection refused by the network allowlist), so I cannot run it here. It can be tried from the server with a free Apify account (monthly free credit, no card; in Apify billing set the monthly spending limit to $0 so nothing can be charged). Suggested trial settings in Sources: type Apify, check every 60 min, results per search 5, max runs per 24 h 2, stop a run at 0.05 USD, details off; then press Check now once for one saved search and look at the listings, title/price/image/location mapping, and whether the radius and sort in the URL were honoured. Report what you see and I fix the field mapping. Option: add a Test button that does one run with 3 results and shows the raw first item. Ask: do you want the button?
Result: the Test button (POST /api/sources/{id}/test) is built and tested against a fake Apify API. Still to do: James runs the free-account trial and reports what the Test dialog shows.

### P-11 - Attach the extension zip to each GitHub release
Requested: 2026-11-07 (James: "yes include the extension for now")
Type: patch (release process)        Status: Built in v0.4.0
Notes / questions: add a step after the release is created that zips the extension/ folder as marketplace-browser-extension-X.Y.Z.zip and uploads it with gh release upload. This is a small deviation from the canonical workflow (which says use it exactly), allowed by James for now. Do it in the same release as P-8 so the workflow is edited once.

### P-1 - Switch to the standard release flow
Requested: 2026-10-22 (James: "switch this app to the standard release flow in the home server app spec")
Type: patch (packaging and CI)        Status: Built in v0.3.1 (first published in v0.3.2)
Notes / questions: tag workflow for mybadreligon/marketplace-browser X.Y.Z, X.Y and latest plus GitHub release; deploy/compose.yaml and deploy/RELEASE.md every release; first tag is v0.3.1 because v0.3.0 never had deploy files.

### P-3 - Add an Update field to deploy/RELEASE.md
Requested: 2026-10-22 (James: "add a fixed field Update: now or Update: later ... Update: now only when I say 'build, push and update' for this release; otherwise Update: later")
Type: patch (release process)        Status: Built in v0.3.2
Notes / questions (answered 2026-10-22: Claude Code deploys `later` in its daily update run and `now` right away; release_check enforces the field): every release's RELEASE.md gets one line, `Update: now` only if the build message was "build, push and update", else `Update: later`. v0.3.1 was built without that phrase, so it would read `Update: later`. Should Claude Code deploy only when the field says now (and just push the tag and confirm the image when it says later)? Also add the field to tests/release_check.py so a release cannot omit it?

### P-4 - Lock the /healthz contract and 30 s health start period
Requested: 2026-10-22 (James: "answers GET /healthz on $PORT with {status:ok, version: same as the image tag}, no login, no private data, no checks of outside services ... HEALTHCHECK in image and compose with a 30 second start period")
Type: patch        Status: Built in v0.3.3
Notes / questions: /healthz already existed from v0.3.1; this release tightens tests and sets the start period to 30 s in both places.

### P-5 - Release on push to main (no tag push)
Requested: 2026-10-22 (James: "Change the release workflow so it never needs a tag push ... trigger on a push to main that changes the version")
Type: patch (release process)        Status: Built in v0.3.4
Notes / questions: version file used is VERSION; the tag trigger stays as a manual fallback with a duplicate guard. The canonical spec in homelab (section 6, 9, 10) still describes the tag-push flow and should be updated to match.

### P-6 - Correct the existing-deployment facts in deploy/RELEASE.md
Requested: 2026-10-22 (James, relaying Claude Code's server check: "several of its facts about the current setup are wrong")
Type: patch (docs)        Status: Built in v0.3.5
Notes / questions: RELEASE.md says the old stack kept data in the named volume `tracker-data` with image `yourname/classifieds-tracker`. Actual: bind folder `<FAST_STORAGE>/marketplacetracker` (set by DATA_PATH), only `tracker.db` (no -wal/-shm), owned 10001:999; old image `mybadreligon/classifieds-tracker:edge` on port 3501, PORT_HOST already 3501. Also add: the old folder is copied (cp -a) and chowned 1000:100, the old folder stays as rollback; verification command on vm101 is `wget -qO- http://127.0.0.1:<PORT>/healthz` (no curl); add `marketplace-browser` to STOP_LIST in /usr/local/bin/tier1-backup.sh so the SQLite file is not copied while running. Would ship as v0.3.5 with Update: later unless you say "build, push and update".

### P-7 - /healthz must be compact JSON, and health checks must require it
Requested: 2026-10-23 and 2026-10-28 (James: "/healthz currently returns {"status": "ok", "version": "0.3.4"} with a space after each colon and comma. Spec v1.9 requires exactly {"status":"ok","version":"<image tag>"}")
Type: patch (bug)        Status: Built in v0.3.5
Notes / questions: (1) /healthz must send exactly {"status":"ok","version":"<image tag>"}, no spaces, e.g. json.dumps with separators=(",", ":"). (2) The image HEALTHCHECK and the compose healthcheck must require "status":"ok" in the response body, not just a 200. (3) A test must lock the exact body bytes and that version equals the VERSION file (smoke.py currently compares parsed JSON, which hides the spaces). Cause: every response uses json.dumps defaults. Open question: compact for /healthz only (my suggestion) or every response? Ships as v0.3.5, with P-6 if you say "build P-6 and P-7", Update: later unless you say "build, push and update".
