# Release v0.3.4
Image: mybadreligon/marketplace-browser:0.3.4   (built by the release workflow on the push to main that set VERSION 0.3.4)
Short: Release on push to main, no tag push needed
Long: A push to main that changes VERSION now builds and pushes the image and runs gh release create --target, which creates the tag. The v*.*.* tag trigger stays as a manual fallback, and a duplicate-release guard stops both firing for one version.
Update: later
Release commit: the commit on main that set VERSION to 0.3.4        Tag: created by the release workflow (gh release create --target); nobody pushes a tag
Type: patch (release process; no change to app features). First published image: v0.3.1 to v0.3.3 were never tagged, so this release carries their changes too.
Port: PORT_HOST = container port. Currently 3501 on the server; the register plan is 8045. Set PORT_HOST in the stack .env. Exception: none
Public hostname: none yet (LAN only, so not installable as an app; the app is not a PWA yet, see docs/pending-changes.md P-2)        Needs Caddy route: no
New or changed env vars: PORT_HOST (new, required, replaces TRACKER_PORT), APP_PASSWORD, INGEST_TOKEN, MIN_POLL_MINUTES. TRACKER_IMAGE is gone (image is pinned in the compose file).
Data: /data on the fast disk at <FAST_STORAGE>/marketplace-browser, owner 1000:100 (the container runs as 1000:100). No /files use.
  Existing deployment: the old stack kept the SQLite database in the named volume `tracker-data` (image yourname/classifieds-tracker, container classifieds-tracker). To keep the data: stop the old container and copy tracker.db, tracker.db-wal and tracker.db-shm together into the new folder, chown 1000:100, then start this stack. Without that, the app starts empty. Remove the old stack so two containers do not share the port.
  Migration in the app: additive schema only (new apify_usage table from v0.3.0); downgrade to 0.2.x starts.
Resources: about 30-60 MB RAM idle, negligible CPU between checks. No limits needed.
Healthcheck: GET /healthz on $PORT -> 200 {"status":"ok","version":"0.3.4"} (no login, no private data, no outside checks); image and compose start period 30s
Verify after deploy: 1) docker ps shows marketplace-browser healthy; 2) http://<host>:<PORT_HOST>/healthz returns version 0.3.4; 3) sign in, Settings shows the saved location and Sources lists the existing sources (proves the copied database is read).
PWA: not installable yet (no manifest or service worker); layouts not checked; Lighthouse not run. Tracked as P-2. Cloudflare Access bypass: not applicable until there is a hostname.
Docker build: not run locally (no Docker daemon in the authoring environment); first build is the release workflow. Confirm the container starts healthy after deploy.
Rollback: v0.3.0 was never published as an image; roll back by restoring the previous stack and the data copy taken before the update. Data restore needed: only if the database was copied.
Known issues: the GitHub release no longer carries the extension zip (the extension folder is in the repo); SIGTERM is not handled gracefully (init: true forwards it; clean shutdown is P-2); Facebook and Apify paths unverified against live services.
Backup tier: small/critical (include in Tier 1); SQLite needs the container stopped (or all three db files copied together).
