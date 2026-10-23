# Changelog

Versions are `MAJOR.MINOR.PATCH`; the git tag is `vMAJOR.MINOR.PATCH` and equals `VERSION`, the extension manifest and the Docker tag. Newest first. Each entry has a Short (50 characters or fewer) and a Long (250 or fewer) comment, used for the commit and the GitHub release. Entries v0.1, v0.2 and v0.3 predate this format and were never tagged or published as images.

## v0.3.2 - 2026-10-22
**Short:** Add Update now/later field to RELEASE.md
**Long:** RELEASE.md gets a fixed Update field: now only when the build message was "build, push and update", otherwise later. Later releases go out in Claude Code's daily update run, now releases right away. release_check enforces the field.

### Added
- `deploy/RELEASE.md` has a fixed `Update:` line. `Update: now` is written only when the build message for that release was "build, push and update"; every other release says `Update: later`. Claude Code deploys `later` releases in its regular daily update run and `now` releases right away.
- `tests/release_check.py` fails a release whose `RELEASE.md` lacks the line or has any value other than `now` or `later`.

### Notes
- v0.3.1 was committed but its tag was never pushed, so no 0.3.1 image or GitHub release exists. v0.3.2 is the first published release and includes everything in v0.3.1.

## v0.3.1 - 2026-10-22
**Short:** Adopt standard release flow and deploy files
**Long:** Tag workflow builds mybadreligon/marketplace-browser X.Y.Z, X.Y and latest, then creates the release. Adds deploy/compose.yaml and RELEASE.md, a /healthz endpoint, and release checks in CI. Replaces the old build workflow and zip packaging.

### Changed
- Releases: pushing a tag `vX.Y.Z` runs `.github/workflows/release.yml`, which validates version and changelog, builds `linux/amd64`, pushes `mybadreligon/marketplace-browser:X.Y.Z`, `X.Y` and `latest`, and creates the GitHub release as its last step. Replaces `docker.yml` (it built on every push and used the Docker Hub username from secrets).
- Tests now run in `.github/workflows/test.yml` on pushes and pull requests to `main`, with `tests/release_check.py` verifying release files, version agreement and changelog lengths. No image is built there.
- `deploy/compose.yaml`, `deploy/.env.example` and `deploy/RELEASE.md` replace `stack/`. The compose file pins the exact image tag, uses `PORT_HOST` for both host and container port, and stores data in a bind folder (`<FAST_STORAGE>/marketplace-browser`) instead of a named volume. Breaking for existing stacks: image name, container name, `TRACKER_PORT`/`TRACKER_IMAGE` variables and data location all change; see `deploy/RELEASE.md`.
- The image runs as user 1000:100 and reads its version from the `VERSION` file (no build argument).
- The functional spec is now the single current-state file `docs/functional-spec.md`; earlier versioned specs stay as history.

### Added
- `GET /healthz` returns `{status, version}` after checking the database; the image and compose health checks use it and follow `PORT`.
- `docs/pending-changes.md`.

### Removed
- `tools/package.py` and the zip delivery, `stack/`, `.github/workflows/docker.yml`. The extension zip is no longer attached to GitHub releases.

### Known limitations
- Docker image not built locally; the tag workflow is the first build. Not a PWA yet and no public hostname (P-2).

## v0.3 - 2026-10-07

### Added
- Apify source type ("Apify scraper (paid)"): runs the `apify/facebook-marketplace-scraper` actor for each active saved search, using the global location, and feeds the results through the normal baseline, dedupe and alert path. Optional and off until a source is added.
- Cost controls: own check interval (default 60 min, floor 15), maximum runs per rolling 24 h (default 24), results limit per search (default 30), per-run spending stop (default 0.25 USD), listing details off by default. Settings changes never start a paid run. Usage (runs and results in 24 h) shows on the source card.
- API token is masked in the API and never included in error messages; sent as a Bearer header, not in the URL.
- `tests/apify_test.py` (23 checks, fake Apify API) and a CI step for it.

### Changed
- `APIFY_BASE` environment variable can point at a different Apify API host (used by tests).
- Research note updated to say the Apify option is built.

### Known limitations
- Not run against live Apify or Facebook. The field mapping and the `radius`/`sortBy` URL parameters rely on the actor's published sample output and on Facebook URL conventions from memory.
- Without "Fetch listing details" there are no coordinates, so results are not distance-filtered by the server.
- Actor prices differ between Apify pages; the cost estimate in the README is an estimate.
- Everything listed under v0.1 still applies.

## v0.2 - 2026-10-07

### Changed (breaking)
- Default port is now 3501 (was 8080): server `PORT`, Dockerfile `EXPOSE` and health check, `stack/compose.yml` (`TRACKER_PORT` default 3501), `.env.example`, extension placeholder, README. Existing Dockhand stacks that map 8080 must change the container port to 3501, and the extension's server URL must be updated.

### Removed
- Root `docker-compose.yml` (local build). The only supported way to run the server is the Docker Hub image via `stack/compose.yml`. The Dockerfile stays because the GitHub Action builds it.

### Added
- Research note on third-party Facebook Marketplace scrapers (Bright Data, Apify actors, Secondhand MCP, others) with a candidate v0.3 design: `docs/research/third-party-facebook-marketplace-options.md`. Nothing integrated.

### Known limitations
- Unchanged from v0.1.

## v0.1 - 2026-10-06

First release.

### Added
- Self-hosted server and web UI in one Docker image (Python standard library, SQLite, non-root, health check).
- Saved searches with keywords, excluded words, price range, source selection and per-search alert mode and channels.
- One global location and radius that applies to every saved search; changing it re-filters everything without alert floods.
- Baselining: new searches, first batches and location changes never alert on listings that already existed.
- Sources: RSS/Atom feeds (URL templates filled from the global location), IMAP alert mailbox parsing, and an ingest API.
- Alerts through ntfy, webhook and SMTP email; instant, hourly or daily digest; quiet hours; test button and alert log.
- Feed with NEW badge, filters, save / seen / not interested.
- Chrome/Edge companion extension (Manifest V3): run all searches, capture the current page, optional automatic runs (15 minute floor), Facebook Marketplace and Kijiji extractors.
- Dockhand stack (`stack/compose.yml`) using an image from Docker Hub with a named data volume.
- GitHub Action: version and release-file checks, server tests, multi-arch build and push to Docker Hub, extension zip attached to releases.
- Tests: server smoke test (27 checks) and a real-Chromium extension test (21 checks).
- Release tooling: `tools/package.py` builds the versioned delivery zip.

### Known limitations
- Facebook and Kijiji extractors and the Facebook search URL template are tested only against fixtures that model those sites; they are unverified against the live sites.
- Alert-email parsing is heuristic and tested on a synthetic email only.
- The Docker image and GitHub Action have not been run yet; the first Action run is the first real build.
- Price-drop alerts, cross-source duplicate grouping, web push, data export and multi-user accounts are not included.
- Single shared password; no login rate limiting; secrets stored unencrypted in the database.
