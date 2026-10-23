# Pending changes

## Pending

### P-2 - Bring the app up to the full app spec (audit gaps)
Requested: 2026-10-22 (found while switching to the standard release flow)
Type: minor        Status: Pending
Notes / questions: missing against the spec: installable PWA (manifest, icons, wide and narrow screenshots, service worker, offline page, install button), distinct phone and desktop layouts checked at 390/768/1440 and 320 px, clean SIGTERM shutdown, tini or equivalent, fail-fast tests for missing config (APP_PASSWORD is currently required only by compose), Docker build run, a public hostname so it can be installed. Needs a public hostname decision. Ask James which of these to build first.

### P-6 - Correct the existing-deployment facts in deploy/RELEASE.md
Requested: 2026-10-22 (James, relaying Claude Code's server check: "several of its facts about the current setup are wrong")
Type: patch (docs)        Status: Pending
Notes / questions: RELEASE.md says the old stack kept data in the named volume `tracker-data` with image `yourname/classifieds-tracker`. Actual: bind folder `<FAST_STORAGE>/marketplacetracker` (set by DATA_PATH), only `tracker.db` (no -wal/-shm), owned 10001:999; old image `mybadreligon/classifieds-tracker:edge` on port 3501, PORT_HOST already 3501. Also add: the old folder is copied (cp -a) and chowned 1000:100, the old folder stays as rollback; verification command on vm101 is `wget -qO- http://127.0.0.1:<PORT>/healthz` (no curl); add `marketplace-browser` to STOP_LIST in /usr/local/bin/tier1-backup.sh so the SQLite file is not copied while running. Would ship as v0.3.5 with Update: later unless you say "build, push and update".

### P-7 - Send /healthz as compact JSON
Requested: 2026-10-23 (James, relaying Claude Code: "/healthz returns {"status": "ok", ...} with a space after the colon; the spec requires compact JSON with no space and the health check greps for "status":"ok"")
Type: patch (bug)        Status: Pending
Notes / questions: the server serialises every response with json.dumps defaults, which put a space after the colon and comma. Fix: send compact separators (",", ":") at least for /healthz, exactly {"status":"ok","version":"X.Y.Z"}; tighten tests/smoke.py to compare the raw body bytes, not parsed JSON. Whole-app compact JSON or /healthz only? Would ship as v0.3.5 together with P-6 if you say "build P-6 and P-7".

## Done

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
