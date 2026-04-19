"""
Smart Explorer — Streamlit frontend (v7.0)

Changes in this version:
  1. Page 1: kids.png background (fixed, layered), elements centered in 100vh,
             no scrolling, button text "أستكشف!" pinned full-width at bottom.
  2. Page 2: clicking a character immediately navigates to camera (no ابدأ التعلّم button).
             Removed لازم اختيار شخصية / تم اختيار phrases.
  3. Page 3: 2 models only (custom default). No COCO/yolov8x-seg references.
             No top-right emoji. Gendered ضع / ضعي instruction.
  4. Page 4 → Page 6 directly (no intermediate "learn this pic" step).
  5. Page 6: English label burned over segmentation image, Arabic word + spelling
             + meaning in cards, TTS autoplays immediately on load.
"""

import streamlit as st
from PIL import Image, ImageDraw, ImageFont
import os
import time
import base64
import io
import requests

st.set_page_config(
    page_title="المستكشف الذكي",
    page_icon="🌟",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# =============================================================================
# Assets
# =============================================================================
girl_path = "girl.png"
boy_path  = "boy.png"
# Optional: a font for the English label we burn client-side. Falls back to PIL default.
ENGLISH_FONT_CANDIDATES = [
    "DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "arial.ttf",
]

# =============================================================================
# Backend config
# =============================================================================
API_URL = "https://interactive-educational-application-production.up.railway.app"

# The 2 models we support in this build.
# `custom` is the default and is always selected at startup.
ALLOWED_MODELS = {"custom", "imagga"}
DEFAULT_MODEL  = "custom"

# =============================================================================
# Session state
# =============================================================================
_DEFAULTS = {
    "selected_character": "",          # "بنت" | "ولد"
    "current_page":       "welcome",    # welcome | characters | camera | results
    "captured_image":     None,
    "annotated_image":    None,         # bytes returned by backend (has Arabic burned in for YOLO)
    "predicted_label":    "",           # Arabic word
    "predicted_label_en": "",           # English label (used for masking image label)
    "predicted_conf":     "",
    "predicted_coverage": 0.0,
    "predicted_spelling": [],
    "audio_word":         None,
    "audio_letters":      [],
    "audio_combined":     None,
    "pending_capture":    None,
    "model_used":         "",
    "tts_voice":          "",
    "selected_model":     DEFAULT_MODEL,
    "audio_autoplayed":   False,        # so we only autoplay once per result
    "_results_page_init": False,        # cleared on navigation away from results
}
for k, v in _DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# =============================================================================
# Helpers
# =============================================================================
def _decode_data_uri(data_uri: str) -> bytes:
    if not data_uri or "," not in data_uri:
        return b""
    try:
        return base64.b64decode(data_uri.split(",", 1)[1])
    except Exception:
        return b""


def _center_square_crop(image_bytes: bytes, guide_ratio: float = 0.62) -> bytes:
    try:
        img  = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        w, h = img.size
        side = int(min(w, h) * guide_ratio)
        left = (w - side) // 2
        top  = (h - side) // 2
        cropped = img.crop((left, top, left + side, top + side))
        buf = io.BytesIO()
        cropped.save(buf, format="JPEG", quality=92)
        return buf.getvalue()
    except Exception:
        return image_bytes


def _load_english_font(size: int = 36) -> ImageFont.FreeTypeFont:
    for candidate in ENGLISH_FONT_CANDIDATES:
        try:
            return ImageFont.truetype(candidate, size)
        except Exception:
            continue
    return ImageFont.load_default()


def overlay_english_label(annotated_bytes: bytes, english_label: str, confidence_pct: float) -> bytes:
    """
    Take the segmentation image the backend returned (which has an Arabic label
    burned in the top-right) and paint a fresh English label on top of it.
    Returns PNG bytes.
    """
    if not annotated_bytes or not english_label:
        return annotated_bytes

    try:
        img  = Image.open(io.BytesIO(annotated_bytes)).convert("RGB")
        draw = ImageDraw.Draw(img, "RGBA")
        font = _load_english_font(size=max(24, img.width // 18))

        text = f"{english_label}  {confidence_pct:.0f}%"
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

        # Cover the same top-right region the backend used, a bit larger to ensure
        # the Arabic label underneath is fully hidden.
        pad_x, pad_y = 16, 12
        box_w = tw + pad_x * 2
        box_h = th + pad_y * 2
        x = img.width - box_w - 16
        y = 16

        # Opaque dark background so Arabic underneath can't show through
        draw.rectangle([x, y, x + box_w, y + box_h], fill=(30, 27, 60, 245))
        # Subtle inner border
        draw.rectangle(
            [x + 2, y + 2, x + box_w - 2, y + box_h - 2],
            outline=(180, 170, 255, 200),
            width=2,
        )
        draw.text((x + pad_x, y + pad_y - 2), text, font=font, fill=(255, 255, 255))

        out = io.BytesIO()
        img.save(out, format="PNG", optimize=True)
        return out.getvalue()
    except Exception:
        return annotated_bytes


@st.cache_data(ttl=120, show_spinner=False)
def fetch_available_models() -> list:
    """Fetch models from backend and keep only the 3 we allow."""
    fallback = [
        {"id": "custom",        "name_ar": "نموذج الأطفال", "emoji": "🎯",
         "num_classes_label": "82",    "available": True,
         "description_ar": "مدرّب على الأشياء المألوفة للأطفال."},
        {"id": "imagga",        "name_ar": "Imagga",        "emoji": "🏷️",
         "num_classes_label": "3000+", "available": False,
         "description_ar": "نموذج سحابي يوفر أكثر من 3000 وسم للصور."},
    ]

    try:
        r = requests.get(f"{API_URL}/models", timeout=8)
        if r.status_code == 200:
            all_models = r.json().get("models", [])
            kept = [m for m in all_models if m.get("id") in ALLOWED_MODELS]
            if kept:
                # Preserve the custom → imagga order
                ordered = []
                for wanted in ("custom", "imagga"):
                    for m in kept:
                        if m["id"] == wanted:
                            ordered.append(m)
                            break
                return ordered
    except Exception:
        pass
    return fallback


def segment_image(image_source, model_id: str = DEFAULT_MODEL) -> dict:
    """POST image to /segment?model=<id>. Returns the parsed JSON."""
    try:
        if hasattr(image_source, "getvalue"):
            name = getattr(image_source, "name", "capture.jpg")
            data = image_source.getvalue()
            mime = getattr(image_source, "type", None) or "image/jpeg"
        elif isinstance(image_source, tuple) and len(image_source) == 3:
            name, data, mime = image_source
        elif isinstance(image_source, (bytes, bytearray)):
            name, data, mime = "capture.jpg", bytes(image_source), "image/jpeg"
        else:
            return {"error": "صيغة الصورة غير مدعومة."}

        files    = {"file": (name, data, mime)}
        params   = {"model": model_id or DEFAULT_MODEL}
        response = requests.post(
            f"{API_URL}/segment", files=files, params=params, timeout=120,
        )
        if response.status_code == 200:
            return response.json()
        try:
            detail = response.json().get("detail", response.text)
        except Exception:
            detail = response.text
        return {"error": f"API error {response.status_code}: {detail}"}
    except requests.exceptions.ConnectionError:
        return {"error": f"تعذر الاتصال بالخادم على {API_URL}."}
    except requests.exceptions.Timeout:
        return {"error": "النموذج استغرق وقتاً طويلاً — حاول مرة أخرى."}
    except Exception as e:
        return {"error": str(e)}


def apply_segmentation_result(source_bytes: bytes, result: dict) -> None:
    st.session_state.captured_image     = source_bytes
    st.session_state.annotated_image    = _decode_data_uri(result.get("annotated_image", ""))
    st.session_state.predicted_label    = result.get("label_ar", "غير معروف")
    st.session_state.predicted_label_en = result.get("label_en", "")
    conf_value = result.get("confidence", 0) or 0
    st.session_state.predicted_conf     = f"{int(conf_value * 100)}٪"
    st.session_state.predicted_coverage = result.get("coverage_percent", 0.0)
    st.session_state.predicted_spelling = result.get("spelling", [])
    st.session_state.audio_word         = result.get("audio_word")
    st.session_state.audio_letters      = result.get("audio_letters", [])
    st.session_state.audio_combined     = result.get("audio_combined")
    st.session_state.model_used         = result.get("model_used", "")
    st.session_state.tts_voice          = result.get("tts_voice", "")
    st.session_state.audio_autoplayed   = False


def reset_prediction():
    keep = {"selected_character", "selected_model"}
    for k, v in _DEFAULTS.items():
        if k not in keep and k != "current_page":
            st.session_state[k] = v
    st.session_state.pending_capture = None
    st.session_state["_results_page_init"] = False


def get_character_emoji() -> str:
    c = st.session_state.get("selected_character", "")
    return "👧" if c == "بنت" else ("🧒" if c == "ولد" else "🐥")


def gendered_place_hint() -> str:
    """Return the right verb form based on selected character."""
    if st.session_state.get("selected_character") == "بنت":
        return "ضعي الشيء داخل المربع المضيء ثم اضغطي على الزر البنفسجي"
    return "ضع الشيء داخل المربع المضيء ثم اضغط على الزر البنفسجي"


def go_to_page(page_name: str):
    with st.spinner("جاري الانتقال..."):
        time.sleep(0.25)
    if page_name != "results":
        st.session_state["_results_page_init"] = False
    st.session_state.current_page = page_name
    st.rerun()

# =============================================================================
# Shared CSS — mobile-first
# =============================================================================
SHARED_CSS = """
<style>
header, footer, #MainMenu { visibility: hidden; }

@import url('https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700;800;900&display=swap');

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  --bg:            #eeeaf8;
  --white:         #ffffff;
  --purple:        #7b6fd4;
  --purple-light:  #a89de8;
  --purple-dark:   #5a4fb0;
  --btn-blue:      #5b8de8;
  --btn-blue-dark: #3d6fd4;
  --btn-pink:      #e86fa0;
  --text-dark:     #2d2557;
  --text-mid:      #6b62a8;
  --card-shadow:   0 4px 24px rgba(91,71,180,0.13);
}

html, body,
[data-testid="stAppViewContainer"], [data-testid="stApp"] {
  background: var(--bg) !important;
  font-family: 'Tajawal', sans-serif !important;
  direction: rtl;
}

.main .block-container {
  max-width: 430px !important; width: 100% !important;
  margin: 0 auto !important;
  padding: 6px 14px 80px !important;
  animation: fadePage 0.45s ease;
}

@keyframes fadePage {
  from { opacity: 0; transform: translateY(10px); }
  to   { opacity: 1; transform: translateY(0); }
}

.blob-bg { position: fixed; inset: 0; pointer-events: none; z-index: -1; overflow: hidden; }
.blob { position: absolute; border-radius: 50%; filter: blur(55px); opacity: 0.30; }
.blob-1 { width: 240px; height: 240px; background: #c3b8f5; top: -8%;  left:  -4%; }
.blob-2 { width: 180px; height: 180px; background: #f5c8e8; bottom: 4%; right: -4%; }
.blob-3 { width: 140px; height: 140px; background: #b8f0e8; top: 40%; right: -2%; opacity: 0.18; }

/* ---------- Shared header ---------- */
.nq-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 8px 0 14px;
}
.nq-title { font-size: 20px; font-weight: 800; color: var(--text-dark); text-align: center; flex: 1; }
.nq-avatar {
  width: 40px; height: 40px; border-radius: 50%;
  background: linear-gradient(135deg,#c3b8f5,#f5c8e8);
  display: flex; align-items: center; justify-content: center;
  font-size: 22px; flex-shrink: 0;
}
.nq-header-spacer { width: 40px; height: 40px; flex-shrink: 0; }

.nq-instruction {
  background: var(--white); border-radius: 16px; padding: 10px 14px;
  display: flex; align-items: center; gap: 10px;
  box-shadow: 0 2px 10px rgba(123,111,212,0.08);
  margin-bottom: 12px; direction: rtl;
}
.nq-instruction-icon { font-size: 22px; flex-shrink: 0; }
.nq-instruction-text { font-size: 14px; font-weight: 500; color: var(--text-mid); line-height: 1.4; }

/* =================== PAGE 1 (welcome) =================== */
/* kids.png background — injected dynamically via Python */
.welcome-bg {
  position: fixed; inset: 0; z-index: 0;
  background-size: cover; background-position: center center;
  background-repeat: no-repeat; background-attachment: fixed;
}
.welcome-bg-overlay {
  position: fixed; inset: 0; z-index: 1;
  background: rgba(238,234,248,0.55);
}
.welcome-wrap {
  position: relative;
  z-index: 5;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  width: 100%;
  min-height: calc(100vh - 160px);
  padding: 24px 8px 20px;
  gap: 22px;
}
.welcome-title-c {
  font-size: 34px;
  font-weight: 900;
  color: #18264a;
  line-height: 1.2;
  margin-top: 8px;
}
.welcome-subtitle-c {
  font-size: 18px;
  font-weight: 800;
  color: #6d7792;
  margin-top: -8px;
}
.welcome-desc-c {
  font-size: 14.5px;
  color: #5c6580;
  line-height: 1.75;
  background: rgba(255,255,255,0.94);
  border-radius: 22px;
  padding: 18px 20px;
  box-shadow: var(--card-shadow);
  max-width: 360px;
  margin: 6px auto 0;
}
.welcome-pills {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 10px;
  margin-top: 4px;
}
.pill-sm {
  display: inline-block; background: rgba(255,255,255,0.98);
  padding: 9px 18px; border-radius: 999px;
  font-weight: 800; color: #667089; font-size: 14px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.05);
}
/* Keep welcome page button fixed at bottom so it never scrolls off */
.welcome-btn-wrap {
  position: fixed; bottom: 0; left: 50%;
  transform: translateX(-50%);
  width: 100%; max-width: 430px;
  padding: 12px 14px 20px; z-index: 10;
  background: linear-gradient(to top, rgba(238,234,248,0.97) 70%, transparent);
}

/* =================== PAGE 2 (characters) =================== */
.char-row-note { font-size: 15px; color: #6b7690; text-align: center; margin-bottom: 8px; }
.char-box { border-radius: 20px; padding: 12px; margin-bottom: 10px; }
.char-box-girl { background: #efd7ee; }
.char-box-boy  { background: #dbeaf7; }
.char-name-c { font-size: 20px; font-weight: 900; color: #18264a; text-align: center; margin: 6px 0 4px; }
.char-desc-c {
  font-size: 12.5px; color: #6d7792; line-height: 1.55;
  min-height: 52px; text-align: center; margin-bottom: 4px;
}

/* =================== PAGE 3 (model picker + camera) =================== */
.nq-picker-wrap {
  background: var(--white); border-radius: 20px;
  padding: 14px 14px 10px; margin-bottom: 14px;
  box-shadow: 0 2px 12px rgba(123,111,212,0.10); direction: rtl;
  border: 2px solid rgba(123,111,212,0.12);
}
.nq-picker-hdr {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 10px;
}
.nq-picker-title {
  font-size: 15px; font-weight: 800; color: var(--text-dark);
  display: flex; align-items: center; gap: 6px;
}
.nq-picker-active-chip {
  font-size: 11.5px; font-weight: 700; color: var(--purple-dark);
  background: linear-gradient(135deg,#ede9fc,#ddd5f8);
  border-radius: 999px; padding: 4px 10px;
}
.nq-picker-desc {
  font-size: 12px; color: var(--text-mid); line-height: 1.5;
  padding: 8px 12px; background: rgba(237,233,252,0.55);
  border-radius: 12px; margin-top: 2px;
}
/* Picker tile buttons */
.nq-picker-wrap div.stButton > button {
  width: 100% !important; min-height: 78px !important;
  padding: 8px 6px !important; border-radius: 14px !important;
  background: #f6f3ff !important; color: var(--text-dark) !important;
  font-family: 'Tajawal', sans-serif !important;
  font-weight: 700 !important; font-size: 12.5px !important;
  line-height: 1.4 !important; white-space: pre-line !important;
  border: 2px solid transparent !important;
  box-shadow: 0 2px 8px rgba(91,71,180,0.08) !important;
  transition: all 0.15s ease !important; text-align: center !important;
}
.nq-picker-wrap div.stButton > button:hover {
  transform: translateY(-2px) !important; background: #ede9fc !important;
  box-shadow: 0 6px 16px rgba(123,111,212,0.18) !important;
}
.nq-picker-wrap div.stButton > button:disabled {
  opacity: 0.55 !important; background: #eeeaf8 !important;
  cursor: not-allowed !important; transform: none !important; box-shadow: none !important;
}
.nq-picker-wrap.picker-sel-custom [data-testid="element-container"]:nth-of-type(1) div.stButton > button,
.nq-picker-wrap.picker-sel-imagga [data-testid="element-container"]:nth-of-type(2) div.stButton > button {
  background: linear-gradient(135deg,#ede9fc,#ddd5f8) !important;
  border-color: var(--purple) !important;
  box-shadow: 0 6px 16px rgba(123,111,212,0.25) !important;
}

/* =================== Image card / badges =================== */
.nq-img-card {
  width: 100%; border-radius: 24px; overflow: hidden; position: relative;
  box-shadow: 0 6px 28px rgba(91,71,180,0.18); margin-bottom: 14px;
}
.nq-seg-badge {
  position: absolute; top: 12px; right: 12px;
  background: rgba(76,175,125,0.92); color: white;
  font-size: 12px; font-weight: 700; padding: 5px 12px; border-radius: 18px;
}
.nq-model-badge {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 12px; font-weight: 700; padding: 5px 12px; border-radius: 18px;
  margin-bottom: 8px; margin-left: 6px;
}
.nq-model-custom        { background: #e8f4ff; color: #1a5fa8; }
.nq-model-imagga        { background: #ffeaf2; color: #a02060; }
.nq-tts-badge {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 12px; font-weight: 600; padding: 5px 12px; border-radius: 18px;
  background: #f0ebff; color: #5a3fc0; margin-bottom: 8px;
}

/* =================== Word + spelling cards =================== */
.nq-word-card, .nq-spell-card {
  background: var(--white); border-radius: 24px; box-shadow: var(--card-shadow);
  padding: 18px; margin-bottom: 14px; position: relative; overflow: hidden; direction: rtl;
}
.nq-word-card::before {
  content: ""; position: absolute; top: 0; right: 0; width: 80px; height: 80px;
  background: linear-gradient(135deg, rgba(195,184,245,0.28), transparent);
  border-radius: 0 24px 0 80px;
}
.word-lbl, .audio-lbl, .spell-hdr-lbl, .spell-hint, .meaning-lbl {
  font-size: 13px; font-weight: 600; color: var(--text-mid);
}
.word-row {
  display: flex; align-items: center; justify-content: space-between;
  gap: 14px; margin-bottom: 10px;
}
.word-arabic { font-size: 36px; font-weight: 900; color: var(--text-dark); }
.conf-pill {
  background: linear-gradient(135deg,#eaf7f0,#d4f0e4); color: #2e7d5a;
  font-size: 13px; font-weight: 700; padding: 6px 14px; border-radius: 18px; flex-shrink: 0;
}
.meaning-en {
  font-size: 16px; font-weight: 700; color: #5a3fc0;
  direction: ltr; text-align: center;
  background: #f0ebff; border-radius: 12px;
  padding: 8px 14px; margin-top: 6px;
}
.spell-hdr { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.spell-bubbles {
  display: flex; flex-wrap: wrap; gap: 8px;
  justify-content: flex-end; margin-bottom: 10px;
}
.spell-bubble {
  width: 46px; height: 50px; border-radius: 14px;
  background: linear-gradient(145deg,#ede9fc,#ddd5f8);
  border: 1.5px solid rgba(123,111,212,0.17);
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 2px; font-size: 22px; font-weight: 900; color: var(--purple-dark);
  box-shadow: 0 3px 9px rgba(91,71,180,0.10);
}
.ltr-num { font-size: 9px; font-weight: 600; color: var(--purple-light); line-height: 1; }

/* =================== Buttons =================== */
div.stButton > button {
  width: 100%; border: none; border-radius: 16px;
  padding: 0.9rem 1rem; font-size: 17px; font-weight: 800; color: white;
  background: linear-gradient(135deg,#745cff,#4d96ff);
  box-shadow: 0 10px 22px rgba(91,110,255,0.22);
  transition: 0.18s ease;
}
div.stButton > button:hover { transform: translateY(-2px); }

/* =================== Loader =================== */
.nq-loader-card {
  background: #ffffff; border-radius: 24px; padding: 28px 20px;
  text-align: center; box-shadow: 0 8px 24px rgba(91,71,180,0.15);
  margin: 20px auto; max-width: 480px;
}
.nq-loader-emoji { font-size: 60px; animation: nq-bounce 1.4s ease-in-out infinite; display: inline-block; }
@keyframes nq-bounce {
  0%,100% { transform: translateY(0) rotate(-6deg); }
  50%     { transform: translateY(-10px) rotate(6deg); }
}
.nq-loader-text { font-size: 20px; font-weight: 800; color: #4a3ea0; margin-top: 12px; }
.nq-loader-bar {
  margin: 16px auto 0; height: 8px; width: 85%; max-width: 320px;
  background: #e9e5fa; border-radius: 999px; overflow: hidden; position: relative;
}
.nq-loader-bar::before {
  content: ""; position: absolute; left: -40%; top: 0; bottom: 0; width: 40%;
  background: linear-gradient(90deg,#7b6fd4,#e86fa0); border-radius: 999px;
  animation: nq-slide 1.6s ease-in-out infinite;
}
@keyframes nq-slide { 0%{ left: -40%; } 100% { left: 100%; } }

[data-testid="stImage"] img { border-radius: 20px; box-shadow: 0 4px 16px rgba(91,71,180,0.14); }

div.stButton {
  position: relative;
  z-index: 10;
}
</style>

<div class="blob-bg">
  <div class="blob blob-1"></div>
  <div class="blob blob-2"></div>
  <div class="blob blob-3"></div>
</div>
"""

st.markdown(SHARED_CSS, unsafe_allow_html=True)

# =============================================================================
# Page 1 — Welcome (compact, no scroll, full-width أستكشف!)
# =============================================================================
def show_welcome_page():
    bg_path = "kids.png"
    if os.path.exists(bg_path):
        with open(bg_path, "rb") as f:
            bg_b64 = base64.b64encode(f.read()).decode()
        st.markdown(
            f'<div class="welcome-bg" style="background-image:url(\'data:image/png;base64,{bg_b64}\');"></div>'
            f'<div class="welcome-bg-overlay"></div>',
            unsafe_allow_html=True,
        )

    st.markdown(
        """
<div class="welcome-wrap">
  <div class="welcome-title-c">ابدأ رحلتك</div>
  <div class="welcome-subtitle-c">رفيقك الذكي في عالم الاكتشاف</div>
  <div class="welcome-desc-c">
    في هذه الرحلة الجميلة ستتعرّف على الأشياء،<br/>
    وتتعلم بطريقة ممتعة ومشوّقة.
  </div>
  <div class="welcome-pills">
    <span class="pill-sm">🌈 ممتع</span>
    <span class="pill-sm">🧠 ذكي</span>
    <span class="pill-sm">✨ للأطفال</span>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

    if st.button("أستكشف! 🚀", key="start_welcome", type="primary", use_container_width=True):
        go_to_page("characters")

# =============================================================================
# Page 2 — Character selection (side-by-side, full-width buttons)
# =============================================================================
def show_character_page():
    if st.button("⬅ رجوع", key="back_to_welcome", use_container_width=True):
        go_to_page("welcome")

    st.markdown('<div style="height:10px"></div>', unsafe_allow_html=True)
    st.markdown(
        '<div style="font-size:26px; font-weight:900; color:#18264a; '
        'text-align:center; margin-bottom:10px;">'
        'اختَر <span style="background:linear-gradient(90deg,#d9ccff,#c7e3ff);'
        'color:#6d4cff;padding:4px 10px;border-radius:12px;">شخصيتك</span>'
        '</div>',
        unsafe_allow_html=True,
    )

    col_girl, col_boy = st.columns(2, gap="small")

    with col_girl:
        st.markdown('<div class="char-box char-box-girl">', unsafe_allow_html=True)
        if os.path.exists(girl_path):
            st.image(Image.open(girl_path), use_container_width=True)
        else:
            st.error("girl.png")
        st.markdown('</div>', unsafe_allow_html=True)
        st.markdown('<div class="char-name-c">بنت</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="char-desc-c">رفيقة تعلم مرحة تحب القصص والألوان.</div>',
            unsafe_allow_html=True,
        )
        if st.button("اختيار البنت", key="pick_girl", use_container_width=True):
            st.session_state.selected_character = "بنت"
            go_to_page("camera")

    with col_boy:
        st.markdown('<div class="char-box char-box-boy">', unsafe_allow_html=True)
        if os.path.exists(boy_path):
            st.image(Image.open(boy_path), use_container_width=True)
        else:
            st.error("boy.png")
        st.markdown('</div>', unsafe_allow_html=True)
        st.markdown('<div class="char-name-c">ولد</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="char-desc-c">رفيق تعلم نشيط يحب الألعاب والتحديات.</div>',
            unsafe_allow_html=True,
        )
        if st.button("اختيار الولد", key="pick_boy", use_container_width=True):
            st.session_state.selected_character = "ولد"
            go_to_page("camera")

# =============================================================================
# Model picker (used on page 3)
# =============================================================================
def show_model_picker():
    models = fetch_available_models()
    if not models:
        return

    available_ids = [m["id"] for m in models if m.get("available", False)]
    if not available_ids:
        st.warning("⚠️ لا توجد نماذج متاحة حالياً.")
        return
    # Default model must be "custom"; if custom is unavailable, fall back to first available
    if st.session_state.selected_model not in available_ids:
        st.session_state.selected_model = (
            DEFAULT_MODEL if DEFAULT_MODEL in available_ids else available_ids[0]
        )

    current   = next((m for m in models if m["id"] == st.session_state.selected_model), models[0])
    active_id = st.session_state.selected_model

    st.markdown(
        f'<div class="nq-picker-wrap picker-sel-{active_id}">'
        f'<div class="nq-picker-hdr">'
        f'  <span class="nq-picker-title">🤖 اختر نموذج الذكاء الاصطناعي</span>'
        f'  <span class="nq-picker-active-chip">{current["emoji"]} {current["name_ar"]}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Card grid — one row of 2 for the two models
    cols = st.columns(2, gap="small")
    for i, m in enumerate(models):
        is_available = m.get("available", True)
        label = f"{m['emoji']} {m['name_ar']}\n{m['num_classes_label']} فئة"
        if not is_available:
            label += "\n(غير مفعّل)"
        with cols[i % 2]:
            if st.button(
                label,
                key=f"pick_model_{m['id']}",
                disabled=not is_available,
                use_container_width=True,
            ):
                st.session_state.selected_model = m["id"]
                st.rerun()

    if current.get("description_ar"):
        st.markdown(
            f'<div class="nq-picker-desc">ℹ️ {current["description_ar"]}</div>',
            unsafe_allow_html=True,
        )
    st.markdown('</div>', unsafe_allow_html=True)

# =============================================================================
# Page 3/4 — Camera + confirmation (skips old page 5; jumps straight to results)
# =============================================================================
CAMERA_CSS = """
<style>
[data-testid="stCameraInput"] {
    position: relative !important;
    background: #1a1a2e !important;
    border-radius: 24px !important;
    box-shadow: 0 6px 24px rgba(91,71,180,0.28) !important;
    padding: 10px !important;
    max-width: 460px !important;
    margin: 0 auto 10px !important;
    overflow: hidden !important;
}
[data-testid="stCameraInput"] > div:first-child {
    width: 100% !important; aspect-ratio: 3/4 !important;
    position: relative !important; border-radius: 18px !important;
    overflow: hidden !important; background: #000 !important;
}
[data-testid="stCameraInput"] video,
[data-testid="stCameraInput"] img {
    position: absolute !important; inset: 0 !important;
    width: 100% !important; height: 100% !important;
    object-fit: cover !important; border-radius: 18px !important; display: block !important;
}
[data-testid="stCameraInput"]::before {
    content: ""; position: absolute;
    top: 20px; left: 20px; right: 20px; bottom: 80px;
    pointer-events: none; z-index: 4;
    background:
        linear-gradient(to right,  rgba(255,255,255,0.55) 22px, transparent 22px) top left    / 22px 2px no-repeat,
        linear-gradient(to bottom, rgba(255,255,255,0.55) 22px, transparent 22px) top left    / 2px 22px no-repeat,
        linear-gradient(to left,   rgba(255,255,255,0.55) 22px, transparent 22px) top right   / 22px 2px no-repeat,
        linear-gradient(to bottom, rgba(255,255,255,0.55) 22px, transparent 22px) top right   / 2px 22px no-repeat,
        linear-gradient(to right,  rgba(255,255,255,0.55) 22px, transparent 22px) bottom left / 22px 2px no-repeat,
        linear-gradient(to top,    rgba(255,255,255,0.55) 22px, transparent 22px) bottom left / 2px 22px no-repeat,
        linear-gradient(to left,   rgba(255,255,255,0.55) 22px, transparent 22px) bottom right/ 22px 2px no-repeat,
        linear-gradient(to top,    rgba(255,255,255,0.55) 22px, transparent 22px) bottom right/ 2px 22px no-repeat;
}
[data-testid="stCameraInput"]::after {
    content: "ضع الشيء هنا"; position: absolute;
    top: calc(50% - 40px); left: 50%; transform: translate(-50%,-50%);
    width: 52%; aspect-ratio: 1; border-radius: 20px;
    border: 2.5px solid rgba(200,185,255,0.9);
    pointer-events: none; z-index: 5;
    animation: nq-glow 2.2s ease-in-out infinite;
    display: flex; align-items: flex-end; justify-content: center;
    padding-bottom: 6px;
    font-family: 'Tajawal',sans-serif; font-size: 12px; font-weight: 600;
    color: rgba(210,200,255,0.9);
}
@keyframes nq-glow {
    0%,100% { box-shadow: 0 0 0 3px rgba(160,140,255,0.20), 0 0 18px 4px rgba(160,140,255,0.35), inset 0 0 18px 2px rgba(160,140,255,0.10); }
    50%     { box-shadow: 0 0 0 5px rgba(160,140,255,0.35), 0 0 28px 8px rgba(160,140,255,0.50), inset 0 0 22px 5px rgba(160,140,255,0.18); }
}
[data-testid="stCameraInput"] button[kind="primary"],
[data-testid="stCameraInput"] button[kind="primaryFormSubmit"],
[data-testid="stCameraInput"] > div > button:first-of-type {
    width: 68px !important; height: 68px !important;
    min-width: 68px !important; max-width: 68px !important;
    border-radius: 50% !important; border: 5px solid #a89de8 !important;
    background: #ffffff !important; color: transparent !important;
    font-size: 0 !important; padding: 0 !important;
    margin: 12px auto 6px !important; display: block !important;
    box-shadow: 0 4px 20px rgba(123,111,212,0.36) !important;
    position: relative !important;
}
[data-testid="stCameraInput"] button[kind="primary"]::before,
[data-testid="stCameraInput"] button[kind="primaryFormSubmit"]::before,
[data-testid="stCameraInput"] > div > button:first-of-type::before {
    content: ""; position: absolute; top: 50%; left: 50%;
    transform: translate(-50%,-50%); width: 48px; height: 48px;
    border-radius: 50%; background: linear-gradient(135deg,#7b6fd4,#5a4fb0);
}
[data-testid="stCameraInput"] button:not([kind="primary"]):not([kind="primaryFormSubmit"]):not(:first-of-type) {
    width: auto !important; height: 30px !important;
    background: rgba(255,255,255,0.12) !important; color: rgba(255,255,255,0.8) !important;
    border: none !important; border-radius: 10px !important;
    font-size: 11px !important; font-weight: 600 !important;
    padding: 4px 12px !important; margin: 6px auto !important;
    box-shadow: none !important; display: inline-flex !important;
}
[data-testid="stCameraInput"] label,
[data-testid="stCameraInput"] [data-testid="stWidgetLabel"] { display: none !important; }
</style>
"""


def show_camera_page():
    st.markdown(CAMERA_CSS, unsafe_allow_html=True)

    # Header — no emoji on the right (per spec: remove top-right emoji)
    st.markdown(
        f'<div class="nq-header">'
        f'  <div class="nq-avatar">{get_character_emoji()}</div>'
        f'  <span class="nq-title">📸 وقت التصوير!</span>'
        f'  <div class="nq-header-spacer"></div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    pending = st.session_state.get("pending_capture")

    # ── Confirmation view (Page 4) ───────────────────────────────────────
    if pending:
        show_model_picker()

        st.markdown(
            '<div class="nq-instruction">'
            '<span class="nq-instruction-icon">👀</span>'
            '<p class="nq-instruction-text">هل هذه الصورة جيدة؟</p>'
            '</div>',
            unsafe_allow_html=True,
        )

        st.markdown('<div class="nq-img-card">', unsafe_allow_html=True)
        st.image(pending, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

        col_use, col_retake = st.columns(2, gap="small")
        with col_use:
            confirm_clicked = st.button(
                "✅ استخدم هذه الصورة",
                use_container_width=True, type="primary", key="confirm_pic",
            )
        with col_retake:
            if st.button("🔄 صورة جديدة", use_container_width=True, key="retake_pending"):
                st.session_state.pending_capture = None
                st.session_state.pop("cam_input", None)
                st.rerun()

        # ⬇ Once the user confirms, call the API and GO STRAIGHT TO RESULTS.
        if confirm_clicked:
            placeholder = st.empty()
            placeholder.markdown(
                """
                <div class="nq-loader-card">
                  <div class="nq-loader-emoji">🤖</div>
                  <div class="nq-loader-text">المستكشف يفكر...</div>
                  <div class="nq-loader-bar"></div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            result = segment_image(
                ("capture.jpg", pending, "image/jpeg"),
                model_id=st.session_state.selected_model,
            )
            placeholder.empty()

            if "error" in result:
                st.error(result["error"])
            else:
                apply_segmentation_result(pending, result)
                st.session_state.pending_capture = None
                st.session_state.pop("cam_input", None)
                # Direct jump to results — no intermediate page 5.
                st.session_state["_results_page_init"] = False
                st.session_state.current_page = "results"
                st.rerun()
        return

    # ── Live camera view (Page 3) ────────────────────────────────────────
    show_model_picker()

    # Gendered instruction
    st.markdown(
        f'<div class="nq-instruction">'
        f'<span class="nq-instruction-icon">🎯</span>'
        f'<p class="nq-instruction-text">{gendered_place_hint()}</p>'
        f'</div>',
        unsafe_allow_html=True,
    )

    cam_shot = st.camera_input("التقط صورة", label_visibility="collapsed", key="cam_input")
    if cam_shot is not None:
        cropped_bytes = _center_square_crop(cam_shot.getvalue())
        st.session_state.pending_capture = cropped_bytes
        st.rerun()

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    if st.button("⬅ رجوع", use_container_width=True, key="camera_back_empty"):
        go_to_page("characters")

# =============================================================================
# Page 6 — Results
# =============================================================================
def to_eastern(n: int) -> str:
    return str(n).translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩"))


def autoplay_audio(audio_bytes: bytes) -> None:
    """
    Embed an HTML5 <audio> element that autoplays on page load.
    st.audio does not autoplay — this is the reliable TTS trigger.
    """
    if not audio_bytes:
        return
    b64 = base64.b64encode(audio_bytes).decode("ascii")
    # controls included so the user can replay; autoplay for instant feedback
    st.markdown(
        f"""
        <audio autoplay controls style="width:100%; margin-top:6px;">
          <source src="data:audio/mp3;base64,{b64}" type="audio/mpeg">
        </audio>
        """,
        unsafe_allow_html=True,
    )


MODEL_LABELS = {
    "custom":        ("🎯 نموذج الأطفال",   "nq-model-custom"),
    "imagga":        ("🏷️ Imagga",         "nq-model-imagga"),
}


def show_results_page():
    # Reset autoplay flag so TTS fires each time the results page is shown
    if not st.session_state.get("_results_page_init"):
        st.session_state.audio_autoplayed = False
        st.session_state["_results_page_init"] = True

    st.markdown(
        f'<div class="nq-header">'
        f'  <div class="nq-avatar">{get_character_emoji()}</div>'
        f'  <span class="nq-title">✨ تعلّمت كلمة جديدة!</span>'
        f'  <div class="nq-header-spacer"></div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    captured        = st.session_state.get("captured_image")
    annotated       = st.session_state.get("annotated_image")
    word_ar         = st.session_state.get("predicted_label", "غير معروف")
    word_en         = st.session_state.get("predicted_label_en", "")
    conf            = st.session_state.get("predicted_conf", "0٪")
    coverage        = st.session_state.get("predicted_coverage", 0.0)
    audio_word      = st.session_state.get("audio_word")
    audio_combined  = st.session_state.get("audio_combined")
    audio_letters   = st.session_state.get("audio_letters", [])
    model_used      = st.session_state.get("model_used", "")
    tts_voice       = st.session_state.get("tts_voice", "")

    # ── Model + TTS badges ───────────────────────────────────────────────
    if model_used or tts_voice:
        badge_html = '<div style="margin-bottom:6px; direction:rtl;">'
        if model_used in MODEL_LABELS:
            label, cls = MODEL_LABELS[model_used]
            badge_html += f'<span class="nq-model-badge {cls}">{label}</span>'
        if tts_voice:
            voice_label = tts_voice.replace("Neural", "").replace("ar-SA-", "")
            badge_html += f'<span class="nq-tts-badge">🔊 {voice_label}</span>'
        badge_html += '</div>'
        st.markdown(badge_html, unsafe_allow_html=True)

    # ── Segmentation image with ENGLISH label overlay ────────────────────
    # The backend already masked the object and burned an Arabic label in the
    # top-right. We paint an English label over that same spot so the
    # displayed label ends up in English (per spec).
    try:
        conf_pct = float(conf.replace("٪", "").replace("%", "")) if conf else 0.0
    except Exception:
        conf_pct = 0.0

    display_bytes = None
    if annotated and word_en:
        display_bytes = overlay_english_label(annotated, word_en, conf_pct)
    elif annotated:
        display_bytes = annotated
    elif captured:
        display_bytes = captured

    is_cloud = model_used in ("imagga",)

    st.markdown('<div class="nq-img-card">', unsafe_allow_html=True)
    if display_bytes:
        st.image(display_bytes, use_container_width=True)
    else:
        st.info("لا توجد صورة لعرضها.")
    if not is_cloud:
        st.markdown(
            f'<div class="nq-seg-badge">✓ {coverage:.1f}%</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown('<div class="nq-seg-badge">✓ تم التعرف</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # ── Word card (Arabic word + English meaning + confidence) ───────────
    meaning_html = (
        f'<div class="meaning-lbl">المعنى بالإنجليزية</div>'
        f'<div class="meaning-en">{word_en}</div>'
        if word_en else ""
    )
    st.markdown(
        f"""
        <div class="nq-word-card">
          <div class="word-lbl">تعرّفت على:</div>
          <div class="word-row">
            <div class="word-arabic">{word_ar}</div>
            <div class="conf-pill">{conf}</div>
          </div>
          {meaning_html}
          <div class="audio-lbl" style="margin-top:10px;">🔊 استمع للكلمة</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── TTS: autoplay once, plus a controls bar for replay ──────────────
    main_audio_b64 = audio_combined or audio_word
    main_bytes     = _decode_data_uri(main_audio_b64) if main_audio_b64 else None

    if main_bytes:
        if not st.session_state.audio_autoplayed:
            autoplay_audio(main_bytes)
            st.session_state.audio_autoplayed = True
        else:
            # Already played once — give a normal controls bar for replay
            st.audio(main_bytes, format="audio/mp3")
    else:
        st.info("🔇 لم يتوفر صوت لهذه الكلمة")

    # ── Spelling bubbles ─────────────────────────────────────────────────
    letters = st.session_state.get("predicted_spelling", []) or list(word_ar)
    bubbles = "".join(
        f'<div class="spell-bubble"><span>{ch}</span>'
        f'<span class="ltr-num">{to_eastern(i + 1)}</span></div>'
        for i, ch in enumerate(letters)
    )
    st.markdown(
        f"""
        <div class="nq-spell-card">
          <div class="spell-hdr">
            <span style="font-size:20px;">🔤</span>
            <span class="spell-hdr-lbl">كيف تُكتب؟</span>
          </div>
          <div class="spell-bubbles">{bubbles}</div>
          <div class="spell-hint">استمع لكل حرف بالترتيب</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Per-letter audio ────────────────────────────────────────────────
    if audio_letters:
        letter_cols = st.columns(min(len(audio_letters), 6))
        for i, item in enumerate(audio_letters):
            col = letter_cols[i % len(letter_cols)]
            with col:
                st.markdown(
                    f"<div style='text-align:center;font-size:26px;font-weight:900;"
                    f"color:#18264a'>{item.get('letter','')}</div>",
                    unsafe_allow_html=True,
                )
                audio_data = _decode_data_uri(item.get("audio", ""))
                if audio_data:
                    st.audio(audio_data, format="audio/mp3")

    # ── Action buttons ──────────────────────────────────────────────────
    if st.button("📷 صورة أخرى", use_container_width=True, key="capture_again"):
        reset_prediction()
        go_to_page("camera")

# =============================================================================
# Router
# =============================================================================
page = st.session_state.current_page
if page == "welcome":
    show_welcome_page()
elif page == "characters":
    show_character_page()
elif page == "camera":
    show_camera_page()
else:
    show_results_page()