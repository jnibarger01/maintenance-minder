# Honda Maintenance Minder Explainer

A customer-facing web app that explains a Honda Maintenance Minder code in plain
language. A customer types the code from their dashboard (for example `A1` or
`B12`), optionally adds their vehicle, and gets a shareable explanation they can
print or read on a phone.

Live site: **https://jnibarger01.github.io/maintenance-minder/**

## How it works

The published site is fully static. It has no backend and makes no API calls of
its own — it reads two committed JSON files:

| File | Purpose |
| --- | --- |
| `data/models.json` | The vehicle catalogue (years, trims, body type). Single source of truth for the browser and the manifest builder. |
| `images.json` | A prebuilt map of `year\|model\|trim` to an official Honda photo. Generated, never hand-edited. |

Vehicle photos are **resolved at build time** by `scripts/resolver.py`, which
reads the Honda Info Center. URLs are hotlinked rather than committed, so the
repository stays free of image binaries and photo changes are picked up by a
scheduled workflow rather than a manual upload.

## Accuracy rules

The whole point of this tool is that it must never show a customer a vehicle
that isn't theirs. Three rules are enforced, and CI fails the build if any is
violated:

1. **Model year must match.** A photo's year is read from the `MY26_` asset name
   (authoritative), falling back to the `/2026-Accord/` folder path. A photo of a
   different year is rejected rather than scored down. This caught real
   wrong-year matches during development — a `2024 Accord` query was being served
   a `2023` image.
2. **Trim must not contradict.** An asset whose filename names a trim (Honda
   ships these as abbreviations: `EXL`, `TRG`, `HYBSP`) is rejected if it isn't
   the requested trim. A photo with no trim token is a generic model shot; it is
   allowed through but labelled *"model shown, not your trim"* in the UI.
3. **Prior-year photos are labelled.** Where a model year has no published photo
   yet, the prior year's image is used and marked as a reference, never presented
   as the customer's exact car.

Where no acceptable photo exists, the app shows a built-in vector silhouette and
says why, instead of substituting a different Honda.

```bash
python3 scripts/build_manifest.py          # rebuild images.json from the Info Center
python3 scripts/verify_manifest.py         # assert the accuracy rules hold
python3 scripts/build_manifest.py --check  # what CI runs before deploying
```

## Local development

```bash
python3 -m http.server 4173
```

Then open http://localhost:4173. Any static file server works; there is nothing
to install and no API to stub.

## Deep links

State lives in the URL, so an advisor can send a customer a pre-filled link:

```
/?code=B12
/?year=2023&model=CR-V&trim=EX-L&code=B12
```

## Layout

```
index.html              markup
styles.css              styles (minified)
app.js                  all behaviour: code parsing, vehicle state, manifest lookup
data/models.json        vehicle catalogue
images.json             generated photo manifest — do not hand-edit
scripts/resolver.py     Honda Info Center photo resolution
scripts/build_manifest.py  generates images.json
scripts/verify_manifest.py accuracy assertions, run in CI
.github/workflows/      Pages deploy + scheduled manifest refresh
```

## Code meanings

Subcode explanations cover the common Maintenance Minder items `1`–`7`. They
describe typical work, not a specific vehicle's schedule. Applicability depends
on model year, trim, engine, drivetrain and equipment. **The dashboard message
and the owner's manual are authoritative.**

This tool does not accept a VIN and does not retrieve an individual vehicle's
factory maintenance schedule.