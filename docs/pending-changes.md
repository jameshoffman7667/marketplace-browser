# Pending changes

## Pending

### P-2 - Bring the app up to the full app spec (audit gaps)
Requested: 2026-10-22 (found while switching to the standard release flow)
Type: minor        Status: Pending
Notes / questions: missing against the spec: installable PWA (manifest, icons, wide and narrow screenshots, service worker, offline page, install button), distinct phone and desktop layouts checked at 390/768/1440 and 320 px, clean SIGTERM shutdown, tini or equivalent, fail-fast tests for missing config (APP_PASSWORD is currently required only by compose), Docker build run, a public hostname so it can be installed. Needs a public hostname decision. Ask James which of these to build first.

## Done

### P-1 - Switch to the standard release flow
Requested: 2026-10-22 (James: "switch this app to the standard release flow in the home server app spec")
Type: patch (packaging and CI)        Status: Built in v0.3.1
Notes / questions: tag workflow for mybadreligon/marketplace-browser X.Y.Z, X.Y and latest plus GitHub release; deploy/compose.yaml and deploy/RELEASE.md every release; first tag is v0.3.1 because v0.3.0 never had deploy files.
