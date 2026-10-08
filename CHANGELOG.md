# Changelog

Each iteration is labelled `vMAJOR.MINOR` (v0.1, v0.2, ...). The label maps to the internal version in `VERSION`, the Docker tag and the extension manifest (v0.1 is 0.1.0, v0.2 is 0.2.0, v0.3 is 0.3.0). Newest first. Every release also has a functional spec (`docs/functional-spec-vX.Y.md`) and a commit message (`docs/releases/vX.Y-commit-message.txt`).

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
