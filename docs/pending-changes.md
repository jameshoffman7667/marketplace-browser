# Pending changes

## Pending

### P-2 - Bring the app up to the full app spec (audit gaps)
Requested: 2026-10-22 (found while switching to the standard release flow)
Type: minor        Status: Pending
Notes / questions: missing against the spec: installable PWA (manifest, icons, wide and narrow screenshots, service worker, offline page, install button), distinct phone and desktop layouts checked at 390/768/1440 and 320 px, clean SIGTERM shutdown, tini or equivalent, fail-fast tests for missing config (APP_PASSWORD is currently required only by compose), Docker build run, a public hostname so it can be installed. Needs a public hostname decision. Ask James which of these to build first.

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
