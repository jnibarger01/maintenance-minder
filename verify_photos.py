#!/usr/bin/env python3
"""Assert the committed photo manifest never misrepresents a vehicle.

Runs in CI. Guards three rules:

  1. A photo's model year must equal the requested model year, unless the entry
     is an explicit prior-year fallback.
  2. A photo that names a trim in its source filename must name the requested
     trim.
  3. Every photo must exist on disk, be a PNG served from images/, and have a
     credit and a source link.

Each record stores the sourceUrl it was verified against, so the year and trim
checks work even though the committed files are named by content hash.

Exits non-zero and prints each violation when the manifest is unsound.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from photo_resolver import (  # noqa: E402
    ROOT, asset_trim_tokens, declared_years, requested_trim_tokens,
)

MANIFEST = ROOT / "photo-manifest.json"
DEFAULT_TRIM = "__default__"
CUSTOM_TRIM = "otherentertrim"


def verify(manifest):
    entries = manifest.get("entries", {})
    problems = []
    stats = {"exact": 0, "generic": 0, "fallback": 0, "miss": 0, "files": set()}

    for key, record in entries.items():
        parts = key.split("|")
        if len(parts) != 3:
            problems.append(f"{key}: malformed key")
            continue
        year_text, model, trim = parts
        year = int(year_text)

        filename = record.get("file", "")
        if not filename.endswith(".png") or "/" in filename or "\\" in filename or ".." in filename:
            problems.append(f"{key}: unsafe or non-PNG file name {filename!r}")
        path = ROOT / "images" / filename
        if not path.exists():
            problems.append(f"{key}: missing file images/{filename}")
        elif path.stat().st_size < 500:
            problems.append(f"{key}: images/{filename} is implausibly small")
        else:
            stats["files"].add(filename)

        if not record.get("credit"):
            problems.append(f"{key}: missing credit")
        if not record.get("source"):
            problems.append(f"{key}: missing source link")

        source_url = record.get("sourceUrl", "")
        if not source_url.startswith("https://"):
            problems.append(f"{key}: sourceUrl is not https")
            continue

        if record.get("fallback"):
            stats["fallback"] += 1
            # A prior-year photo is never an exact match for this vehicle.
            if record.get("trimMatch"):
                problems.append(f"{key}: fallback claims an exact trim match")
            continue

        declared = declared_years(source_url)
        if declared and declared != {year}:
            problems.append(f"{key}: photo is model year {sorted(declared)}, not {year}")

        if trim != DEFAULT_TRIM and trim not in ("", CUSTOM_TRIM):
            asset_trims = asset_trim_tokens(source_url)
            wanted = requested_trim_tokens(trim)
            if asset_trims and not (asset_trims & wanted):
                problems.append(
                    f"{key}: photo names trim {sorted(asset_trims)}, not {trim}"
                )

        if trim == DEFAULT_TRIM:
            if record.get("trimMatch"):
                problems.append(f"{key}: generic entry claims an exact trim match")
            stats["generic"] += 1
        elif record.get("trimMatch") and record.get("trim") == trim:
            stats["exact"] += 1
        else:
            stats["generic"] += 1

    return problems, stats


def main():
    if not MANIFEST.exists():
        print(f"{MANIFEST} is missing", file=sys.stderr)
        return 1

    manifest = json.loads(MANIFEST.read_text())
    problems, stats = verify(manifest)

    total = stats["exact"] + stats["generic"] + stats["fallback"]
    print(
        f"photo manifest: {len(manifest.get('entries', {}))} entries, "
        f"{len(stats['files'])} distinct files | exact trim {stats['exact']} | "
        f"model-only {stats['generic']} | prior-year {stats['fallback']}"
    )
    print(f"generated: {manifest.get('generated', 'unknown')}")

    if problems:
        print(f"\n{len(problems)} problem(s):", file=sys.stderr)
        for problem in problems[:40]:
            print(f"  - {problem}", file=sys.stderr)
        if len(problems) > 40:
            print(f"  ... and {len(problems) - 40} more", file=sys.stderr)
        return 1

    print("manifest OK: no wrong-year or wrong-trim photos, all files present")
    return 0


if __name__ == "__main__":
    sys.exit(main())