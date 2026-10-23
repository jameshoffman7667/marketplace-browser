"""Release files check. Run: python3 tests/release_check.py
Mirrors the tag workflow's validation (version file, CHANGELOG entry with Short <= 50 and Long <= 250 chars)
and checks the files every release must leave in the repo."""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
errors = []


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


version = read("VERSION").strip()
if not re.fullmatch(r"\d+\.\d+\.\d+", version):
    errors.append(f"VERSION '{version}' is not MAJOR.MINOR.PATCH")
manifest = json.loads(read("extension/manifest.json"))["version"]
if manifest != version:
    errors.append(f"extension manifest {manifest} != VERSION {version}")

cl = read("CHANGELOG.md")
m = re.search(rf"^## v{re.escape(version)} .*?^\*\*Short:\*\* (.*?)$\n^\*\*Long:\*\* (.*?)$", cl, re.M | re.S)
if not m:
    errors.append(f"CHANGELOG.md has no '## v{version}' entry with Short and Long lines")
else:
    short, long_ = m.group(1).strip(), m.group(2).strip()
    if not 0 < len(short) <= 50:
        errors.append(f"Short is {len(short)} chars (max 50)")
    if not 0 < len(long_) <= 250:
        errors.append(f"Long is {len(long_)} chars (max 250)")

for rel in ("Dockerfile", ".dockerignore", ".github/workflows/release.yml", "docs/functional-spec.md",
            "docs/pending-changes.md", "deploy/compose.yaml", "deploy/.env.example", "deploy/RELEASE.md", "README.md"):
    if not os.path.isfile(os.path.join(ROOT, rel)):
        errors.append(f"missing {rel}")
else:
    compose = read("deploy/compose.yaml")
    if f"image: mybadreligon/marketplace-browser:{version}" not in compose:
        errors.append(f"deploy/compose.yaml image is not pinned to mybadreligon/marketplace-browser:{version}")
    if "latest" in re.findall(r"image:.*", compose)[0]:
        errors.append("deploy/compose.yaml uses :latest")
    if re.search(r"^\s*build:", compose, re.M):
        errors.append("deploy/compose.yaml has a build: section")
    wf = read(".github/workflows/release.yml")
    for needle, why in (("branches: [main]", "main trigger"), ("paths: [VERSION", "VERSION path filter"),
                        ('--target "$GITHUB_SHA"', "gh release create --target"), ("group: release", "concurrency group")):
        if needle not in wf:
            errors.append(f"release.yml is missing {why} ({needle})")
    dockerfile = read("Dockerfile")
    hc = re.search(r"^HEALTHCHECK .*?(?=^\S*CMD \[|\Z)", dockerfile, re.M | re.S)
    if not hc or "--start-period=30s" not in hc.group(0) or "/healthz" not in hc.group(0) or "${PORT}" not in hc.group(0):
        errors.append("Dockerfile HEALTHCHECK must use --start-period=30s and GET /healthz on ${PORT}")
    if not re.search(r"^\s*start_period: 30s$", compose, re.M) or "/healthz" not in compose:
        errors.append("deploy/compose.yaml healthcheck must use start_period: 30s and /healthz")
    release_md = read("deploy/RELEASE.md")
    if f"# Release v{version}" not in release_md:
        errors.append(f"deploy/RELEASE.md is not for v{version}")
    if not re.search(r"^Update: (now|later)$", release_md, re.M):
        errors.append("deploy/RELEASE.md needs a line exactly 'Update: now' or 'Update: later'")

print("release check: " + ("FAILED\n  " + "\n  ".join(errors) if errors else f"OK (v{version})"))
sys.exit(1 if errors else 0)
