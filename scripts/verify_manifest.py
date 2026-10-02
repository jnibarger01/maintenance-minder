#!/usr/bin/env python3
"""Assert the committed photo manifest never misrepresents a vehicle.

Guards the two accuracy rules the resolver enforces when building:

  1. A photo's model year must equal the requested model year, unless the entry
     is an explicit prior-year fallback.
  2. A photo that names a trim in its filename must name the requested trim.

Also checks that every image URL is HTTPS on an expected Honda host, so a
scrape change cannot inject an arbitrary source.

Exits non-zero and prints each violation when the manifest is unsound.
"""

import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))

from resolver import asset_trim_tokens, declared_years, requested_trim_tokens  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "images.json"

ALLOWED_HOSTS = {"www.hondainfocenter.com", "hondainfocenter.com", "automobiles.honda.com"}
DEFAULT_TRIM = "__default__"
CUSTOM_TRIM = "otherentertrim"


def verify(manifest):
    entries = manifest.get("entries", {})
    problems = []
    stats = {"exact": 0, "generic": 0, "fallback": 0, "miss": 0}

    for key, entry in entries.items():
        parts = key.split("|")
        if len(parts) != 3:
            problems.append(f"{key}: malformed key")
            continue
        year_text, model, trim = parts
        year = int(year_text)

        if not entry.get("found"):
            stats["miss"] += 1
            if not entry.get("reason"):
                problems.append(f"{key}: not found but carries no reason")
            continue

        url = entry.get("image", "")
        host = urlsplit(url).netloc
        if urlsplit(url).scheme != "https" or host not in ALLOWED_HOSTS:
            problems.append(f"{key}: unexpected image source {host!r}")

        if not entry.get("credit"):
            problems.append(f"{key}: missing credit")
        if not entry.get("source"):
            problems.append(f"{key}: missing source link")

        if entry.get("fallback"):
            stats["fallback"] += 1
            # A fallback is by definition a different year, so it must not also
            # claim an exact trim match.
            if entry.get("trimMatch"):
                problems.append(f"{key}: fallback claims an exact trim match")
            continue

        declared = declared_years(url)
        if declared and declared != {year}:
            problems.append(
                f"{key}: photo is model year {sorted(declared)}, not {year}"
            )

        if trim != DEFAULT_TRIM:
            asset_trims = asset_trim_tokens(url)
            wanted = requested_trim_tokens(trim)
            if trim not in ("", CUSTOM_TRIM) and asset_trims and not (asset_trims & wanted):
                problems.append(
                    f"{key}: photo names trim {sorted(asset_trims)}, not {trim}"
                )

        if trim == DEFAULT_TRIM:
            if entry.get("trimMatch"):
                problems.append(f"{key}: generic entry claims an exact trim match")
            stats["generic"] += 1
        elif entry.get("trimMatch"):
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

    total = stats["exact"] + stats["generic"] + stats["fallback"] + stats["miss"]
    print(
        f"manifest: {total} entries | exact trim {stats['exact']} | "
        f"model-only {stats['generic']} | prior-year {stats['fallback']} | "
        f"unmatched {stats['miss']}"
    )
    print(f"generated: {manifest.get('generated', 'unknown')}")

    if problems:
        print(f"\n{len(problems)} problem(s):", file=sys.stderr)
        for problem in problems[:40]:
            print(f"  - {problem}", file=sys.stderr)
        if len(problems) > 40:
            print(f"  ... and {len(problems) - 40} more", file=sys.stderr)
        return 1

    print("manifest OK: no wrong-year or wrong-trim photos")
    return 0


if __name__ == "__main__":
    sys.exit(main())