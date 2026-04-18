"""
Smart Explorer backend v5.0 — adds Google Cloud Vision + Imagga as model options.

Models available:
  - custom        : the trained YOLO-seg kids model (best.pt)
  - fallback      : YOLOv8x-seg pretrained on COCO (80 classes)
  - google_vision : Google Cloud Vision API (LABEL_DETECTION, thousands of classes)
  - imagga        : Imagga /v2/tags (3,000+ tags)
  - auto          : custom first, falls back to yolov8x-seg if confidence low

Local YOLO models return pixel-level segmentation masks.
Google Vision and Imagga are classification APIs — they only return labels +
confidences. For those we show the original image with a clean label banner
burned in the top-right corner instead of mask overlays.

Credentials (set as environment variables before running):
  GOOGLE_VISION_API_KEY     — Google Cloud Vision API key (create in GCP console)
  IMAGGA_API_KEY            — Imagga API key
  IMAGGA_API_SECRET         — Imagga API secret

If a credential is missing, the corresponding model is reported as
unavailable=False in /models and returns 503 if forced via /segment?model=...
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
import requests
from bidi.algorithm import get_display
from deep_translator import GoogleTranslator
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel
from ultralytics import YOLO

# ----------------------------------------------------------------------
# Setup
# ----------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("smart-explorer")

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "best.pt")
FONT_PATH  = os.path.join(BASE_DIR, "NotoNaskhArabic-Regular.ttf")

FALLBACK_CONF_THRESHOLD = 0.45
EDGE_TTS_VOICE          = "ar-SA-ZariyahNeural"

# External API credentials
GOOGLE_VISION_API_KEY = os.getenv("GOOGLE_VISION_API_KEY", "").strip()
IMAGGA_API_KEY        = os.getenv("IMAGGA_API_KEY", "").strip()
IMAGGA_API_SECRET     = os.getenv("IMAGGA_API_SECRET", "").strip()

GOOGLE_VISION_ENABLED = bool(GOOGLE_VISION_API_KEY)
IMAGGA_ENABLED        = bool(IMAGGA_API_KEY and IMAGGA_API_SECRET)

if GOOGLE_VISION_ENABLED:
    log.info("Google Cloud Vision: API key configured")
else:
    log.info("Google Cloud Vision: no API key (set GOOGLE_VISION_API_KEY to enable)")

if IMAGGA_ENABLED:
    log.info("Imagga: credentials configured")
else:
    log.info("Imagga: no credentials (set IMAGGA_API_KEY and IMAGGA_API_SECRET to enable)")

# ----------------------------------------------------------------------
# Load local YOLO models
# ----------------------------------------------------------------------
log.info(f"Loading custom model from {MODEL_PATH}")
custom_model = YOLO(MODEL_PATH)
log.info(f"Custom model loaded — {len(custom_model.names)} classes")

log.info("Loading fallback model YOLOv8x-seg (COCO 80 classes)")
try:
    fallback_model = YOLO("yolov8x-seg.pt")
    log.info(f"Fallback model loaded — {len(fallback_model.names)} classes")
except Exception as e:
    fallback_model = None
    log.warning(f"Fallback model failed to load: {e}")

# ----------------------------------------------------------------------
# Arabic font
# ----------------------------------------------------------------------
try:
    FONT = ImageFont.truetype(FONT_PATH, 48)
except Exception:
    log.warning(f"Arabic font not found at {FONT_PATH}, falling back to default")
    FONT = ImageFont.load_default()

# ----------------------------------------------------------------------
# Translation
# ----------------------------------------------------------------------
translator = GoogleTranslator(source="en", target="ar")
_DIACRITICS = set("ًٌٍَُِّْٰٱؐؑؒؓؔؕؖؗ")


@lru_cache(maxsize=1024)
def translate_to_arabic(en_name: str) -> str:
    clean = en_name.replace("_", " ").strip()
    try:
        result = translator.translate(clean)
        return result if result else clean
    except Exception as e:
        log.warning(f"Translation failed for '{clean}': {e}")
        return clean


# ----------------------------------------------------------------------
# TTS — edge-tts, called directly from async endpoint
# ----------------------------------------------------------------------
async def edge_tts_bytes(text: str, voice: str = EDGE_TTS_VOICE) -> Optional[bytes]:
    if not text or not text.strip():
        return None
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_path = tmp.name
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(tmp_path)
        with open(tmp_path, "rb") as f:
            audio = f.read()
        return audio if audio else None
    except Exception as e:
        log.warning(f"edge-tts failed for '{text}': {type(e).__name__}: {e}")
        return None
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


def bytes_to_data_uri(mp3_bytes: Optional[bytes]) -> Optional[str]:
    if not mp3_bytes:
        return None
    return f"data:audio/mp3;base64,{base64.b64encode(mp3_bytes).decode('ascii')}"


# ----------------------------------------------------------------------
# Image helpers
# ----------------------------------------------------------------------
def spell_word(word: str) -> list:
    return [ch for ch in word if ch.strip() and ch not in _DIACRITICS]


def shape_arabic(text: str) -> str:
    return get_display(arabic_reshaper.reshape(text))


def annotate_yolo_image(results, ar_label: str, coverage_pct: float) -> Image.Image:
    """YOLO-seg: render masks + label banner."""
    annotated  = Image.fromarray(results.plot()[:, :, ::-1])
    label_text = shape_arabic(f"{ar_label} ({coverage_pct:.1f}%)")
    _burn_label(annotated, label_text)
    return annotated


def annotate_classification_image(img: Image.Image, ar_label: str, confidence: float) -> Image.Image:
    """Google Vision / Imagga: no masks — just the original image with a clean label."""
    annotated  = img.copy()
    label_text = shape_arabic(f"{ar_label} ({confidence*100:.1f}%)")
    _burn_label(annotated, label_text)
    return annotated


def _burn_label(img: Image.Image, label_text: str) -> None:
    draw = ImageDraw.Draw(img, "RGBA")
    bbox = draw.textbbox((0, 0), label_text, font=FONT)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x, y = img.width - w - 20, 20
    draw.rectangle([x - 10, y - 10, x + w + 10, y + h + 10], fill=(0, 0, 0, 180))
    draw.text((x, y), label_text, font=FONT, fill=(255, 255, 255))


def image_to_b64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode('ascii')}"


# ----------------------------------------------------------------------
# Detection runners
# ----------------------------------------------------------------------
def run_yolo(model_obj, img: Image.Image):
    """Returns (results, label_en, top_conf, coverage_pct) or None."""
    results = model_obj.predict(img, device="cpu", verbose=False, imgsz=640)[0]
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
    label_en     = model_obj.names[top_cls]
    top_conf     = class_stats[top_cls]["conf"]
    coverage_pct = 100.0 * class_stats[top_cls]["area"] / (img.width * img.height)
    return results, label_en, top_conf, coverage_pct


def run_google_vision(img: Image.Image):
    """Returns (label_en, confidence) or None. Raises HTTPException on API / connection errors."""
    if not GOOGLE_VISION_ENABLED:
        raise HTTPException(status_code=503, detail="Google Vision API غير مفعّل على الخادم.")

    buffer = io.BytesIO()
    img.save(buffer, format="JPEG")
    b64_string = base64.b64encode(buffer.getvalue()).decode("utf-8")

    payload = {
        "requests": [{
            "image": {"content": b64_string},
            "features": [{"type": "LABEL_DETECTION", "maxResults": 5}],
        }]
    }
    url = f"https://vision.googleapis.com/v1/images:annotate?key={GOOGLE_VISION_API_KEY}"

    try:
        r = requests.post(url, json=payload, timeout=20)
        if r.status_code != 200:
            raise HTTPException(status_code=r.status_code, detail=f"Google Vision Error: {r.text}")

        data = r.json()
        responses = data.get("responses", [])
        if not responses or "labelAnnotations" not in responses[0]:
            return None

        top = responses[0]["labelAnnotations"][0]
        return top.get("description", ""), float(top.get("score", 0.0))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"خطأ في الاتصال بـ Google Vision: {str(e)}")


def run_imagga(img_bytes: bytes):
    """Returns (label_en, confidence_0_to_1) or None."""
    if not IMAGGA_ENABLED:
        raise HTTPException(status_code=503, detail="Imagga API غير مفعّل على الخادم.")

    try:
        r = requests.post(
            "https://api.imagga.com/v2/tags",
            auth=(IMAGGA_API_KEY, IMAGGA_API_SECRET),
            files={"image": ("capture.jpg", img_bytes, "image/jpeg")},
            timeout=20,
        )
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Imagga request failed: {e}")

    if r.status_code == 401:
        raise HTTPException(status_code=502, detail="Imagga: المفتاح غير صالح.")
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Imagga error {r.status_code}: {r.text[:200]}")

    try:
        tags = r.json().get("result", {}).get("tags", [])
    except Exception:
        return None

    if not tags:
        return None

    top = tags[0]
    tag_obj    = top.get("tag", {})
    label_en   = tag_obj.get("en") if isinstance(tag_obj, dict) else str(tag_obj)
    # Imagga returns confidence as 0–100 — normalise to 0–1 to match YOLO/Google
    confidence = float(top.get("confidence", 0.0)) / 100.0
    return label_en, confidence


# ----------------------------------------------------------------------
# FastAPI app
# ----------------------------------------------------------------------
app = FastAPI(title="Smart Explorer API", version="5.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    model_used: str
    tts_voice: str


# ----------------------------------------------------------------------
# Endpoints
# ----------------------------------------------------------------------
@app.get("/")
def root():
    return {
        "status": "ok",
        "service": "Smart Explorer API",
        "version": "5.0.0",
        "models": {
            "custom":        {"available": True, "classes": len(custom_model.names)},
            "fallback":      {"available": fallback_model is not None,
                              "classes": len(fallback_model.names) if fallback_model else 0},
            "google_vision": {"available": GOOGLE_VISION_ENABLED, "classes": "thousands"},
            "imagga":        {"available": IMAGGA_ENABLED, "classes": "3000+"},
        },
        "tts_voice": EDGE_TTS_VOICE,
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "custom_model_loaded":   custom_model is not None,
        "fallback_model_loaded": fallback_model is not None,
        "google_vision_enabled": GOOGLE_VISION_ENABLED,
        "imagga_enabled":        IMAGGA_ENABLED,
        "tts_engine":            "edge-tts",
        "tts_voice":             EDGE_TTS_VOICE,
    }


@app.get("/models")
def list_models():
    """List models the Streamlit UI can offer."""
    return {
        "models": [
            {
                "id": "auto",
                "name_ar": "تلقائي",
                "name_en": "Auto",
                "emoji": "✨",
                "num_classes_label": f"{len(custom_model.names)} + 80",
                "kind": "hybrid",
                "available": True,
                "description_ar": "يجرب نموذج الأطفال أولاً، ثم الاحتياطي إن لزم الأمر.",
            },
            {
                "id": "custom",
                "name_ar": "نموذج الأطفال",
                "name_en": "Kids model",
                "emoji": "🎯",
                "num_classes_label": f"{len(custom_model.names)}",
                "kind": "local-yolo",
                "available": custom_model is not None,
                "description_ar": "مدرّب خصيصاً على الأشياء المألوفة للأطفال — الأدق لمحتوى التعلّم.",
            },
            {
                "id": "fallback",
                "name_ar": "YOLO الشامل",
                "name_en": "YOLOv8x-seg (COCO)",
                "emoji": "🔄",
                "num_classes_label": f"{len(fallback_model.names) if fallback_model else 0}",
                "kind": "local-yolo",
                "available": fallback_model is not None,
                "description_ar": "نموذج عام يغطي 80 فئة من الأشياء اليومية.",
            },
            {
                "id": "google_vision",
                "name_ar": "Google Vision",
                "name_en": "Google Cloud Vision",
                "emoji": "🌐",
                "num_classes_label": "آلاف",
                "kind": "cloud",
                "available": GOOGLE_VISION_ENABLED,
                "description_ar": "سحابي — يغطي آلاف الفئات ولكن بدون تحديد المنطقة.",
            },
            {
                "id": "imagga",
                "name_ar": "Imagga",
                "name_en": "Imagga",
                "emoji": "🏷️",
                "num_classes_label": "3000+",
                "kind": "cloud",
                "available": IMAGGA_ENABLED,
                "description_ar": "سحابي — أكثر من 3000 وسم للصور بدون تحديد المنطقة.",
            },
        ]
    }


@app.post("/segment", response_model=SegmentResponse)
async def segment(
    file: UploadFile = File(...),
    model: str = Query("auto", description="auto | custom | fallback | google_vision | imagga"),
):
    # ---- Read + validate image -------------------------------------------
    try:
        raw = await file.read()
        img = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid image: {e}")

    model = (model or "auto").lower().strip()
    if model not in ("auto", "custom", "fallback", "google_vision", "imagga"):
        model = "auto"

    # Tracked results across branches
    model_used     = ""
    label_en       = ""
    top_conf       = 0.0
    coverage_pct   = 0.0
    annotated_img  = None

    # ---- Local YOLO branches ---------------------------------------------
    if model == "custom":
        r = run_yolo(custom_model, img)
        if r is None:
            raise HTTPException(status_code=422,
                                detail="لم أتمكن من التعرف على أي شيء. حاول مع صورة أوضح!")
        results, label_en, top_conf, coverage_pct = r
        model_used    = "custom"

    elif model == "fallback":
        if fallback_model is None:
            raise HTTPException(status_code=503, detail="YOLO الشامل غير متوفر على الخادم.")
        r = run_yolo(fallback_model, img)
        if r is None:
            raise HTTPException(status_code=422,
                                detail="لم أتمكن من التعرف على أي شيء. حاول مع صورة أوضح!")
        results, label_en, top_conf, coverage_pct = r
        model_used    = "fallback"

    elif model == "auto":
        r_custom = run_yolo(custom_model, img)
        chosen   = r_custom
        chosen_tag = "custom"

        needs_fb = (
            fallback_model is not None
            and (r_custom is None or r_custom[2] < FALLBACK_CONF_THRESHOLD)
        )
        if needs_fb:
            low = r_custom[2] if r_custom else 0.0
            log.info(f"auto: custom conf={low:.2f} < {FALLBACK_CONF_THRESHOLD} — trying fallback")
            r_fb = run_yolo(fallback_model, img)
            if r_fb is not None and (r_custom is None or r_fb[2] > r_custom[2]):
                chosen, chosen_tag = r_fb, "fallback"

        if chosen is None:
            raise HTTPException(status_code=422,
                                detail="لم أتمكن من التعرف على أي شيء. حاول مع صورة أوضح!")
        results, label_en, top_conf, coverage_pct = chosen
        model_used = chosen_tag

    # ---- Cloud API branches (classification only — no masks) -------------
    elif model == "google_vision":
        r = run_google_vision(img)
        if r is None:
            raise HTTPException(status_code=422,
                                detail="Google Vision لم تتعرف على أي شيء في الصورة.")
        label_en, top_conf = r
        coverage_pct       = 0.0
        model_used         = "google_vision"

    elif model == "imagga":
        r = run_imagga(raw)
        if r is None:
            raise HTTPException(status_code=422,
                                detail="Imagga لم تتعرف على أي شيء في الصورة.")
        label_en, top_conf = r
        coverage_pct       = 0.0
        model_used         = "imagga"

    # ---- Translate -------------------------------------------------------
    label_ar = translate_to_arabic(label_en)
    letters  = spell_word(label_ar)

    # ---- Annotate image --------------------------------------------------
    if model_used in ("custom", "fallback"):
        annotated_img = annotate_yolo_image(results, label_ar, coverage_pct)  # noqa: F821
    else:
        annotated_img = annotate_classification_image(img, label_ar, top_conf)
    annotated_b64 = image_to_b64(annotated_img)

    # ---- Generate all audio in parallel ---------------------------------
    word_task    = asyncio.create_task(edge_tts_bytes(label_ar))
    letter_tasks = [asyncio.create_task(edge_tts_bytes(ch)) for ch in letters]
    word_bytes   = await word_task
    letter_bytes = await asyncio.gather(*letter_tasks) if letter_tasks else []

    got_letters = sum(1 for b in letter_bytes if b)
    log.info(f"TTS: word={'✓' if word_bytes else '✗'}, letters={got_letters}/{len(letters)}")

    audio_word    = bytes_to_data_uri(word_bytes)
    audio_letters = [
        {"letter": ch, "audio": bytes_to_data_uri(b)}
        for ch, b in zip(letters, letter_bytes)
    ]

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
        f"✅ [{model_used}] {label_en} -> {label_ar} | "
        f"conf={top_conf:.2f} | coverage={coverage_pct:.1f}% | letters={len(letters)}"
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