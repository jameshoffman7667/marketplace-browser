# Release v0.3.5
Image: mybadreligon/marketplace-browser:0.3.5   (built by the release workflow on the push to main that set VERSION 0.3.5)
Short: Compact /healthz JSON; fix deployment notes
Long: /healthz now sends exactly {"status":"ok","version":"X.Y.Z"} with no spaces. Image and compose health checks require "status":"ok" in the body, and tests lock the exact bytes. RELEASE.md now describes the real existing deployment.
Update: later
Release commit: the commit on main that set VERSION to 0.3.5        Tag: created by the release workflow (gh release create --target); nobody pushes a tag
Type: patch (bug fix and docs; no new features). Fixes /healthz formatting (P-7) and the existing-deployment notes (P-6).
Port: PORT_HOST = container port. Currently 3501 on the server; the register plan is 8045. Set PORT_HOST in the stack .env. Exception: none
Public hostname: none yet (LAN only, so not installable as an app; the app is not a PWA yet, see docs/pending-changes.md P-2)        Needs Caddy route: no
New or changed env vars: PORT_HOST (new, required, replaces TRACKER_PORT), APP_PASSWORD, INGEST_TOKEN, MIN_POLL_MINUTES. TRACKER_IMAGE is gone (image is pinned in the compose file).
Data: /data on the fast disk at <FAST_STORAGE>/marketplace-browser, owner 1000:100 (the container runs as 1000:100). No /files use.
  Existing deployment (verified on the server): container classifieds-tracker runs mybadreligon/classifieds-tracker:edge on port 3501 (PORT_HOST already 3501). Its data is the bind folder <FAST_STORAGE>/marketplacetracker (set by DATA_PATH in the old .env), containing only tracker.db with no -wal or -shm, owned 10001:999. There is no named volume.
  Migration to this stack: stop (do not remove) the old container, then as root: cp -a <FAST_STORAGE>/marketplacetracker <FAST_STORAGE>/marketplace-browser and chown -R 1000:100 <FAST_STORAGE>/marketplace-browser. The old folder stays untouched as the pre-update copy and rollback. Do not run two containers on the same port.
  Backup: add marketplace-browser to STOP_LIST in /usr/local/bin/tier1-backup.sh so the nightly backup does not copy the SQLite file while the app runs.
  Migration in the app: additive schema only (new apify_usage table from v0.3.0); downgrade to 0.2.x starts.
Resources: about 30-60 MB RAM idle, negligible CPU between checks. No limits needed.
Healthcheck: GET /healthz on $PORT -> 200 with exactly {"status":"ok","version":"0.3.5"} (compact, no spaces); the image HEALTHCHECK and the compose healthcheck require "status":"ok" in the body (no login, no private data, no outside checks); image and compose start period 30s
Verify after deploy: 1) docker ps shows marketplace-browser healthy (on vm101 there is wget but no curl: wget -qO- http://127.0.0.1:<PORT_HOST>/healthz); 2) http://<host>:<PORT_HOST>/healthz returns exactly {"status":"ok","version":"0.3.5"}; 3) sign in, Settings shows the saved location and Sources lists the existing sources (proves the copied database is read).
PWA: not installable yet (no manifest or service worker); layouts not checked; Lighthouse not run. Tracked as P-2. Cloudflare Access bypass: not applicable until there is a hostname.
Docker build: not run locally (no Docker daemon in the authoring environment); first build is the release workflow. Confirm the container starts healthy after deploy.
Rollback: stop the new container and start the old classifieds-tracker stack (image mybadreligon/classifieds-tracker:edge); its data folder marketplacetracker is untouched. Data restore needed: no, unless the old folder was changed.
Known issues: the GitHub release no longer carries the extension zip (the extension folder is in the repo); SIGTERM is not handled gracefully (init: true forwards it; clean shutdown is P-2); Facebook and Apify paths unverified against live services.
Backup tier: small/critical (include in Tier 1); SQLite needs the container stopped (or all three db files copied together).
