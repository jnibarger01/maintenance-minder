#!/usr/bin/env python3
"""Regenerate photo_manifest.py from photo-manifest.json.

photo-manifest.json is the source of truth. photo_manifest.py is an importable
copy so Vercel traces the cache into the function bundle: a JSON file opened at
runtime is invisible to the bundler, which would silently drop the cache in
production.

Run after regenerating or hand-editing photo-manifest.json:

    python3 scripts/build_photo_manifest.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "photo-manifest.json"
TARGET = ROOT / "photo_manifest.py"

HEADER = '''"""Generated from photo-manifest.json. Do not hand-edit.

Kept as a Python module rather than a JSON file so Vercel traces it into the
function bundle: a file opened at runtime is invisible to the bundler, which
would silently drop the whole photo cache in production.

Regenerate with: python3 scripts/build_photo_manifest.py
"""
'''


def main():
    if not SOURCE.exists():
        print(f"{SOURCE} is missing", file=sys.stderr)
        return 1

    manifest = json.loads(SOURCE.read_text())
    entries = manifest.get("entries", {})
    if not entries:
        print("manifest has no entries; refusing to write an empty module", file=sys.stderr)
        return 1

    body = (
        HEADER
        + f"\nGENERATED = {manifest.get('generated', 'unknown')!r}\n"
        + f"\nENTRIES = {entries!r}\n"
    )
    TARGET.write_text(body)

    print(f"wrote {TARGET.relative_to(ROOT)}: {len(entries)} entries, {len(body) / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())