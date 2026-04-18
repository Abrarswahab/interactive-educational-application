"""
Smart Explorer — Vision backend
POST /detect: upload an image, get back Google Vision's object localization results.
"""

import glob
import io
import json
import logging
import os
from typing import List, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from google.cloud import vision
from google.oauth2 import service_account
from pydantic import BaseModel

# ----------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("vision-backend")

# ----------------------------------------------------------------------
# Google Vision client
# ----------------------------------------------------------------------
# Credentials are loaded in this order:
#   1. GOOGLE_APPLICATION_CREDENTIALS_JSON env var → the full JSON blob as a string
#      (best for Render / Cloud Run — no file on disk).
#   2. GOOGLE_APPLICATION_CREDENTIALS env var → explicit path to a JSON key file.
#   3. Auto-detect: any *.json file in this folder that looks like a service
#      account key. This means local dev "just works" no matter what Google
#      named your downloaded key file.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _find_service_account_file() -> Optional[str]:
    """Scan BASE_DIR for a JSON file that looks like a Google service account key."""
    for path in glob.glob(os.path.join(BASE_DIR, "*.json")):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Service account keys always have these two fields
            if data.get("type") == "service_account" and "private_key" in data:
                return path
        except (json.JSONDecodeError, OSError):
            continue
    return None


def _build_vision_client() -> vision.ImageAnnotatorClient:
    """Load credentials from env or disk and return a Vision client."""
    # 1. Inline JSON via env var (preferred for cloud deployments)
    inline_json = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")
    if inline_json:
        info = json.loads(inline_json)
        creds = service_account.Credentials.from_service_account_info(info)
        log.info("Loaded Vision credentials from GOOGLE_APPLICATION_CREDENTIALS_JSON env var.")
        return vision.ImageAnnotatorClient(credentials=creds)

    # 2. Explicit file path via env var
    explicit_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if explicit_path and os.path.exists(explicit_path):
        creds = service_account.Credentials.from_service_account_file(explicit_path)
        log.info(f"Loaded Vision credentials from GOOGLE_APPLICATION_CREDENTIALS: {explicit_path}")
        return vision.ImageAnnotatorClient(credentials=creds)

    # 3. Auto-detect any service-account JSON sitting next to main.py
    auto_path = _find_service_account_file()
    if auto_path:
        creds = service_account.Credentials.from_service_account_file(auto_path)
        log.info(f"Auto-detected service account key: {os.path.basename(auto_path)}")
        return vision.ImageAnnotatorClient(credentials=creds)

    raise RuntimeError(
        "No Google credentials found. Either:\n"
        "  • set GOOGLE_APPLICATION_CREDENTIALS_JSON env var (cloud), or\n"
        "  • set GOOGLE_APPLICATION_CREDENTIALS env var to a key file path, or\n"
        f"  • drop your service-account JSON key into {BASE_DIR}"
    )


vision_client = _build_vision_client()

# ----------------------------------------------------------------------
# FastAPI app
# ----------------------------------------------------------------------
app = FastAPI(title="Smart Explorer Vision API", version="1.0.0")

# Streamlit frontend talks to this API from a different origin → enable CORS.
# Lock this down to your real Streamlit URL in production if you want to be strict.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------------------------------------------------
# Response schema
# ----------------------------------------------------------------------
class DetectedObject(BaseModel):
    name: str
    confidence: float


class DetectResponse(BaseModel):
    count: int
    objects: List[DetectedObject]


# ----------------------------------------------------------------------
# Endpoints
# ----------------------------------------------------------------------
@app.get("/")
def root():
    return {
        "status": "ok",
        "service": "Smart Explorer Vision API",
        "endpoints": {
            "POST /detect": "Upload an image, get detected objects + confidence",
            "GET  /health": "Health check",
            "GET  /docs":   "Interactive API docs",
        },
    }


@app.get("/health")
def health():
    return {"status": "healthy", "vision_client": vision_client is not None}


# File-size guard — Google Vision caps uploads at ~20 MB per request.
MAX_IMAGE_BYTES = 20 * 1024 * 1024


@app.post("/detect", response_model=DetectResponse)
async def detect(file: UploadFile = File(...)):
    """
    Accept an uploaded image, run Google Vision's object localization on it,
    and return the list of detected objects with confidence scores.
    """
    # ---- Validate content type ------------------------------------------
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=400,
            detail=f"Expected an image upload, got content_type={file.content_type!r}",
        )

    # ---- Read bytes -----------------------------------------------------
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file.")
    if len(raw) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Image too large ({len(raw)} bytes). Max is {MAX_IMAGE_BYTES}.",
        )

    # ---- Call Vision ----------------------------------------------------
    image = vision.Image(content=raw)
    try:
        response = vision_client.object_localization(image=image)
    except Exception as e:
        log.exception("Vision API call failed")
        raise HTTPException(status_code=502, detail=f"Vision API error: {e}")

    if response.error.message:
        # Google returns errors inside the response body, not as exceptions
        raise HTTPException(status_code=502, detail=response.error.message)

    objects = [
        DetectedObject(name=obj.name, confidence=round(float(obj.score), 4))
        for obj in response.localized_object_annotations
    ]
    # Sort most-confident first so the frontend can grab objects[0] for the top hit.
    objects.sort(key=lambda o: o.confidence, reverse=True)

    log.info(f"/detect → {len(objects)} objects: {[o.name for o in objects[:5]]}")
    return DetectResponse(count=len(objects), objects=objects)


# ----------------------------------------------------------------------
# Local dev entrypoint: `python main.py`
# (In production, uvicorn is invoked by the Dockerfile CMD.)
# ----------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
