"""Resolve official Honda vehicle photos for a given year/model/trim.

Used at build time to generate images.json for the static GitHub Pages app.
This module contains no server code; the published site never calls it.
"""

import re
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
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

# Hardcoded where the Info Center has no year-scoped page.
HARDCODED = {
    ("CR-V e:FCEV", 2025): {
        "image": "https://automobiles.honda.com/-/media/Honda-Automobiles/Vehicles/2025/cr-v-fcev/nonVLP/Global-Nav/MY25_CR-V-FCEV_Search_Inventory_Jelly.png?sc_lang=en",
        "source": "https://automobiles.honda.com/cr-v-fcev",
        "credit": "Honda • 2025 CR-V e:FCEV",
    },
}

# A year published as a MY26_/MY25_ asset name or a /2026-Accord/ folder.
MY_YEAR_PATTERN = re.compile(r"[/_-]MY(20)?(\d\d)[_.-]", re.I)
FOLDER_YEAR_PATTERN = re.compile(r"/(20\d\d)-[A-Za-z0-9]", re.I)


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
    """The model year of a photo, from the most authoritative signal available.

    The MY26_ asset name identifies the photographed vehicle directly and takes
    precedence. The /2026-Accord/ folder only says where Honda filed the asset and
    is not always consistent with it, so it is used only as a fallback signal.
    Returns an empty set when neither yields a usable year.
    """
    my_years = _years_from(MY_YEAR_PATTERN, url)
    if my_years:
        return my_years
    return _years_from(FOLDER_YEAR_PATTERN, url)


def normalize(value):
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def asset_width(url):
    """Rendered width from the Info Center resize params, 0 when absent.

    The hash param pins a specific rendition, so these values reflect the true
    pixel size rather than a server-side upscale request.
    """
    match = re.search(r"[?&]w=(\d{2,5})", url)
    return int(match.group(1)) if match else 0


def asset_height(url):
    match = re.search(r"[?&]h=(\d{2,5})", url)
    return int(match.group(1)) if match else 0


# Honda asset filenames encode the trim with these abbreviations rather than
# the words used in the trim dropdown (e.g. "EX-L" ships as EXL, "Sport" as SP).
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


def requested_trim_tokens(trim):
    """Filename tokens that identify the requested trim."""
    key = normalize(trim).upper()
    tokens = set(TRIM_ABBREVIATIONS.get(key, []))
    if key and key not in TRIM_ABBREVIATIONS:
        tokens.add(key)
    return tokens


def asset_trim_tokens(url):
    """All recognised trim tokens present in an asset filename.

    Matching runs against uppercased path segments split on separators, so
    EXL matches "MY23_ACCORD_EXL_jelly" while avoiding substring false
    positives such as "SI" inside "SIEBEL".
    """
    name = url.rsplit("/", 1)[-1].split("?")[0].upper()
    known = {token for tokens in TRIM_ABBREVIATIONS.values() for token in tokens}
    found = set()
    for segment in re.split(r"[^A-Z0-9]+", name):
        if segment in known:
            found.add(segment)
            continue
        # Honda appends the model year to some tokens, e.g. TRG20 / LX22.
        stripped = re.sub(r"\d+$", "", segment)
        if stripped and stripped in known:
            found.add(stripped)
    return found


@lru_cache(maxsize=256)
def fetch(url):
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 MaintenanceMinderExplainer/1.0"})
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


def _from_infocenter(year, model, trim):
    hic_url = f"{HIC}/{year}/{HIC_SLUGS[model]}/"
    try:
        page = fetch(hic_url)
    except Exception:
        return None

    parser = ImageParser(hic_url)
    parser.feed(page)

    model_key = normalize(model)
    trim_key = normalize(trim)
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

        # Year must match. A photo of a different model year shown to a
        # customer as their vehicle is worse than showing no photo at all.
        years = declared_years(image)
        if years and year not in years:
            continue

        # Trim must not contradict the request. An asset that names a different
        # trim is rejected outright; an asset that names no trim is a generic
        # model shot and is allowed through, but flagged as trim-agnostic.
        asset_trims = asset_trim_tokens(image)
        if trim_key and trim_key != "otherentertrim":
            if asset_trims and not (asset_trims & requested_trim_tokens(trim)):
                continue
            trim_match = bool(asset_trims & requested_trim_tokens(trim))
        else:
            trim_match = not asset_trims

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
        "image": image,
        "source": hic_url,
        "credit": f"Honda Info Center • {year} {model}",
        "width": asset_width(image) or None,
        "height": asset_height(image) or None,
        # False means this is a shot of the model year, not the customer's trim.
        "trimMatch": bool(trim_match),
    }


# The Honda Newsroom was previously used as a secondary source. It was removed
# deliberately: its card images are 364x204 thumbnails behind opaque per-article
# S3 hashes, so the model year cannot be verified from the URL. Those matches
# could not pass the year gate in _from_infocenter, and a wrong-year photo shown
# to a customer as their own vehicle is worse than showing none.


def resolve(year, model, trim):
    """Return a photo entry for the exact year/model, or a not-found reason.

    ``fallback`` entries use the prior model year and are labelled as such so
    the UI never presents them as the customer's exact vehicle.
    """
    if model not in HIC_SLUGS or not 2015 <= year <= 2027:
        return {"found": False, "reason": "Unsupported year or model."}

    hardcoded = HARDCODED.get((model, year))
    if hardcoded:
        return {"found": True, **hardcoded}

    slug = HIC_SLUGS[model]
    if model == "Clarity":
        slug = "Clarity-Fuel-Cell" if "fuel" in (trim or "").lower() else "Clarity-Plug-In-Hybrid"

    if model != "Clarity":
        hit = _from_infocenter(year, model, trim)
        if hit:
            return {"found": True, **hit}
    else:
        hic_url = f"{HIC}/{year}/{slug}/"
        try:
            page = fetch(hic_url)
            parser = ImageParser(hic_url)
            parser.feed(page)
            images = [
                url for url in dict.fromkeys(parser.images)
                if "/images/" in url and "past-models" not in url.lower()
            ]
            if images:
                return {
                    "found": True,
                    "image": images[0],
                    "source": hic_url,
                    "credit": f"Honda Info Center • {year} {model}",
                }
        except Exception:
            pass

    # Newer model years often have no published photo yet. Fall back to the
    # prior year but mark it clearly as a reference, never as the exact car.
    if year >= 2026:
        reference = resolve(year - 1, model, trim)
        if reference.get("found"):
            return {
                "found": True,
                **reference,
                # A prior-year photo is not an exact match for this vehicle.
                "fallback": True,
                "trimMatch": False,
                "credit": (
                    f"Honda photo reference • {year - 1} {model} "
                    f"(closest published image for {year})"
                ),
            }

    return {
        "found": False,
        "reason": f"No matching official image found for the {year} Honda {model}.",
    }


def resolve_many(combinations, workers=8):
    """Resolve many (year, model, trim) tuples concurrently."""
    results = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(resolve, year, model, trim): (year, model, trim)
            for year, model, trim in combinations
        }
        for future, key in futures.items():
            try:
                results["%d|%s|%s" % key] = future.result()
            except Exception as error:
                results["%d|%s|%s" % key] = {
                    "found": False,
                    "reason": f"Resolver error: {error}",
                }
    return results