import streamlit as st
from PIL import Image
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

# =============================
# الملفات المطلوبة في نفس المجلد
# =============================
logo_path = "logo.png"
kids_image_path = "kids.png"
girl_path = "girl.png"
boy_path = "boy.png"

# =============================
# API URL — hardcoded Railway backend
# =============================
API_URL = "https://interactive-educational-application-production.up.railway.app"

# =============================
# Session State
# =============================
_DEFAULTS = {
    "selected_character": "",
    "current_page": "welcome",
    "captured_image": None,
    "captured_name": "",
    "annotated_image": None,
    "predicted_label": "",
    "predicted_label_en": "",
    "predicted_conf": "",
    "predicted_coverage": 0.0,
    "predicted_spelling": [],
    "audio_word": None,
    "audio_letters": [],
    "audio_combined": None,
    "pending_capture": None,
}
for _k, _v in _DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

# =============================
# API helpers
# =============================
def _decode_data_uri(data_uri: str) -> bytes:
    if not data_uri or "," not in data_uri:
        return b""
    try:
        return base64.b64decode(data_uri.split(",", 1)[1])
    except Exception:
        return b""


def _center_square_crop(image_bytes: bytes, guide_ratio: float = 0.62) -> bytes:
    """Crop to a centered square matching the on-screen guide."""
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        w, h = img.size
        side = int(min(w, h) * guide_ratio)
        left = (w - side) // 2
        top = (h - side) // 2
        cropped = img.crop((left, top, left + side, top + side))
        buf = io.BytesIO()
        cropped.save(buf, format="JPEG", quality=92)
        return buf.getvalue()
    except Exception:
        return image_bytes


def check_api_health() -> dict:
    try:
        r = requests.get(f"{API_URL}/health", timeout=5)
        if r.status_code == 200:
            return {"ok": True, "data": r.json()}
        return {"ok": False, "error": f"الخادم رد بـ {r.status_code}"}
    except requests.exceptions.ConnectionError:
        return {"ok": False, "error": "تعذر الاتصال بالخادم."}
    except requests.exceptions.Timeout:
        return {"ok": False, "error": "انتهت مهلة الاتصال بالخادم."}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def segment_image(image_source) -> dict:
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

        files = {"file": (name, data, mime)}
        response = requests.post(f"{API_URL}/segment", files=files, timeout=120)

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
        return {"error": "النموذج استغرق وقتاً طويلاً — حاولي مرة أخرى."}
    except Exception as e:
        return {"error": str(e)}


def apply_segmentation_result(source_bytes: bytes, source_name: str, result: dict) -> None:
    st.session_state.captured_image = source_bytes
    st.session_state.captured_name = source_name
    st.session_state.annotated_image = _decode_data_uri(result.get("annotated_image", ""))
    st.session_state.predicted_label = result.get("label_ar", "غير معروف")
    st.session_state.predicted_label_en = result.get("label_en", "")
    conf_value = result.get("confidence", 0) or 0
    st.session_state.predicted_conf = f"{int(conf_value * 100)}٪"
    st.session_state.predicted_coverage = result.get("coverage_percent", 0.0)
    st.session_state.predicted_spelling = result.get("spelling", [])
    st.session_state.audio_word = result.get("audio_word")
    st.session_state.audio_letters = result.get("audio_letters", [])
    st.session_state.audio_combined = result.get("audio_combined")


def reset_prediction():
    st.session_state.captured_image = None
    st.session_state.captured_name = ""
    st.session_state.annotated_image = None
    st.session_state.predicted_label = ""
    st.session_state.predicted_label_en = ""
    st.session_state.predicted_conf = ""
    st.session_state.predicted_coverage = 0.0
    st.session_state.predicted_spelling = []
    st.session_state.audio_word = None
    st.session_state.audio_letters = []
    st.session_state.audio_combined = None
    st.session_state.pending_capture = None


def get_selected_character_image():
    if st.session_state.selected_character == "بنت" and os.path.exists(girl_path):
        return girl_path
    if st.session_state.selected_character == "ولد" and os.path.exists(boy_path):
        return boy_path
    return None


def show_selected_character_badge():
    avatar_path = get_selected_character_image()
    if not avatar_path:
        return
    with open(avatar_path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode()
    st.markdown(
        f"""
        <div class="selected-avatar-badge">
            <img src="data:image/png;base64,{encoded}" alt="character">
        </div>
        """,
        unsafe_allow_html=True,
    )

# =============================
# Shared CSS — phone-first, deduplicated
# =============================
SHARED_CSS = """
<style>
header {visibility: hidden;}
footer {visibility: hidden;}
#MainMenu {visibility: hidden;}

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
  --btn-pink-dark: #c9507f;
  --text-dark:     #2d2557;
  --text-mid:      #6b62a8;
  --card-shadow:   0 4px 24px rgba(91,71,180,0.13);
}

html, body,
[data-testid="stAppViewContainer"],
[data-testid="stApp"] {
  background: var(--bg) !important;
  font-family: 'Tajawal', sans-serif !important;
  direction: rtl;
}

/* Phone-first: narrow column, tight padding */
.main .block-container {
  max-width: 430px !important;
  width: 100% !important;
  margin: 0 auto !important;
  padding: 14px 12px 80px !important;
  animation: fadePage 0.55s ease;
}

@keyframes fadePage {
  from {opacity: 0; transform: translateY(16px);}
  to   {opacity: 1; transform: translateY(0);}
}

@keyframes floatImage {
  0%   {transform: translateY(0);}
  50%  {transform: translateY(-10px);}
  100% {transform: translateY(0);}
}

.blob-bg { position:fixed; inset:0; pointer-events:none; z-index:0; overflow:hidden; }
.blob { position:absolute; border-radius:50%; filter:blur(55px); opacity:0.30; }
.blob-1 { width:200px; height:200px; background:#c3b8f5; top:-6%; left:-10%; }
.blob-2 { width:160px; height:160px; background:#f5c8e8; bottom:4%; right:-12%; }
.blob-3 { width:120px; height:120px; background:#b8f0e8; top:44%; right:-8%; opacity:0.18; }

/* ===== Welcome page ===== */
.logo-wrap { display:flex; justify-content:center; margin-top:6px; }
.welcome-title {
    font-size: 40px; font-weight: 900; color: #18264a;
    margin-top: 12px; margin-bottom: 8px; text-align: center; line-height: 1.1;
}
.welcome-subtitle {
    font-size: 20px; font-weight: 800; color: #6d7792;
    margin-bottom: 14px; text-align: center;
}
.welcome-desc {
    font-size: 16px; color: #7a849f; line-height: 1.9;
    text-align: center; margin-bottom: 18px;
}

/* ===== Characters page ===== */
.main-title {
    font-size: 32px; font-weight: 900; line-height: 1.15;
    color: #18264a; margin-bottom: 12px; text-align: center;
}
.highlight {
    background: linear-gradient(90deg,#d9ccff,#c7e3ff); color:#6d4cff;
    padding: 4px 12px; border-radius: 14px;
}
.sub-text {
    font-size: 16px; color: #6b7690; line-height: 1.8;
    margin-bottom: 16px; text-align: center;
}
.pill {
    display: inline-block; background: rgba(255,255,255,0.98);
    padding: 9px 14px; border-radius: 999px;
    margin-left: 6px; margin-bottom: 8px;
    font-weight: 800; color: #667089;
    box-shadow: 0 4px 12px rgba(0,0,0,0.05); font-size: 14px;
}
.message-box {
    background: #f2d8a4; color: #5f462f; border-radius: 20px;
    padding: 14px; text-align: center; font-size: 17px;
    font-weight: 800; margin-top: 14px; margin-bottom: 10px;
}
.note { text-align: center; color: #7b85a1; font-size: 14px; margin-top: 8px; }
.section-title {
    text-align: center; font-size: 22px; font-weight: 900;
    color: #1b2a4c; margin: 14px 0 12px;
}

.card { transition: transform 0.18s ease, box-shadow 0.18s ease; }
.card:hover { transform: translateY(-4px); box-shadow: 0 16px 28px rgba(42,58,95,0.12); }

.img-box-girl { background:#efd7ee; border-radius:20px; padding:14px; margin-bottom:12px; }
.img-box-boy  { background:#dbeaf7; border-radius:20px; padding:14px; margin-bottom:12px; }

.char-name {
    font-size: 20px; font-weight: 900; color: #18264a;
    margin: 6px 0 4px; text-align: center;
}
.char-desc {
    font-size: 13px; color: #6d7792; line-height: 1.65;
    text-align: center; margin-bottom: 8px; min-height: 72px;
}

.floating-image {
    animation: floatImage 3.5s ease-in-out infinite;
    filter: drop-shadow(0 14px 22px rgba(0, 0, 0, 0.10));
    margin: 10px auto 4px; max-width: 300px;
}

/* ===== Header (camera + results) ===== */
.nq-header {
  display:flex; align-items:center; justify-content:space-between;
  padding:10px 0 14px;
}
.nq-title { font-size:18px; font-weight:800; color:var(--text-dark); text-align:center; flex:1; }
.nq-avatar {
  width:40px; height:40px; border-radius:50%;
  background:linear-gradient(135deg,#c3b8f5,#f5c8e8);
  display:flex; align-items:center; justify-content:center;
  font-size:22px; flex-shrink:0;
}
.nq-back {
  width:40px; height:40px; border-radius:50%; background:var(--white);
  display:flex; align-items:center; justify-content:center;
  box-shadow:0 2px 10px rgba(123,111,212,0.18);
  font-size:20px; color:var(--purple); font-weight:900; flex-shrink:0;
}

.nq-instruction {
  background:var(--white); border-radius:18px; padding:10px 14px;
  display:flex; align-items:center; gap:10px;
  box-shadow:0 2px 12px rgba(123,111,212,0.10);
  margin-bottom:14px; direction:rtl;
}
.nq-instruction-icon { font-size:22px; flex-shrink:0; }
.nq-instruction-text { font-size:14px; font-weight:500; color:var(--text-mid); line-height:1.5; }

/* ===== Results page — image + cards ===== */
.nq-img-card {
  width:100%; border-radius:24px; overflow:hidden; position:relative;
  box-shadow:0 6px 26px rgba(91,71,180,0.18); margin-bottom:12px;
}
.nq-img-placeholder {
  width:100%; aspect-ratio:4/3; background:linear-gradient(135deg,#e8e4fc,#f5e8f8);
  display:flex; flex-direction:column; align-items:center; justify-content:center; gap:8px;
  color:var(--text-mid); font-size:14px; font-weight:500;
}
.nq-seg-badge {
  position:absolute; top:12px; right:12px;
  background:rgba(76,175,125,0.92); color:white;
  font-size:12px; font-weight:700; padding:5px 12px; border-radius:18px;
}

.nq-word-card, .nq-spell-card {
  background:var(--white); border-radius:24px; box-shadow:var(--card-shadow);
  padding:18px; margin-bottom:14px; position:relative; overflow:hidden; direction:rtl;
}
.nq-word-card::before {
  content:''; position:absolute; top:0; right:0; width:72px; height:72px;
  background:linear-gradient(135deg,rgba(195,184,245,0.28),transparent);
  border-radius:0 24px 0 72px;
}

/* Entrance animations */
@keyframes bounce-in { 0% { transform: scale(0); opacity: 0; } 100% { transform: scale(1); opacity: 1; } }
@keyframes slide-up  { 0% { transform: translateY(12px); opacity: 0; } 100% { transform: translateY(0); opacity: 1; } }

.word-lbl, .audio-lbl, .spell-hdr-lbl, .spell-hint {
  font-size:13px; font-weight:600; color:var(--text-mid);
}
.word-row { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:14px; }
.word-left { display:flex; align-items:center; gap:12px; }
.word-arabic {
    font-size:32px; font-weight:900; color:var(--text-dark);
    animation: slide-up 0.5s cubic-bezier(0.34,1.56,0.64,1) 0.15s both;
}
.conf-pill {
  background:linear-gradient(135deg,#eaf7f0,#d4f0e4); color:#2e7d5a;
  font-size:13px; font-weight:700; padding:6px 14px; border-radius:18px; flex-shrink:0;
}

/* Animated wave bars */
.audio-row { display:flex; align-items:center; gap:10px; margin-top:6px; }
.audio-wave { flex:1; display:flex; align-items:center; gap:4px; height:36px; }
.wbar { flex:1; background:var(--purple-light); border-radius:3px;
        animation: wave-anim 0.9s ease-in-out infinite; }
.wbar:nth-child(1){height:20%; animation-delay:0s}
.wbar:nth-child(2){height:50%; animation-delay:.10s}
.wbar:nth-child(3){height:80%; animation-delay:.20s}
.wbar:nth-child(4){height:40%; animation-delay:.15s}
.wbar:nth-child(5){height:70%; animation-delay:.05s}
.wbar:nth-child(6){height:55%; animation-delay:.25s}
.wbar:nth-child(7){height:30%; animation-delay:.18s}
.wbar:nth-child(8){height:65%; animation-delay:.08s}
.wbar:nth-child(9){height:45%; animation-delay:.22s}
.wbar:nth-child(10){height:25%; animation-delay:.12s}
@keyframes wave-anim { 0%,100% { transform: scaleY(0.6);} 50% { transform: scaleY(1.2);} }

/* Spelling bubbles */
.spell-hdr { display:flex; align-items:center; gap:10px; margin-bottom:12px; }
.spell-hdr-icon { font-size:20px; }
.spell-bubbles { display:flex; flex-wrap:wrap; gap:8px; flex-direction:row; justify-content:flex-end; margin-bottom:10px; }
.spell-bubble {
  width:44px; height:48px; border-radius:14px;
  background:linear-gradient(145deg,#ede9fc,#ddd5f8);
  border:1.5px solid rgba(123,111,212,0.17);
  display:flex; flex-direction:column; align-items:center; justify-content:center;
  gap:2px; font-size:20px; font-weight:900; color:var(--purple-dark);
  box-shadow:0 3px 10px rgba(91,71,180,0.10);
  animation: bounce-in 0.5s cubic-bezier(0.34,1.56,0.64,1) both;
}
.ltr-num { font-size:10px; font-weight:600; color:var(--purple-light); line-height:1; }

[data-testid="stFileUploaderDropzone"] {
  border:1.5px dashed var(--purple-light) !important;
  border-radius:16px !important; background:rgba(255,255,255,0.6) !important;
}

/* ===== Buttons (single consolidated rule with disabled state) ===== */
div.stButton > button {
  width: 100%; border: none; border-radius: 16px;
  padding: 0.75rem 1rem; font-size: 16px; font-weight: 800;
  color: white;
  background: linear-gradient(135deg, #745cff, #4d96ff);
  box-shadow: 0 10px 22px rgba(91,110,255,0.22);
  transition: 0.18s ease;
  min-height: 44px; /* thumb-friendly */
}
div.stButton > button:hover:not(:disabled) { transform: translateY(-2px); }
div.stButton > button:disabled {
  opacity: 0.45; cursor: not-allowed; box-shadow: none;
}

.start-btn { max-width: 220px; margin: 18px auto 0; }
.back-btn  { max-width: 140px; margin-bottom: 12px; }

[data-testid="stImage"] img { border-radius:18px; box-shadow:0 4px 16px rgba(91,71,180,0.14); }

/* ===== Fixed character badge (top-left) ===== */
.selected-avatar-badge {
  position: fixed; top: 12px; left: 12px;
  width: 56px; height: 56px; border-radius: 50%;
  background: #ffffff;
  box-shadow: 0 6px 16px rgba(91,71,180,0.22);
  padding: 3px; z-index: 9999;
  display: flex; align-items: center; justify-content: center;
}
.selected-avatar-badge img {
  width: 100%; height: 100%; border-radius: 50%; object-fit: cover;
}

/* ===== Small phone tweaks ===== */
@media (max-width: 380px) {
  .welcome-title { font-size: 34px; }
  .main-title    { font-size: 28px; }
  .word-arabic   { font-size: 28px; }
  .char-desc     { min-height: 64px; }
  .nq-title      { font-size: 16px; }
  .selected-avatar-badge { width:48px; height:48px; top:10px; left:10px; }
}
</style>

<div class="blob-bg">
  <div class="blob blob-1"></div>
  <div class="blob blob-2"></div>
  <div class="blob blob-3"></div>
</div>
"""

st.markdown(SHARED_CSS, unsafe_allow_html=True)

# =============================
# Navigation helper
# =============================
def go_to_page(page_name: str):
    with st.spinner("جاري الانتقال..."):
        time.sleep(0.35)
    st.session_state.current_page = page_name
    st.rerun()

# =============================
# Welcome page
# =============================
def show_welcome_page():
    st.markdown('<div class="logo-wrap">', unsafe_allow_html=True)
    if os.path.exists(logo_path):
        st.image(logo_path, width=170)
    else:
        st.warning("ملف logo.png غير موجود")
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="welcome-title">ابدأ رحلتك</div>', unsafe_allow_html=True)
    st.markdown('<div class="welcome-subtitle">مرحبًا بالمستكشف الذكي</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="welcome-desc">في هذه الرحلة الجميلة ستتعرف على الأشياء، وتتعلم بطريقة ممتعة، وتختار شخصيتك المفضلة لتبدأ المغامرة.</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div style="text-align:center;">
            <span class="pill">🌈 ممتع</span>
            <span class="pill">🧠 ذكي</span>
            <span class="pill">✨ مناسب للأطفال</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if os.path.exists(kids_image_path):
        st.markdown('<div class="floating-image">', unsafe_allow_html=True)
        st.image(kids_image_path, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="start-btn">', unsafe_allow_html=True)
    if st.button("ابدأ", key="start_welcome"):
        go_to_page("characters")
    st.markdown('</div>', unsafe_allow_html=True)

# =============================
# Character page
# =============================
def show_character_page():
    st.markdown('<div class="back-btn">', unsafe_allow_html=True)
    if st.button("⬅ رجوع", key="back_to_welcome"):
        go_to_page("welcome")
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown(
        '<div class="main-title">اختَر <span class="highlight">شخصيتك</span></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="sub-text">لازم تختار شخصية أولًا قبل ما تبدأ التعلّم.</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        """
        <div style="text-align:center;">
            <span class="pill">👧 بنت</span>
            <span class="pill">👦 ولد</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="section-title">اختر شخصيتك</div>', unsafe_allow_html=True)

    col_girl, col_boy = st.columns(2, gap="small")

    with col_girl:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="img-box-girl">', unsafe_allow_html=True)
        if os.path.exists(girl_path):
            st.image(Image.open(girl_path), width=140)
        else:
            st.error("ملف girl.png غير موجود")
        st.markdown('</div>', unsafe_allow_html=True)
        st.markdown('<div class="char-name">بنت</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="char-desc">رفيقة تعلم مرحة تحب القصص، والألوان، واكتشاف أشياء جديدة.</div>',
            unsafe_allow_html=True,
        )
        if st.button("اختيار البنت", key="girl_button_unique"):
            st.session_state.selected_character = "بنت"
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    with col_boy:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="img-box-boy">', unsafe_allow_html=True)
        if os.path.exists(boy_path):
            st.image(Image.open(boy_path), width=140)
        else:
            st.error("ملف boy.png غير موجود")
        st.markdown('</div>', unsafe_allow_html=True)
        st.markdown('<div class="char-name">ولد</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="char-desc">رفيق تعلم نشيط يحب الألعاب، والتحديات، والمغامرات الممتعة.</div>',
            unsafe_allow_html=True,
        )
        if st.button("اختيار الولد", key="boy_button_unique"):
            st.session_state.selected_character = "ولد"
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    if st.session_state.selected_character:
        st.markdown(
            f'<div class="message-box">تم اختيار: {st.session_state.selected_character} 💛</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="message-box">اختر بنت أو ولد أولًا</div>',
            unsafe_allow_html=True,
        )

    st.markdown('<div class="note">لن تتمكن من المتابعة حتى تختار الشخصية.</div>', unsafe_allow_html=True)

    st.markdown('<div class="start-btn">', unsafe_allow_html=True)
    start_disabled = st.session_state.selected_character == ""
    if st.button("ابدأ التعلّم", key="start_learning_btn", disabled=start_disabled):
        go_to_page("camera")
    st.markdown('</div>', unsafe_allow_html=True)

# =============================
# Camera page — HTML-style glowing overlay on st.camera_input
# =============================
def show_camera_page():
    show_selected_character_badge()

    # The guide square + corner marks now sit DIRECTLY on the live video
    # (on [data-testid="stCameraInput"] > div:first-child), not on the outer
    # container — so they frame the subject exactly like page2_camera.html.
    st.markdown("""
    <style>
    /* Outer dark frame */
    [data-testid="stCameraInput"] {
        border-radius: 24px;
        background: #1a1a2e;
        box-shadow: 0 8px 28px rgba(91,71,180,0.30);
        padding: 10px 10px 4px;
        max-width: 100%;
        margin: 0 auto 12px;
        position: relative;
        overflow: hidden;
    }

    /* Video wrapper — the overlay surface */
    [data-testid="stCameraInput"] > div:first-child {
        position: relative;
        border-radius: 18px;
        overflow: hidden;
    }

    [data-testid="stCameraInput"] video,
    [data-testid="stCameraInput"] img {
        border-radius: 18px !important;
        width: 100% !important;
        display: block !important;
    }

    /* ==== GLOWING GUIDE SQUARE ==== */
    [data-testid="stCameraInput"] > div:first-child::after {
        content: "ضع الشيء هنا";
        position: absolute;
        top: 50%; left: 50%;
        transform: translate(-50%, -50%);
        width: 62%;
        aspect-ratio: 1;
        border-radius: 20px;
        border: 2.5px solid rgba(200,185,255,0.9);
        pointer-events: none;
        z-index: 4;
        animation: nq-glow-pulse 2.2s ease-in-out infinite;

        display: flex;
        align-items: flex-end;
        justify-content: center;
        padding-bottom: 6px;
        font-family: 'Tajawal', sans-serif;
        font-size: 12px;
        font-weight: 600;
        color: rgba(210,200,255,0.9);
    }
    @keyframes nq-glow-pulse {
        0%,100% {
            box-shadow: 0 0 0 3px rgba(160,140,255,0.20),
                        0 0 18px 4px rgba(160,140,255,0.35),
                        inset 0 0 18px 2px rgba(160,140,255,0.10);
            border-color: rgba(200,185,255,0.85);
        }
        50% {
            box-shadow: 0 0 0 5px rgba(160,140,255,0.35),
                        0 0 32px 10px rgba(160,140,255,0.55),
                        inset 0 0 24px 6px rgba(160,140,255,0.20);
            border-color: rgba(220,210,255,1);
        }
    }

    /* ==== FOUR CORNER MARKS (inside the video area) ==== */
    [data-testid="stCameraInput"] > div:first-child::before {
        content: "";
        position: absolute;
        top: 12px; bottom: 12px; left: 12px; right: 12px;
        pointer-events: none;
        z-index: 3;
        background:
            linear-gradient(to right,  rgba(255,255,255,0.5) 20px, transparent 20px) top left    / 20px 2px no-repeat,
            linear-gradient(to bottom, rgba(255,255,255,0.5) 20px, transparent 20px) top left    / 2px 20px no-repeat,
            linear-gradient(to left,   rgba(255,255,255,0.5) 20px, transparent 20px) top right   / 20px 2px no-repeat,
            linear-gradient(to bottom, rgba(255,255,255,0.5) 20px, transparent 20px) top right   / 2px 20px no-repeat,
            linear-gradient(to right,  rgba(255,255,255,0.5) 20px, transparent 20px) bottom left / 20px 2px no-repeat,
            linear-gradient(to top,    rgba(255,255,255,0.5) 20px, transparent 20px) bottom left / 2px 20px no-repeat,
            linear-gradient(to left,   rgba(255,255,255,0.5) 20px, transparent 20px) bottom right/ 20px 2px no-repeat,
            linear-gradient(to top,    rgba(255,255,255,0.5) 20px, transparent 20px) bottom right/ 2px 20px no-repeat;
    }

    /* Shutter button */
    [data-testid="stCameraInput"] button {
        width: 72px !important;
        height: 72px !important;
        border-radius: 50% !important;
        border: 4px solid #a89de8 !important;
        background: #ffffff !important;
        color: transparent !important;
        font-size: 0 !important;
        padding: 0 !important;
        margin: 14px auto 6px !important;
        display: block !important;
        box-shadow: 0 4px 20px rgba(123,111,212,0.35) !important;
        transition: transform 0.12s ease !important;
        position: relative !important;
    }
    [data-testid="stCameraInput"] button:active { transform: scale(0.92) !important; }
    [data-testid="stCameraInput"] button::before {
        content: "";
        position: absolute;
        top: 50%; left: 50%;
        transform: translate(-50%, -50%);
        width: 52px; height: 52px;
        border-radius: 50%;
        background: linear-gradient(135deg, #7b6fd4, #5a4fb0);
    }

    /* Loader card */
    .nq-loader-card {
        background: #ffffff; border-radius: 24px; padding: 28px 20px;
        text-align: center; box-shadow: 0 10px 28px rgba(91,71,180,0.15);
        margin: 20px auto; max-width: 100%;
    }
    .nq-loader-emoji {
        font-size: 60px;
        animation: nq-loader-bounce 1.4s ease-in-out infinite;
        display: inline-block;
    }
    @keyframes nq-loader-bounce {
        0%,100% { transform: translateY(0) rotate(-6deg); }
        50%     { transform: translateY(-10px) rotate(6deg); }
    }
    .nq-loader-text { font-size: 20px; font-weight: 800; color: #4a3ea0; margin-top: 12px; }
    .nq-loader-bar {
        margin: 16px auto 0; height: 9px; width: 85%; max-width: 320px;
        background: #e9e5fa; border-radius: 999px; overflow: hidden; position: relative;
    }
    .nq-loader-bar::before {
        content: ""; position: absolute; left: -40%; top: 0; bottom: 0; width: 40%;
        background: linear-gradient(90deg, #7b6fd4, #e86fa0); border-radius: 999px;
        animation: nq-loader-slide 1.6s ease-in-out infinite;
    }
    @keyframes nq-loader-slide { 0%{ left:-40%; } 100% { left:100%; } }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="nq-header">
      <div class="nq-avatar">🐥</div>
      <span class="nq-title">📸 وقت التصوير!</span>
      <div style="width:40px;"></div>
    </div>
    """, unsafe_allow_html=True)

    captured = st.session_state.get("captured_image")
    pending = st.session_state.get("pending_capture")

    # --------- State 3: photo confirmed & processed by API ---------
    if captured:
        st.markdown('<div class="nq-instruction">'
                    '<span class="nq-instruction-icon">🎉</span>'
                    '<p class="nq-instruction-text">رائع! تعرّفت على الشيء</p>'
                    '</div>', unsafe_allow_html=True)
        st.markdown('<div class="nq-img-card">', unsafe_allow_html=True)
        st.image(captured, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

        # Mobile: primary action on its own row, back+retake side-by-side below
        if st.button("✨ تعلّم هذه الكلمة!", use_container_width=True, type="primary", key="learn_word"):
            go_to_page("results")

        col_back, col_retake = st.columns(2, gap="small")
        with col_back:
            if st.button("⬅ رجوع", use_container_width=True, key="camera_back"):
                go_to_page("characters")
        with col_retake:
            if st.button("↩️ إعادة", use_container_width=True, key="retake_after"):
                reset_prediction()
                st.session_state.pop("cam_input", None)
                st.rerun()
        return

    # --------- State 2: photo taken, awaiting user confirmation ---------
    if pending:
        st.markdown('<div class="nq-instruction">'
                    '<span class="nq-instruction-icon">👀</span>'
                    '<p class="nq-instruction-text">هل هذه الصورة جيدة؟</p>'
                    '</div>', unsafe_allow_html=True)

        st.markdown('<div class="nq-img-card">', unsafe_allow_html=True)
        st.image(pending, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

        # On phones, stack the buttons — easier to tap, no cramped columns
        confirm_clicked = st.button(
            "✅ استخدم هذه الصورة",
            use_container_width=True,
            type="primary",
            key="confirm_pic",
        )
        if st.button("🔄 صورة جديدة", use_container_width=True, key="retake_pending"):
            st.session_state.pending_capture = None
            st.session_state.pop("cam_input", None)
            st.rerun()

        if confirm_clicked:
            loader_placeholder = st.empty()
            loader_placeholder.markdown("""
            <div class="nq-loader-card">
              <div class="nq-loader-emoji">🤖</div>
              <div class="nq-loader-text">نطوق يفكر...</div>
              <div class="nq-loader-bar"></div>
            </div>
            """, unsafe_allow_html=True)

            result = segment_image(("capture.jpg", pending, "image/jpeg"))
            loader_placeholder.empty()

            if "error" in result:
                st.error(result["error"])
            else:
                apply_segmentation_result(pending, "capture.jpg", result)
                st.session_state.pending_capture = None
                st.session_state.pop("cam_input", None)
                st.rerun()
        return

    # --------- State 1: live camera ---------
    st.markdown(
        '<div class="nq-instruction">'
        '<span class="nq-instruction-icon">🎯</span>'
        '<p class="nq-instruction-text">ضع الشيء داخل المربع المضيء ثم اضغطي على الزر البنفسجي</p>'
        '</div>',
        unsafe_allow_html=True,
    )

    cam_shot = st.camera_input("التقط صورة", label_visibility="collapsed", key="cam_input")

    if cam_shot is not None:
        cropped_bytes = _center_square_crop(cam_shot.getvalue())
        st.session_state.pending_capture = cropped_bytes
        st.rerun()

    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
    if st.button("⬅ رجوع", use_container_width=True, key="camera_back_empty"):
        go_to_page("characters")

# =============================
# Results page
# =============================
def to_eastern(n: int) -> str:
    return str(n).translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩"))


def show_results_page():
    show_selected_character_badge()
    st.markdown("""
    <div class="nq-header">
      <div class="nq-avatar">🐥</div>
      <span class="nq-title">✨ تعلّمت كلمة جديدة!</span>
      <div style="width:40px;"></div>
    </div>
    """, unsafe_allow_html=True)

    captured = st.session_state.get("captured_image")
    annotated = st.session_state.get("annotated_image")
    word = st.session_state.get("predicted_label", "غير معروف")
    conf = st.session_state.get("predicted_conf", "0٪")
    coverage = st.session_state.get("predicted_coverage", 0.0)
    audio_word = st.session_state.get("audio_word")
    audio_combined = st.session_state.get("audio_combined")
    audio_letters = st.session_state.get("audio_letters", [])

    # --- Image card
    st.markdown('<div class="nq-img-card">', unsafe_allow_html=True)
    show_seg = st.toggle("عرض الصورة مع تمييز الجزء المكتشف", value=True, key="show_seg_toggle")
    if show_seg and annotated:
        st.image(annotated, use_container_width=True)
    elif captured:
        st.image(captured, use_container_width=True)
    else:
        st.markdown("""
        <div class="nq-img-placeholder">
          <div style="font-size:48px">🖼️</div>
          <span>الصورة الملتقطة تظهر هنا</span>
        </div>
        """, unsafe_allow_html=True)
    st.markdown(f'<div class="nq-seg-badge">✓ تم التعرف ({coverage:.1f}%)</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # --- Word card with animated wave bars
    st.markdown(f"""
    <div class="nq-word-card">
      <div class="word-lbl">تعرّفت على:</div>
      <div class="word-row">
        <div class="word-left">
          <div class="word-arabic">{word}</div>
        </div>
        <div class="conf-pill">{conf}</div>
      </div>
      <div class="audio-lbl">🔊 استمع للكلمة</div>
      <div class="audio-row">
        <div class="audio-wave">
          <div class="wbar"></div><div class="wbar"></div><div class="wbar"></div>
          <div class="wbar"></div><div class="wbar"></div><div class="wbar"></div>
          <div class="wbar"></div><div class="wbar"></div><div class="wbar"></div>
          <div class="wbar"></div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # --- Main audio
    main_audio = audio_combined or audio_word
    if main_audio:
        st.audio(_decode_data_uri(main_audio), format="audio/mp3")
    else:
        st.info("🔇 لم يتوفر صوت لهذه الكلمة")

    # --- Spelling bubbles with staggered entrance
    letters = st.session_state.get("predicted_spelling", []) or list(word)
    bubbles = "".join(
        f'<div class="spell-bubble" style="animation-delay:{i*0.07:.2f}s">'
        f'<span>{ch}</span><span class="ltr-num">{to_eastern(i + 1)}</span>'
        f'</div>'
        for i, ch in enumerate(letters)
    )
    st.markdown(f"""
    <div class="nq-spell-card">
      <div class="spell-hdr">
        <span class="spell-hdr-icon">🔤</span>
        <span class="spell-hdr-lbl">كيف تُكتب؟</span>
      </div>
      <div class="spell-bubbles">{bubbles}</div>
      <div class="spell-hint">استمع لكل حرف بالترتيب</div>
    </div>
    """, unsafe_allow_html=True)

    # --- Per-letter audio: 3 per row on phones (was up to 6 — too cramped)
    if audio_letters:
        per_row = 3
        for row_start in range(0, len(audio_letters), per_row):
            row_items = audio_letters[row_start:row_start + per_row]
            cols = st.columns(per_row)
            for i, item in enumerate(row_items):
                with cols[i]:
                    st.markdown(
                        f"<div style='text-align:center;font-size:24px;font-weight:900;color:#18264a'>"
                        f"{item.get('letter','')}</div>",
                        unsafe_allow_html=True,
                    )
                    audio_data = _decode_data_uri(item.get("audio", ""))
                    if audio_data:
                        st.audio(audio_data, format="audio/mp3")

    # Action buttons: primary on its own row, secondary side-by-side
    if st.button("⭐ احفظ الكلمة", use_container_width=True, type="primary", key="save_word"):
        st.success("✅ تم الحفظ!")

    col_back, col_again = st.columns(2, gap="small")
    with col_back:
        if st.button("⬅ رجوع", use_container_width=True, key="results_back"):
            go_to_page("camera")
    with col_again:
        if st.button("📷 صورة أخرى", use_container_width=True, key="capture_again"):
            reset_prediction()
            go_to_page("camera")

# =============================
# Router
# =============================
page = st.session_state.current_page
if page == "welcome":
    show_welcome_page()
elif page == "characters":
    show_character_page()
elif page == "camera":
    show_camera_page()
else:
    show_results_page()