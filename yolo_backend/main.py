"""
Smart Explorer backend — one endpoint, everything bundled.

POST /segment accepts an image and returns JSON containing:
  - label_ar         : detected class translated to Arabic
  - label_en         : raw YOLO class name
  - confidence       : top confidence score
  - coverage_percent : % of image covered by the dominant object (segmentation)
  - spelling         : list of Arabic letters in the word
  - annotated_image  : base64 PNG with YOLO boxes + masks + Arabic label
  - audio_word       : base64 MP3 pronouncing the whole word
  - audio_letters    : list of {letter, audio} for letter-by-letter playback
"""

import base64
import io
import logging
import os
import urllib.parse
import urllib.request
from functools import lru_cache
from typing import Optional

import arabic_reshaper
from bidi.algorithm import get_display
from deep_translator import GoogleTranslator
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel
from ultralytics import YOLO

# ----------------------------------------------------------------------
# Setup
# ----------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("smart-explorer")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "best.pt")
FONT_PATH = os.path.join(BASE_DIR, "NotoNaskhArabic-Regular.ttf")

# Load YOLO once at startup
log.info(f"Loading model from {MODEL_PATH}")
model = YOLO(MODEL_PATH)
log.info(f"Model loaded. Classes: {list(model.names.values())[:10]}...")

# Arabic font for burning the label onto the annotated image
try:
    FONT = ImageFont.truetype(FONT_PATH, 48)
except Exception:
    log.warning(f"Arabic font not found at {FONT_PATH}, falling back to default")
    FONT = ImageFont.load_default()

translator = GoogleTranslator(source="en", target="ar")

app = FastAPI(title="Smart Explorer API", version="3.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
# Arabic diacritics (harakat) — we strip these before spelling
_DIACRITICS = set("ًٌٍَُِّْٰٱؐؑؒؓؔؕؖؗ")


@lru_cache(maxsize=512)
def translate_to_arabic(en_name: str) -> str:
    """English class name -> Arabic. Cached so we only hit Google once per class."""
    clean = en_name.replace("_", " ").strip()
    try:
        result = translator.translate(clean)
        return result if result else clean
    except Exception as e:
        log.warning(f"Translation failed for '{clean}': {e}")
        return clean


def spell_word(word: str) -> list:
    """Break an Arabic word into its individual letters, skipping spaces and diacritics."""
    return [ch for ch in word if ch.strip() and ch not in _DIACRITICS]


def shape_arabic(text: str) -> str:
    """Reshape Arabic text so PIL draws the letters correctly connected and right-to-left."""
    return get_display(arabic_reshaper.reshape(text))


@lru_cache(maxsize=1024)
def synth_audio_b64(text: str) -> Optional[str]:
    """
    Use Google Translate's free TTS endpoint to synthesize Arabic speech for a word or
    single letter. Returns a base64-encoded MP3 as a data: URI, or None on failure.
    Cached aggressively so repeated words / letters don't re-fetch.
    """
    if not text or not text.strip():
        return None
    try:
        url = (
            "https://translate.google.com/translate_tts"
            f"?ie=UTF-8&q={urllib.parse.quote(text)}&tl=ar&client=tw-ob"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            mp3_bytes = resp.read()
        encoded = base64.b64encode(mp3_bytes).decode("ascii")
        return f"data:audio/mp3;base64,{encoded}"
    except Exception as e:
        log.warning(f"TTS failed for '{text}': {e}")
        return None


def annotate_image(results, image: Image.Image, ar_label: str, coverage_pct: float) -> Image.Image:
    """Draw YOLO's boxes/masks, then burn the Arabic label in the top-right corner."""
    annotated = Image.fromarray(results.plot()[:, :, ::-1])  # YOLO returns BGR -> flip to RGB
    label_text = shape_arabic(f"{ar_label} ({coverage_pct:.1f}%)")

    draw = ImageDraw.Draw(annotated, "RGBA")
    bbox = draw.textbbox((0, 0), label_text, font=FONT)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = annotated.width - w - 20
    y = 20
    draw.rectangle([x - 10, y - 10, x + w + 10, y + h + 10], fill=(0, 0, 0, 180))
    draw.text((x, y), label_text, font=FONT, fill=(255, 255, 255))
    return annotated


def image_to_b64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


# ----------------------------------------------------------------------
# Response schema
# ----------------------------------------------------------------------
class LetterAudio(BaseModel):
    letter: str
    audio: Optional[str]


class SegmentResponse(BaseModel):
    label_ar: str
    label_en: str
    confidence: float
    coverage_percent: float
    spelling: list
    annotated_image: str
    audio_word: Optional[str]
    audio_letters: list


# ----------------------------------------------------------------------
# Endpoints
# ----------------------------------------------------------------------
@app.get("/")
def root():
    return {
        "status": "ok",
        "service": "Smart Explorer API",
        "model_classes": len(model.names),
        "endpoints": {
            "POST /segment": "Upload an image, get everything back in one response",
            "GET  /health":  "Health check",
            "GET  /docs":    "Interactive API docs",
        },
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "model_loaded": model is not None,
        "num_classes": len(model.names) if model else 0,
    }


@app.post("/segment", response_model=SegmentResponse)
async def segment(file: UploadFile = File(...)):
    # ---- Read + validate image -------------------------------------------
    try:
        raw = await file.read()
        img = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid image: {e}")

    # ---- Run YOLO segmentation -------------------------------------------
    results = model.predict(img, device="cpu", verbose=False, imgsz=640)[0]

    if results.masks is None or len(results.masks) == 0:
        raise HTTPException(
            status_code=422,
            detail="لم أتمكن من التعرف على أي شيء. حاول مع صورة أوضح!",
        )

    # ---- Find the dominant class (largest total mask area) ---------------
    masks = results.masks.data.cpu().numpy()            # (N, H, W)
    cls_ids = results.boxes.cls.cpu().numpy().astype(int)
    confs = results.boxes.conf.cpu().numpy()

    # Accumulate area + best confidence per class
    class_stats = {}
    for m, c, conf in zip(masks, cls_ids, confs):
        s = class_stats.setdefault(int(c), {"area": 0.0, "conf": 0.0})
        s["area"] += float(m.sum())
        if conf > s["conf"]:
            s["conf"] = float(conf)

    top_cls = max(class_stats, key=lambda k: class_stats[k]["area"])
    label_en = model.names[top_cls]
    top_conf = class_stats[top_cls]["conf"]

    total_pixels = img.width * img.height
    coverage_pct = 100.0 * class_stats[top_cls]["area"] / total_pixels

    # ---- Translate + spell -----------------------------------------------
    label_ar = translate_to_arabic(label_en)
    letters = spell_word(label_ar)

    # ---- Annotate image --------------------------------------------------
    annotated = annotate_image(results, img, label_ar, coverage_pct)
    annotated_b64 = image_to_b64(annotated)

    # ---- Generate audio (word + each letter) -----------------------------
    audio_word = synth_audio_b64(label_ar)
    audio_letters = [
        {"letter": ch, "audio": synth_audio_b64(ch)}
        for ch in letters
    ]

    log.info(
        f"✅ {label_en} -> {label_ar} | conf={top_conf:.2f} | "
        f"coverage={coverage_pct:.1f}% | letters={len(letters)}"
    )

    return SegmentResponse(
        label_ar=label_ar,
        label_en=label_en,
        confidence=round(top_conf, 3),
        coverage_percent=round(coverage_pct, 2),
        spelling=letters,
        annotated_image=annotated_b64,
        audio_word=audio_word,
        audio_letters=audio_letters,
    )