# Honda Maintenance Minder Explainer

A customer-facing web app that explains a Honda Maintenance Minder code in plain
language. A customer types the code from their dashboard (for example `A1` or
`B12`), optionally adds their vehicle, and gets a shareable explanation they can
print or read on a phone.

Deployed on Vercel: the frontend is static, and `api/index.py` runs the Python
photo resolver as a serverless function.

## Architecture

`server.py` is the local development server and `api/index.py` is the same set of
routes as a FastAPI app for Vercel. Both delegate to `photo_resolver.py`, so the
two behave identically.

| Route | Purpose |
| --- | --- |
| `GET /api/vehicle-image?year=&model=&trim=` | Resolves an official Honda photo. |
| `GET /api/health` | Liveness check. |
| `GET /images/<file>.png` | Served by Vercel's CDN as a static asset, not by the function. |

The frontend is served as static files: `index.html`, `styles.css`, `app.js`,
`data/models.json`, `favicon.svg`.

### Why the cache is a Python module

`photo_manifest.py` is generated from `photo-manifest.json` and imported, not
read with `open()`. Vercel builds a function bundle by tracing imports, so a JSON
file opened at runtime is never included — the entire photo cache would silently
vanish in production and every request would fall back to a live scrape. For the
same reason the 195 photos under `images/` are static assets served from the CDN
rather than bundled into the function, which keeps it around 330KB.

Regenerate the module after editing the manifest:

```bash
python3 scripts/build_photo_manifest.py
```

### Where photos come from

Resolution runs in the backend, in this order:

1. **`photo-manifest.json` + `images/`** — 195 verified photos committed to the
   repository, keyed by `year|model|trim`. This is the fast path and it keeps the
   app working if Honda's site is unreachable.
2. **Live scrape of the Honda Info Center** — for vehicles that were not cached,
   so the app covers newer vehicles without a redeploy.

Each manifest record stores the `sourceUrl` it was verified against alongside the
committed file, so the year and trim checks still work even though the cached
files are named by content hash.

## Accuracy rules

The point of this tool is that it must never show a customer a vehicle that isn't
theirs. Three rules are enforced, and `verify_photos.py` runs in CI:

1. **Model year must match.** A photo's year is read from the `MY26_` asset name
   (authoritative), falling back to the `/2026-Accord/` folder path. A photo of a
   different year is rejected outright. This caught real wrong-year matches
   during development — a `2024 Accord` query was being served a `2023` image.
2. **Trim must not contradict.** An asset whose filename names a trim (Honda ships
   these as abbreviations: `EXL`, `TRG`, `HYBSP`) is rejected if it isn't the
   requested trim. A photo with no trim token is a generic model shot; it is
   allowed through but labelled *"model shown, not your trim"* in the UI.
3. **Prior-year photos are labelled.** Where a model year has no published photo
   yet, the prior year's image is used and marked as a reference, never presented
   as the customer's exact car.

Where no acceptable photo exists, the app shows a built-in vector silhouette and
says why, instead of substituting a different Honda. Photos too small to render
(the Info Center's 164px colour swatches, which are the only size the CDN serves)
also fall back to the silhouette, with a link to the official image.

```bash
python3 verify_photos.py    # assert the accuracy rules hold against the manifest
```

## Local development

```bash
python3 server.py                     # http://localhost:4173, no dependencies
```

Or to run the Vercel entrypoint the way production does:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn api.index:app --port 4180
```

## Deep links

State lives in the URL, so an advisor can send a customer a pre-filled link:

```
/?code=B12
/?year=2023&model=CR-V&trim=EX-L&code=B12
```

## Layout

```
index.html              markup
styles.css              styles
app.js                  code parsing, vehicle state, photo rendering
data/models.json        vehicle catalogue
images/                 195 cached Honda photos (committed)
photo-manifest.json     key -> cached file + verified source URL (source of truth)
photo_manifest.py       generated importable copy, so Vercel bundles the cache
scripts/build_photo_manifest.py  regenerates photo_manifest.py from the JSON
photo_resolver.py       cache-first resolution with live-scrape fallback
server.py               local development server
api/index.py            FastAPI app for Vercel
verify_photos.py        accuracy assertions, run in CI
vercel.json             routes /api and /images to the function
```

## Code meanings

Subcode explanations cover the common Maintenance Minder items `1`–`7`. They
describe typical work, not a specific vehicle's schedule. Applicability depends on
model year, trim, engine, drivetrain and equipment. **The dashboard message and
the owner's manual are authoritative.**

This tool does not accept a VIN and does not retrieve an individual vehicle's
factory maintenance schedule.