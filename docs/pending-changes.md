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
