"""
Smart Explorer backend v5.2 — Custom YOLO + Imagga cloud.

Models available:
  - custom : the trained YOLO-seg kids model (best.pt)
  - imagga : Imagga /v2/tags (3,000+ tags)

Local YOLO returns pixel-level segmentation masks.
Imagga is a classification API — labels + confidences only, no masks.
For Imagga we show the original image with a clean label banner burned in
the top-right corner instead of mask overlays.

Credentials (set as environment variables before running):
  IMAGGA_API_KEY    — Imagga API key
  IMAGGA_API_SECRET — Imagga API secret

If a credential is missing, Imagga is reported as unavailable in /models
and returns 503 if forced via /segment?model=imagga.
"""

import asyncio
import base64
import io
import logging
import os
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

EDGE_TTS_VOICE = "ar-SA-ZariyahNeural"

# External API credentials
IMAGGA_API_KEY    = os.getenv("IMAGGA_API_KEY", "").strip()
IMAGGA_API_SECRET = os.getenv("IMAGGA_API_SECRET", "").strip()
IMAGGA_ENABLED    = bool(IMAGGA_API_KEY and IMAGGA_API_SECRET)

if IMAGGA_ENABLED:
    log.info("Imagga: credentials configured")
else:
    log.info("Imagga: no credentials (set IMAGGA_API_KEY and IMAGGA_API_SECRET to enable)")

# ----------------------------------------------------------------------
# Load local YOLO model
# ----------------------------------------------------------------------
log.info(f"Loading custom model from {MODEL_PATH}")
custom_model = YOLO(MODEL_PATH)
log.info(f"Custom model loaded — {len(custom_model.names)} classes")

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
# TTS — edge-tts (primary) with gTTS fallback over plain HTTPS
# ----------------------------------------------------------------------
#
# Why a fallback?
#   edge-tts streams audio over a WebSocket to Microsoft's servers.
#   Railway (and many cloud hosts) frequently block or throttle those
#   WebSocket connections, which surfaces as `NoAudioReceived` errors and
#   the dreaded "لم يتوفر صوت لهذه الكلمة" message on the client.
#   gTTS uses plain HTTPS to translate.google.com and works reliably on
#   any host that can make outbound HTTPS calls.

# Arabic single-letter → spoken letter name.
# TTS engines pronounce isolated letters like "ب" poorly or silently
# because they treat them as fragments, not words. Feeding the full
# letter name ("باء", "ميم", …) produces the pronunciation kids expect.
ARABIC_LETTER_NAMES = {
    "ا": "ألف",  "أ": "ألف",  "إ": "ألف",  "آ": "ألف",  "ء": "همزة",
    "ب": "باء",  "ت": "تاء",  "ث": "ثاء",
    "ج": "جيم",  "ح": "حاء",  "خ": "خاء",
    "د": "دال",  "ذ": "ذال",
    "ر": "راء",  "ز": "زاي",
    "س": "سين",  "ش": "شين",
    "ص": "صاد",  "ض": "ضاد",
    "ط": "طاء",  "ظ": "ظاء",
    "ع": "عين",  "غ": "غين",
    "ف": "فاء",  "ق": "قاف",
    "ك": "كاف",  "ل": "لام",
    "م": "ميم",  "ن": "نون",
    "ه": "هاء",  "ة": "تاء مربوطة",
    "و": "واو",  "ؤ": "واو",
    "ي": "ياء",  "ى": "ألف مقصورة",  "ئ": "ياء",
}


def _spoken_form(text: str) -> str:
    """If the input is a single Arabic letter, expand it to its letter name so TTS
    pronounces it the way a teacher would read it aloud."""
    stripped = text.strip()
    if len(stripped) == 1 and stripped in ARABIC_LETTER_NAMES:
        return ARABIC_LETTER_NAMES[stripped]
    return text


async def _edge_tts_bytes(
    text: str,
    voice: str = EDGE_TTS_VOICE,
    *,
    retries: int = 2,
) -> Optional[bytes]:
    """
    Stream TTS audio from edge-tts directly into memory. No tempfiles.
    Retries up to `retries` times on transient failures.
    Returns None if every attempt fails — caller should fall back to gTTS.
    """
    if not text or not text.strip():
        return None

    last_err: Optional[BaseException] = None
    for attempt in range(retries + 1):
        try:
            communicate = edge_tts.Communicate(text, voice)
            chunks = bytearray()
            async for chunk in communicate.stream():
                if chunk.get("type") == "audio" and chunk.get("data"):
                    chunks.extend(chunk["data"])
            if chunks:
                return bytes(chunks)
            last_err = RuntimeError("edge-tts returned no audio data")
        except Exception as e:  # noqa: BLE001 — edge-tts raises varied errors
            last_err = e
            log.warning(
                f"edge-tts attempt {attempt + 1}/{retries + 1} failed for '{text}': "
                f"{type(e).__name__}: {e}"
            )
        if attempt < retries:
            await asyncio.sleep(0.4 * (attempt + 1))

    log.warning(f"edge-tts giving up on '{text}': {last_err}")
    return None


# Google Translate's unofficial TTS endpoint — also used by the `gTTS`
# package. Plain HTTPS GET, returns an MP3 body. Works on any host.
_GTTS_URL = "https://translate.google.com/translate_tts"
_GTTS_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    ),
    "Referer": "https://translate.google.com/",
}


def _gtts_bytes_sync(text: str, lang: str = "ar") -> Optional[bytes]:
    """Blocking HTTP fetch from translate.google.com. Called via to_thread."""
    try:
        params = {
            "ie": "UTF-8",
            "q": text,
            "tl": lang,
            "client": "tw-ob",
            "ttsspeed": "1.0",
        }
        r = requests.get(_GTTS_URL, params=params, headers=_GTTS_HEADERS, timeout=15)
        if r.status_code == 200 and r.content:
            return r.content
        log.warning(f"gTTS HTTP {r.status_code} for '{text}'")
    except Exception as e:  # noqa: BLE001
        log.warning(f"gTTS failed for '{text}': {type(e).__name__}: {e}")
    return None


async def _gtts_bytes(text: str, lang: str = "ar") -> Optional[bytes]:
    """Async wrapper so we don't block the event loop on the HTTP call."""
    return await asyncio.to_thread(_gtts_bytes_sync, text, lang)


async def tts_bytes(text: str, voice: str = EDGE_TTS_VOICE) -> Optional[bytes]:
    """
    Unified TTS entrypoint: try edge-tts first, fall back to gTTS over HTTPS.
    Expands single Arabic letters to their letter names for correct pronunciation.
    Returns MP3 bytes, or None only if BOTH providers fail.
    """
    if not text or not text.strip():
        return None

    spoken = _spoken_form(text)

    # Primary: edge-tts (neural voice, better quality)
    audio = await _edge_tts_bytes(spoken, voice=voice)
    if audio:
        return audio

    # Fallback: gTTS (plain HTTPS, works when WebSocket is blocked)
    log.info(f"Falling back to gTTS for '{text}'")
    return await _gtts_bytes(spoken, lang="ar")


# Kept as a thin alias so the rest of the code doesn't have to change.
edge_tts_bytes = tts_bytes


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
    """Imagga: no masks — just the original image with a clean label."""
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
app = FastAPI(title="Smart Explorer API", version="5.2.0")
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
        "version": "5.2.0",
        "models": {
            "custom": {"available": True, "classes": len(custom_model.names)},
            "imagga": {"available": IMAGGA_ENABLED, "classes": "3000+"},
        },
        "tts_voice": EDGE_TTS_VOICE,
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "custom_model_loaded": custom_model is not None,
        "imagga_enabled":      IMAGGA_ENABLED,
        "tts_engine":          "edge-tts + gTTS fallback",
        "tts_voice":           EDGE_TTS_VOICE,
    }


@app.get("/models")
def list_models():
    """List models the Streamlit UI can offer."""
    return {
        "models": [
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
    model: str = Query("custom", description="custom | imagga"),
):
    # ---- Read + validate image -------------------------------------------
    try:
        raw = await file.read()
        img = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid image: {e}")

    model = (model or "custom").lower().strip()
    if model not in ("custom", "imagga"):
        model = "custom"

    # Tracked results across branches
    model_used    = ""
    label_en      = ""
    top_conf      = 0.0
    coverage_pct  = 0.0
    results       = None

    # ---- Local YOLO branch -----------------------------------------------
    if model == "custom":
        r = run_yolo(custom_model, img)
        if r is None:
            raise HTTPException(status_code=422,
                                detail="لم أتمكن من التعرف على أي شيء. حاول مع صورة أوضح!")
        results, label_en, top_conf, coverage_pct = r
        model_used = "custom"

    # ---- Cloud API branch (classification only — no masks) ---------------
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
    if model_used == "custom":
        annotated_img = annotate_yolo_image(results, label_ar, coverage_pct)
    else:
        annotated_img = annotate_classification_image(img, label_ar, top_conf)
    annotated_b64 = image_to_b64(annotated_img)

    # ---- Generate all audio (word in parallel, letters in small batches) -
    # Firing 10+ concurrent edge-tts requests often trips rate limits or the
    # "NoAudioReceived" failure mode. We batch letters 3-at-a-time while the
    # word TTS runs in parallel — fast enough that the loader doesn't drag.
    word_task = asyncio.create_task(tts_bytes(label_ar))

    LETTER_BATCH_SIZE = 3
    letter_bytes: list = []
    for i in range(0, len(letters), LETTER_BATCH_SIZE):
        batch = letters[i:i + LETTER_BATCH_SIZE]
        batch_results = await asyncio.gather(*(tts_bytes(ch) for ch in batch))
        letter_bytes.extend(batch_results)

    word_bytes = await word_task

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