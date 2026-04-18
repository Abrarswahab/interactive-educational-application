"""
Smart Explorer backend — one endpoint, everything bundled.

POST /segment accepts an image and returns JSON containing:
  - label_ar         : detected class translated to Arabic
  - label_en         : raw YOLO class name
  - confidence       : top confidence score
  - coverage_percent : % of image covered by the dominant object (segmentation)
  - spelling         : list of Arabic letters in the word
  - annotated_image  : base64 PNG with YOLO boxes + masks + Arabic label
  - audio_word       : base64 MP3 pronouncing the whole word (via edge-tts)
  - audio_letters    : list of {letter, audio} for letter-by-letter playback
  - model_used       : which model produced the result ("custom" or "fallback")

CHANGES vs v3.0.0:
  - TTS: replaced Google Translate scrape with edge-tts (Microsoft Neural Arabic voices)
  - Added YOLOv8x-seg as a high-class-count fallback model (80 COCO classes)
    used when custom model confidence < FALLBACK_CONF_THRESHOLD (0.45)
"""

import asyncio
import base64
import io
import logging
import os
import tempfile
from functools import lru_cache
from typing import Optional

import arabic_reshaper
import edge_tts
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

# Confidence threshold — if custom model is below this, fallback model is tried
FALLBACK_CONF_THRESHOLD = 0.45

# edge-tts Arabic voices
# ar-SA-ZariyahNeural  → female, warm, natural (great for kids)
# ar-SA-HamedNeural    → male, clear
EDGE_TTS_VOICE = "ar-SA-ZariyahNeural"

# ----------------------------------------------------------------------
# Load models
# ----------------------------------------------------------------------
log.info(f"Loading custom model from {MODEL_PATH}")
custom_model = YOLO(MODEL_PATH)
log.info(f"Custom model loaded — {len(custom_model.names)} classes: {list(custom_model.names.values())[:8]}...")

log.info("Loading fallback model YOLOv8x-seg (COCO 80 classes) — auto-downloads if needed")
try:
    fallback_model = YOLO("yolov8x-seg.pt")   # downloads ~140 MB on first run, cached after
    log.info(f"Fallback model loaded — {len(fallback_model.names)} classes")
except Exception as e:
    fallback_model = None
    log.warning(f"Fallback model failed to load: {e} — will only use custom model")

# ----------------------------------------------------------------------
# Arabic font
# ----------------------------------------------------------------------
try:
    FONT = ImageFont.truetype(FONT_PATH, 48)
except Exception:
    log.warning(f"Arabic font not found at {FONT_PATH}, falling back to default")
    FONT = ImageFont.load_default()

# ----------------------------------------------------------------------
# Translation (deep_translator — kept as-is)
# ----------------------------------------------------------------------
translator = GoogleTranslator(source="en", target="ar")

_DIACRITICS = set("ًٌٍَُِّْٰٱؐؑؒؓؔؕؖؗ")


@lru_cache(maxsize=512)
def translate_to_arabic(en_name: str) -> str:
    """English class name -> Arabic via deep_translator. Cached per class."""
    clean = en_name.replace("_", " ").strip()
    try:
        result = translator.translate(clean)
        return result if result else clean
    except Exception as e:
        log.warning(f"Translation failed for '{clean}': {e}")
        return clean


# ----------------------------------------------------------------------
# TTS — edge-tts (Microsoft Neural Arabic)
# ----------------------------------------------------------------------
async def _edge_tts_bytes(text: str, voice: str = EDGE_TTS_VOICE) -> Optional[bytes]:
    """
    Synthesise text using edge-tts and return raw MP3 bytes.
    edge-tts writes to a temp file; we read it back and delete it.
    """
    if not text or not text.strip():
        return None
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_path = tmp.name

        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(tmp_path)

        with open(tmp_path, "rb") as f:
            audio = f.read()

        os.unlink(tmp_path)
        return audio if audio else None
    except Exception as e:
        log.warning(f"edge-tts failed for '{text}': {e}")
        return None


def synth_audio_bytes(text: str) -> Optional[bytes]:
    """Sync wrapper around the async edge-tts call."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Inside an async context (FastAPI) — run in a thread executor
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, _edge_tts_bytes(text))
                return future.result(timeout=20)
        else:
            return loop.run_until_complete(_edge_tts_bytes(text))
    except Exception as e:
        log.warning(f"synth_audio_bytes failed for '{text}': {e}")
        return None


def bytes_to_data_uri(mp3_bytes: Optional[bytes]) -> Optional[str]:
    """Wrap raw MP3 bytes into a data: URI Streamlit can play."""
    if not mp3_bytes:
        return None
    encoded = base64.b64encode(mp3_bytes).decode("ascii")
    return f"data:audio/mp3;base64,{encoded}"


# ----------------------------------------------------------------------
# Image helpers
# ----------------------------------------------------------------------
def spell_word(word: str) -> list:
    """Break an Arabic word into its individual letters, skipping spaces and diacritics."""
    return [ch for ch in word if ch.strip() and ch not in _DIACRITICS]


def shape_arabic(text: str) -> str:
    """Reshape Arabic text so PIL draws the letters correctly connected and right-to-left."""
    return get_display(arabic_reshaper.reshape(text))


def annotate_image(results, image: Image.Image, ar_label: str, coverage_pct: float) -> Image.Image:
    """Draw YOLO's boxes/masks, then burn the Arabic label in the top-right corner."""
    annotated = Image.fromarray(results.plot()[:, :, ::-1])   # BGR -> RGB
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
    return f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode('ascii')}"


def run_model_and_pick_best(model, img: Image.Image):
    """
    Run a YOLO segmentation model and return:
      (results, label_en, top_conf, coverage_pct, class_stats)
    Returns None if no masks found.
    """
    results = model.predict(img, device="cpu", verbose=False, imgsz=640)[0]
    if results.masks is None or len(results.masks) == 0:
        return None

    masks   = results.masks.data.cpu().numpy()
    cls_ids = results.boxes.cls.cpu().numpy().astype(int)
    confs   = results.boxes.conf.cpu().numpy()

    class_stats = {}
    for m, c, conf in zip(masks, cls_ids, confs):
        s = class_stats.setdefault(int(c), {"area": 0.0, "conf": 0.0})
        s["area"] += float(m.sum())
        if conf > s["conf"]:
            s["conf"] = float(conf)

    top_cls      = max(class_stats, key=lambda k: class_stats[k]["area"])
    label_en     = model.names[top_cls]
    top_conf     = class_stats[top_cls]["conf"]
    coverage_pct = 100.0 * class_stats[top_cls]["area"] / (img.width * img.height)

    return results, label_en, top_conf, coverage_pct


# ----------------------------------------------------------------------
# FastAPI app
# ----------------------------------------------------------------------
app = FastAPI(title="Smart Explorer API", version="4.0.0")
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
    audio_combined: Optional[str]
    model_used: str          # "custom" | "fallback"
    tts_voice: str           # which edge-tts voice was used


# ----------------------------------------------------------------------
# Endpoints
# ----------------------------------------------------------------------
@app.get("/")
def root():
    return {
        "status": "ok",
        "service": "Smart Explorer API",
        "version": "4.0.0",
        "custom_model_classes": len(custom_model.names),
        "fallback_model_classes": len(fallback_model.names) if fallback_model else 0,
        "tts_engine": "edge-tts",
        "tts_voice": EDGE_TTS_VOICE,
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
        "custom_model_loaded": custom_model is not None,
        "fallback_model_loaded": fallback_model is not None,
        "custom_num_classes": len(custom_model.names) if custom_model else 0,
        "fallback_num_classes": len(fallback_model.names) if fallback_model else 0,
        "tts_engine": "edge-tts",
        "tts_voice": EDGE_TTS_VOICE,
    }


@app.post("/segment", response_model=SegmentResponse)
async def segment(file: UploadFile = File(...)):
    # ---- Read + validate image -------------------------------------------
    try:
        raw = await file.read()
        img = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid image: {e}")

    # ---- Try custom model first ------------------------------------------
    custom_result = run_model_and_pick_best(custom_model, img)
    model_used = "custom"
    final_result = custom_result

    # ---- Fallback: use YOLOv8x-seg if custom confidence is too low -------
    if (
        fallback_model is not None
        and (
            custom_result is None
            or custom_result[2] < FALLBACK_CONF_THRESHOLD   # top_conf < threshold
        )
    ):
        log.info(
            f"Custom model conf={custom_result[2]:.2f if custom_result else 0:.2f} < {FALLBACK_CONF_THRESHOLD} "
            f"— trying fallback YOLOv8x-seg"
        )
        fallback_result = run_model_and_pick_best(fallback_model, img)
        if fallback_result is not None:
            # Use fallback only if it found something
            final_result = fallback_result
            model_used = "fallback"
            log.info(f"Fallback detected: {fallback_result[1]} (conf={fallback_result[2]:.2f})")

    # ---- Nothing found at all -------------------------------------------
    if final_result is None:
        raise HTTPException(
            status_code=422,
            detail="لم أتمكن من التعرف على أي شيء. حاول مع صورة أوضح!",
        )

    results, label_en, top_conf, coverage_pct = final_result

    # ---- Translate (deep_translator — unchanged) -------------------------
    label_ar = translate_to_arabic(label_en)
    letters  = spell_word(label_ar)

    # ---- Annotate image --------------------------------------------------
    annotated     = annotate_image(results, img, label_ar, coverage_pct)
    annotated_b64 = image_to_b64(annotated)

    # ---- Generate audio via edge-tts ------------------------------------
    # Run all TTS calls concurrently for speed
    async def _all_audio():
        word_task    = asyncio.create_task(_edge_tts_bytes(label_ar))
        letter_tasks = [asyncio.create_task(_edge_tts_bytes(ch)) for ch in letters]
        word_bytes   = await word_task
        letter_bytes = await asyncio.gather(*letter_tasks)
        return word_bytes, list(letter_bytes)

    word_bytes, letter_bytes = await _all_audio()

    audio_word    = bytes_to_data_uri(word_bytes)
    audio_letters = [
        {"letter": ch, "audio": bytes_to_data_uri(b)}
        for ch, b in zip(letters, letter_bytes)
    ]

    # Combined: word → letters → word
    combined_parts = []
    if word_bytes:
        combined_parts.append(word_bytes)
    for b in letter_bytes:
        if b:
            combined_parts.append(b)
    if word_bytes:
        combined_parts.append(word_bytes)
    audio_combined = bytes_to_data_uri(b"".join(combined_parts)) if combined_parts else None

    log.info(
        f"✅ [{model_used}] {label_en} -> {label_ar} | conf={top_conf:.2f} | "
        f"coverage={coverage_pct:.1f}% | letters={len(letters)} | voice={EDGE_TTS_VOICE}"
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
        audio_combined=audio_combined,
        model_used=model_used,
        tts_voice=EDGE_TTS_VOICE,
    )