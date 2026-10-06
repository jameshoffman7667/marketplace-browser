# Changelog

Each iteration is labelled `vMAJOR.MINOR` (v0.1, v0.2, ...). The label maps to the internal version in `VERSION`, the Docker tag and the extension manifest (v0.1 is 0.1.0). Newest first. Every release also has a functional spec (`docs/functional-spec-vX.Y.md`) and a commit message (`docs/releases/vX.Y-commit-message.txt`).

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
