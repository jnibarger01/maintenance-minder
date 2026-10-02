#!/usr/bin/env python3
"""Generate images.json for the static site.

Resolves an official Honda photo for every year/model/trim combination the app
offers, plus a per-year/model default used when a customer types a custom trim
name that we did not pre-resolve.

Usage:
    python3 scripts/build_manifest.py            # refresh, keep previous on total failure
    python3 scripts/build_manifest.py --check    # exit 1 if manifest is missing/stale
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from resolver import resolve, resolve_many  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "models.json"
MANIFEST = ROOT / "images.json"


def trims_for(spec, year, model):
    """Trims actually offered for this year and model."""
    if model["name"] != "Clarity":
        return model["trims"]
    if year == 2017:
        return ["Fuel Cell"]
    if 2018 <= year <= 2021:
        return ["Plug-In Hybrid", "Fuel Cell"]
    return []


def combinations(spec):
    for model in spec["models"]:
        first, last = model["years"]
        excluded = set(model.get("exclude", []))
        for year in range(first, last + 1):
            if year in excluded:
                continue
            for trim in trims_for(spec, year, model):
                yield year, model["name"], trim


def combos_for(spec, year, model_name):
    model = next((m for m in spec["models"] if m["name"] == model_name), None)
    return trims_for(spec, year, model) if model else []


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="validate without rewriting")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    spec = json.loads(DATA.read_text())

    if args.check:
        if not MANIFEST.exists():
            print("images.json missing", file=sys.stderr)
            return 1
        manifest = json.loads(MANIFEST.read_text())
        expected = len(set(combinations(spec)))
        actual = len(manifest.get("entries", {}))
        print(f"images.json: {actual} entries, {expected} expected")
        if actual < expected:
            print(f"stale: manifest covers {actual} of {expected} combinations", file=sys.stderr)
            return 1
        # Re-run the accuracy assertions so a bad manifest blocks a deploy.
        import verify_manifest

        problems, _stats = verify_manifest.verify(manifest)
        if problems:
            print(f"{len(problems)} manifest problem(s):", file=sys.stderr)
            for problem in problems[:20]:
                print(f"  - {problem}", file=sys.stderr)
            return 1
        print("manifest OK")
        return 0

    combos = list(combinations(spec))
    print(f"resolving {len(combos)} year/model/trim combinations...")
    started = time.time()

    entries = resolve_many(combos, workers=args.workers)

    # Per-year/model default: the first photo resolved for that vehicle, used
    # when a customer types a custom trim name. It cannot claim an exact trim
    # match, so trimMatch is cleared rather than inherited from the source trim.
    defaults = {}
    for year, model, _trim in combos:
        key = f"{year}|{model}|__default__"
        if key in defaults:
            continue
        for candidate in combos_for(spec, year, model):
            hit = entries.get(f"{year}|{model}|{candidate}", {})
            if hit.get("found"):
                defaults[key] = {**hit, "genericTrim": True, "trimMatch": False}
                break

    entries.update(defaults)

    matched = sum(1 for entry in entries.values() if entry.get("found"))
    fallback = sum(1 for entry in entries.values() if entry.get("fallback"))

    payload = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": "hondainfocenter.com, hondanews.com",
        "entries": dict(sorted(entries.items())),
    }

    MANIFEST.write_text(json.dumps(payload, indent=0, sort_keys=True) + "\n")

    total = len(entries)
    print(
        f"wrote {MANIFEST.relative_to(ROOT)}: {total} entries, "
        f"{matched} matched, {fallback} prior-year references, "
        f"{total - matched} unmatched, {time.time() - started:.0f}s"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())