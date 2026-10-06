#!/usr/bin/env python3
"""Build the delivery zip for the current version.

    python3 tools/package.py [output_dir]      (default: ./dist)

Produces classifieds-tracker-vX.Y.zip with the repository contents at the zip root, ready to be
extracted and uploaded to GitHub. Refuses to build if any versioned release file is missing or inconsistent.
"""
import json
import os
import re
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXCLUDE_DIRS = {".git", "__pycache__", "data", "dist", "node_modules"}
EXCLUDE_FILES = {".env"}


def main():
    version = open(os.path.join(ROOT, "VERSION")).read().strip()
    major, minor = version.split(".")[:2]
    label = f"v{major}.{minor}"
    errors = []
    manifest = json.load(open(os.path.join(ROOT, "extension", "manifest.json")))["version"]
    if manifest != version:
        errors.append(f"extension/manifest.json version {manifest} != VERSION {version}")
    changelog = open(os.path.join(ROOT, "CHANGELOG.md")).read()
    if not re.search(rf"^## {re.escape(label)}( |$)", changelog, re.M):
        errors.append(f"CHANGELOG.md has no '## {label}' entry")
    for rel in (f"docs/functional-spec-{label}.md", f"docs/releases/{label}-commit-message.txt"):
        if not os.path.isfile(os.path.join(ROOT, rel)):
            errors.append(f"missing {rel}")
    if errors:
        sys.exit("Cannot package:\n  " + "\n  ".join(errors))

    out_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "dist")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"classifieds-tracker-{label}.zip")
    count = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for d, dirs, files in os.walk(ROOT):
            dirs[:] = sorted(x for x in dirs if x not in EXCLUDE_DIRS)
            for n in sorted(files):
                if n in EXCLUDE_FILES or n.endswith((".zip", ".pyc")):
                    continue
                p = os.path.join(d, n)
                z.write(p, os.path.relpath(p, ROOT))
                count += 1
    print(f"{out}  ({count} files, {label})")


if __name__ == "__main__":
    main()
