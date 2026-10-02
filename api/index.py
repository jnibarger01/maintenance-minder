"""FastAPI entrypoint for Vercel.

Vercel serves static files from the repository root and routes /api/* to this
function. Photo resolution lives in photo_resolver.py, which is shared with the
local server.py so both paths behave identically.
"""

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

# Vercel's Python runtime imports this file as a module, so the repo root is not
# guaranteed to be on the path.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import photo_resolver  # noqa: E402

app = FastAPI(title="Honda Maintenance Minder Explainer", docs_url=None, redoc_url=None)

# The frontend is same-origin in production; CORS is only needed to allow local
# development against the deployed function.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/vehicle-image")
def vehicle_image(year: int = 0, model: str = "", trim: str = ""):
    """Resolve an official Honda photo for a year/model/trim.

    Returns {found: false, reason} rather than a substitute photo when no
    acceptable image exists for the exact vehicle.
    """
    payload = photo_resolver.resolve(year, model, trim)
    # Cached responses are stable; misses and live scrapes are not.
    headers = {"Cache-Control": "public, max-age=86400"} if payload.get("found") else {"Cache-Control": "no-store"}
    return JSONResponse(payload, headers=headers)


@app.get("/images/{filename}")
def cached_image(filename: str):
    """Serve a photo committed under images/.

    Static hosting usually covers this path, but the Vercel function owns it
    when the static layer is bypassed.
    """
    if "/" in filename or "\\" in filename or ".." in filename or not filename.endswith(".png"):
        return Response(status_code=404)
    path = ROOT / "images" / filename
    if not path.is_file():
        return Response(status_code=404)
    return Response(
        path.read_bytes(),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )