"""Resolve an official Honda vehicle photo for a given year, model and trim.

Used by both entrypoints: server.py for local development and api/index.py when
deployed to Vercel.

Resolution order:
  1. photo-manifest.json, which points at the photos committed under images/.
  2. A live scrape of the Honda Info Center, so the app keeps working for
     vehicles that were not cached at build time.

Accuracy rules, enforced on the live-scrape path as well:
  - A photo's model year must equal the requested model year.
  - A photo that names a trim in its filename must name the requested trim.
  - Prior-year photos are only used as clearly-labelled references.

Showing a customer a different model year or a different trim as their own
vehicle is worse than showing them nothing, so misses are reported honestly.
"""

import json
import os
import re
from functools import lru_cache
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = ROOT / "photo-manifest.json"
HIC = "https://www.hondainfocenter.com"

HIC_SLUGS = {
    "Accord": "Accord", "Civic Sedan": "Civic-Sedan",
    "Civic Hatchback": "Civic-Hatchback", "Civic Si": "Civic-Si",
    "Civic Type R": "Civic-Type-R", "HR-V": "HR-V", "CR-V": "CR-V",
    "Passport": "Passport", "Pilot": "Pilot", "Odyssey": "Odyssey",
    "Ridgeline": "Ridgeline", "Prologue": "Prologue", "Prelude": "Prelude",
    "CR-V e:FCEV": "CR-V-e:FCEV", "Fit": "Fit", "Insight": "Insight",
    "Clarity": "Clarity",
}

# Models with no Info Center year-scoped page.
HARDCODED = {
    ("CR-V e:FCEV", 2025): {
        "image": "https://automobiles.honda.com/-/media/Honda-Automobiles/Vehicles/2025/cr-v-fcev/nonVLP/Global-Nav/MY25_CR-V-FCEV_Search_Inventory_Jelly.png?sc_lang=en",
        "source": "https://automobiles.honda.com/cr-v-fcev",
        "credit": "Honda • 2025 CR-V e:FCEV",
        "trimMatch": False,
    },
}

MY_YEAR_PATTERN = re.compile(r"[/_-]MY(20)?(\d\d)[_.-]", re.I)
FOLDER_YEAR_PATTERN = re.compile(r"/(20\d\d)-[A-Za-z0-9]", re.I)

# Honda asset filenames encode the trim with these abbreviations rather than the
# words used in the trim dropdown (e.g. "EX-L" ships as EXL, "Sport" as SP).
TRIM_ABBREVIATIONS = {
    "LX": ["LX"], "SPORT": ["SPORT", "SP"], "EX": ["EX"], "EXL": ["EXL"],
    "TOURING": ["TOURING", "TRG", "TRGT"], "ELITE": ["ELITE", "ELT"],
    "HYBRID": ["HYBRID", "HYB"], "HYBRIDSPORT": ["HYBSPORT", "HYBRIDSPORT", "HYBSP"],
    "HYBRIDEXL": ["HYBEXL", "HYBRIDEXL"], "HYBRIDTOURING": ["HYBTRG", "HYBRIDTOURING", "HYBTOURING"],
    "HYBRIDSPORTL": ["HYBSPTL", "HYBRIDSPORTL"], "HYBRIDEX": ["HYBEX", "HYBRIDEX"],
    "SPORTHYBRID": ["SPHYB", "SPORTHYBRID"], "SPORTTOURINGHYBRID": ["SPTRGHYB", "SPORTTOURINGHYBRID"],
    "SPORTL": ["SPTL", "SPORTL"], "SIXL": ["SIXL", "6XL"], "BLACKEDITION": ["BE", "BLKED", "BLACKEDITION"],
    "TRAILSPORT": ["TS", "TRAILSPORT", "TRLSPT"], "RTL": ["RTL"], "SI": ["SI"],
    "TYPER": ["TYPER"], "PLUGINHYBRID": ["PHEV", "PLUGINHYBRID"], "FUELCELL": ["FCV", "FUELCELL"],
    "EXTRG": ["EXTRG"], "LE": ["LE"],
}


def normalize(value):
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def asset_width(url):
    """Rendered width from the Info Center resize params, 0 when absent.

    The hash param pins a specific rendition, so these are the true pixel
    dimensions rather than a request the server may ignore.
    """
    match = re.search(r"[?&]w=(\d{2,5})", url)
    return int(match.group(1)) if match else 0


def asset_height(url):
    match = re.search(r"[?&]h=(\d{2,5})", url)
    return int(match.group(1)) if match else 0


def _years_from(pattern, url):
    years = set()
    for match in pattern.findall(url):
        digits = re.findall(r"\d{2,4}", "".join(match))
        if not digits:
            continue
        raw = digits[0]
        year = int(raw if len(raw) == 4 else "20" + raw)
        if 2015 <= year <= 2030:
            years.add(year)
    return years


def declared_years(url):
    """Model year of a photo, from the most authoritative signal available.

    The MY26_ asset name identifies the photographed vehicle directly and wins.
    The /2026-Accord/ folder only says where Honda filed the asset and is not
    always consistent with it, so it is used only as a fallback signal.
    """
    my_years = _years_from(MY_YEAR_PATTERN, url)
    if my_years:
        return my_years
    return _years_from(FOLDER_YEAR_PATTERN, url)


def requested_trim_tokens(trim):
    key = normalize(trim).upper()
    tokens = set(TRIM_ABBREVIATIONS.get(key, []))
    if key and key not in TRIM_ABBREVIATIONS:
        tokens.add(key)
    return tokens


def asset_trim_tokens(url):
    """All recognised trim tokens present in an asset filename.

    Runs against uppercased path segments split on separators, so EXL matches
    "MY23_ACCORD_EXL_jelly" while avoiding substring hits like SI in SIEBEL.
    """
    name = url.rsplit("/", 1)[-1].split("?")[0].upper()
    known = {token for tokens in TRIM_ABBREVIATIONS.values() for token in tokens}
    found = set()
    for segment in re.split(r"[^A-Z0-9]+", name):
        if segment in known:
            found.add(segment)
            continue
        # Some tokens carry the model year, e.g. TRG20 / LX22.
        stripped = re.sub(r"\d+$", "", segment)
        if stripped and stripped in known:
            found.add(stripped)
    return found


@lru_cache(maxsize=256)
def fetch(url):
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 HondaMaintenanceMinder/1.0"})
    with urlopen(request, timeout=20) as response:
        return response.read(3_000_000).decode("utf-8", "ignore")


class ImageParser(HTMLParser):
    def __init__(self, base):
        super().__init__()
        self.base, self.images = base, []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "img":
            return
        values = dict(attrs)
        for key in ("src", "data-src", "data-original"):
            value = values.get(key, "")
            if value and not value.startswith("data:"):
                self.images.append(urljoin(self.base, value))
        srcset = values.get("srcset", "")
        if srcset:
            self.images.extend(
                urljoin(self.base, item.strip().split()[0])
                for item in srcset.split(",")
                if item.strip()
            )


def load_manifest():
    """Committed photo cache, reloaded when the file changes during dev."""
    try:
        stat = os.stat(MANIFEST_PATH)
        signature = (stat.st_mtime, stat.st_size)
    except OSError:
        return {}

    cached = load_manifest._cached
    if cached and cached[0] == signature:
        return cached[1]

    try:
        payload = json.loads(MANIFEST_PATH.read_text())
    except (OSError, ValueError):
        return {}

    entries = payload.get("entries", {})
    load_manifest._cached = (signature, entries)
    return entries


load_manifest._cached = None


def from_cache(year, model, trim):
    """Photo committed under images/, or None if this vehicle isn't cached."""
    entries = load_manifest()
    record = entries.get(f"{year}|{model}|{trim}")
    if record is None and trim:
        record = entries.get(f"{year}|{model}|__default__")
    if not record:
        return None
    if not (ROOT / "images" / record["file"]).exists():
        return None

    result = {
        "found": True,
        "image": f"/images/{record['file']}",
        "credit": record.get("credit", "Honda"),
        "source": record.get("source", HIC),
        # Trust the record's flag only when this photo was resolved for the trim
        # that was actually requested. A __default__ record was resolved for
        # whichever trim matched, so it can never be an exact trim match.
        "trimMatch": bool(record.get("trimMatch")) and record.get("trim") == trim,
    }
    if record.get("fallback"):
        result["fallback"] = True
    if record.get("width"):
        result["width"] = record["width"]
    return result


def from_infocenter(year, model, trim):
    slug = HIC_SLUGS[model]
    if model == "Clarity":
        slug = "Clarity-Fuel-Cell" if "fuel" in (trim or "").lower() else "Clarity-Plug-In-Hybrid"
    hic_url = f"{HIC}/{year}/{slug}/"

    try:
        page = fetch(hic_url)
    except Exception:
        return None

    parser = ImageParser(hic_url)
    parser.feed(page)

    model_key = normalize(model)
    trim_key = normalize(trim)
    wanted_tokens = requested_trim_tokens(trim)
    candidates = []

    for image in dict.fromkeys(parser.images):
        low = image.lower()
        if "honda-sales-tool-media-folder/images/" not in low:
            continue
        if not any(mark in low for mark in ("jelly", "header", "vehicle", "hero")):
            continue
        if model == "Civic Sedan" and "coupe" in low:
            continue
        if "past-models" in low or ".pdf" in low:
            continue

        # Model year must match exactly.
        years = declared_years(image)
        if years and year not in years:
            continue

        # Trim must not contradict the request. An asset naming a different trim
        # is rejected; an asset naming no trim is a generic model shot and is
        # allowed through, but flagged as trim-agnostic.
        asset_trims = asset_trim_tokens(image)
        if trim_key and trim_key != "otherentertrim":
            if asset_trims and not (asset_trims & wanted_tokens):
                continue
            trim_match = bool(asset_trims & wanted_tokens)
        else:
            trim_match = not asset_trims

        # Prefer width over the "jelly" filename, which the site uses for its
        # 164px colour swatches.
        score = 10 + min(asset_width(image) // 50, 24)
        if trim_match:
            score += 70
        if model_key and model_key in normalize(image):
            score += 15
        candidates.append((score, image, trim_match))

    if not candidates:
        return None

    _, image, trim_match = sorted(candidates, reverse=True)[0]
    return {
        "found": True,
        "image": image,
        "source": hic_url,
        "credit": f"Honda Info Center • {year} {model}",
        "trimMatch": bool(trim_match),
        "width": asset_width(image) or None,
        "height": asset_height(image) or None,
    }


def resolve(year, model, trim):
    """Return a photo entry for the vehicle, or a not-found reason.

    Never raises: a failure to reach Honda is reported as a miss so the app can
    fall back to the built-in silhouette.
    """
    if model not in HIC_SLUGS or not 2015 <= year <= 2027:
        return {"found": False, "reason": "Unsupported year or model."}

    cached = from_cache(year, model, trim)
    if cached:
        return cached

    hardcoded = HARDCODED.get((model, year))
    if hardcoded:
        return {"found": True, **hardcoded}

    hit = from_infocenter(year, model, trim)
    if hit:
        return hit

    # Newer model years often have no published photo yet. Use the prior year but
    # mark it clearly as a reference, never as the customer's exact car.
    if year >= 2026:
        reference = from_cache(year - 1, model, trim) or from_infocenter(year - 1, model, trim)
        if reference and reference.get("found"):
            result = dict(reference)
            result["fallback"] = True
            result["trimMatch"] = False
            result["credit"] = (
                f"Honda photo reference • {year - 1} {model} "
                f"(closest published image for {year})"
            )
            return result

    return {
        "found": False,
        "reason": f"No matching official image found for the {year} Honda {model}.",
    }