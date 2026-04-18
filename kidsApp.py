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
# (change this one line if your Railway domain changes)
# =============================
API_URL = "https://interactive-educational-application-production.up.railway.app"

# =============================
# Session State
# =============================
if "selected_character" not in st.session_state:
    st.session_state.selected_character = ""
if "current_page" not in st.session_state:
    st.session_state.current_page = "welcome"
if "captured_image" not in st.session_state:
    st.session_state.captured_image = None          # original image bytes (what the user uploaded)
if "captured_name" not in st.session_state:
    st.session_state.captured_name = ""
if "annotated_image" not in st.session_state:
    st.session_state.annotated_image = None         # raw PNG bytes with masks + Arabic label burned in
if "predicted_label" not in st.session_state:
    st.session_state.predicted_label = ""
if "predicted_label_en" not in st.session_state:
    st.session_state.predicted_label_en = ""
if "predicted_conf" not in st.session_state:
    st.session_state.predicted_conf = ""
if "predicted_coverage" not in st.session_state:
    st.session_state.predicted_coverage = 0.0
if "predicted_spelling" not in st.session_state:
    st.session_state.predicted_spelling = []
if "audio_word" not in st.session_state:
    st.session_state.audio_word = None              # data URI string
if "audio_letters" not in st.session_state:
    st.session_state.audio_letters = []             # list of {letter, audio}
if "audio_combined" not in st.session_state:
    st.session_state.audio_combined = None          # word → spelling → word, as one track
if "pending_capture" not in st.session_state:
    st.session_state.pending_capture = None         # image bytes awaiting ✅/🔄 confirmation

# =============================
# API helpers
# =============================
def _decode_data_uri(data_uri: str) -> bytes:
    """Turn 'data:audio/mp3;base64,...' (or image equivalent) into raw bytes."""
    if not data_uri or "," not in data_uri:
        return b""
    try:
        return base64.b64decode(data_uri.split(",", 1)[1])
    except Exception:
        return b""


def _center_square_crop(image_bytes: bytes, guide_ratio: float = 0.62) -> bytes:
    """
    Crop the captured image to a centered square matching the on-screen guide.
    Mirrors the reference HTML: the guide square covers `guide_ratio` (default 62%)
    of the shorter frame side, centered. This is what the user visually frames
    inside the pulsing purple square, so we cut exactly that out.
    Returns JPEG bytes. Falls back to the original if PIL fails.
    """
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
    """Ping the backend so we can show status before the user wastes a capture."""
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
    """
    Send an image to /segment. Accepts:
      - a Streamlit UploadedFile (file_uploader or camera_input)
      - raw bytes
    Returns the parsed JSON response, or {"error": "..."} on failure.
    """
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
        # YOLO on CPU + TTS calls can take a while on Railway's free tier
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
    """Copy the fields from the API response into session state."""
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


def get_character_emoji() -> str:
    """Match kidsApp: 👧 for girl, 🧒 for boy, default 🐥 if nothing picked."""
    c = st.session_state.get("selected_character", "")
    if c == "بنت":
        return "👧"
    if c == "ولد":
        return "🧒"
    return "🐥"


# =============================
# Shared CSS
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

.main .block-container {
  max-width: 430px !important;
  width: 100% !important;
  margin: 0 auto !important;
  padding: 16px 14px 42px !important;
  animation: fadePage 0.55s ease;
}

@keyframes fadePage {
  from {opacity: 0; transform: translateY(16px);}
  to {opacity: 1; transform: translateY(0);}
}

@keyframes floatImage {
  0% {transform: translateY(0px);}
  50% {transform: translateY(-12px);}
  100% {transform: translateY(0px);}
}

.blob-bg { position:fixed; inset:0; pointer-events:none; z-index:0; overflow:hidden; }
.blob { position:absolute; border-radius:50%; filter:blur(55px); opacity:0.30; }
.blob-1 { width:240px; height:240px; background:#c3b8f5; top:-8%; left:-4%; }
.blob-2 { width:180px; height:180px; background:#f5c8e8; bottom:4%; right:-4%; }
.blob-3 { width:140px; height:140px; background:#b8f0e8; top:40%; right:-2%; opacity:0.18; }

.welcome-title {
    font-size: 72px;
    font-weight: 900;
    color: #18264a;
    margin-top: 10px;
    margin-bottom: 12px;
    text-align: right;
    line-height: 1.1;
}
.welcome-subtitle {
    font-size: 30px;
    font-weight: 800;
    color: #6d7792;
    margin-bottom: 18px;
    text-align: right;
}
.welcome-desc {
    font-size: 24px;
    color: #7a849f;
    line-height: 2;
    text-align: right;
    margin-bottom: 22px;
}
.main-title {
    font-size: 64px;
    font-weight: 900;
    line-height: 1.15;
    color: #18264a;
    margin-bottom: 18px;
    text-align: right;
}
.highlight {
    background: linear-gradient(90deg, #d9ccff, #c7e3ff);
    color: #6d4cff;
    padding: 6px 16px;
    border-radius: 16px;
}
.sub-text {
    font-size: 22px;
    color: #6b7690;
    line-height: 1.9;
    margin-bottom: 20px;
    text-align: right;
}
.pill {
    display: inline-block;
    background: rgba(255,255,255,0.98);
    padding: 12px 20px;
    border-radius: 999px;
    margin-left: 10px;
    margin-bottom: 10px;
    font-weight: 800;
    color: #667089;
    box-shadow: 0 6px 16px rgba(0,0,0,0.05);
    font-size: 18px;
}
.message-box {
    background: #f2d8a4;
    color: #5f462f;
    border-radius: 24px;
    padding: 18px;
    text-align: center;
    font-size: 24px;
    font-weight: 800;
    margin-top: 20px;
    margin-bottom: 15px;
}
.note {
    text-align: center;
    color: #7b85a1;
    font-size: 17px;
    margin-top: 10px;
}
.section-title {
    text-align: center;
    font-size: 34px;
    font-weight: 900;
    color: #1b2a4c;
    margin-bottom: 20px;
}

.card:hover {
    transform: translateY(-4px);
    box-shadow: 0 16px 28px rgba(42,58,95,0.12);
}

.img-box-girl {
    background: #efd7ee;
    border-radius: 24px;
    padding: 20px;
    margin-bottom: 18px;
}
.img-box-boy {
    background: #dbeaf7;
    border-radius: 24px;
    padding: 20px;
    margin-bottom: 18px;
}
.char-name {
    font-size: 30px;
    font-weight: 900;
    color: #18264a;
    margin-top: 10px;
    margin-bottom: 10px;
    text-align: center;
}
.char-desc {
    font-size: 18px;
    color: #6d7792;
    line-height: 1.9;
    min-height: 120px;
    text-align: center;
}
.floating-image {
    animation: floatImage 3.5s ease-in-out infinite;
    filter: drop-shadow(0 20px 28px rgba(0, 0, 0, 0.10));
    margin-top: 90px;
}

.nq-header {
  display:flex; align-items:center; justify-content:space-between;
  padding:12px 0 16px;
}
.nq-title {
  font-size:22px; font-weight:800; color:var(--text-dark); text-align:center; flex:1;
}
.nq-avatar {
  width:44px; height:44px; border-radius:50%;
  background:linear-gradient(135deg,#c3b8f5,#f5c8e8);
  display:flex; align-items:center; justify-content:center; font-size:24px; flex-shrink:0;
}
.nq-back {
  width:44px; height:44px; border-radius:50%; background:var(--white);
  display:flex; align-items:center; justify-content:center;
  box-shadow:0 2px 12px rgba(123,111,212,0.18);
  font-size:22px; color:var(--purple); font-weight:900; flex-shrink:0;
}
.nq-instruction {
  background:var(--white); border-radius:20px; padding:12px 18px;
  display:flex; align-items:center; gap:12px; box-shadow:0 2px 14px rgba(123,111,212,0.10);
  margin-bottom:18px; direction:rtl;
}
.nq-instruction-icon { font-size:26px; flex-shrink:0; }
.nq-instruction-text { font-size:15px; font-weight:500; color:var(--text-mid); line-height:1.5; }
.nq-cam-frame {
  width:100%; aspect-ratio:3/4; border-radius:30px; overflow:hidden; position:relative;
  background:#1a1a2e; box-shadow:0 8px 40px rgba(91,71,180,0.28); margin-bottom:18px;
}
.cc { position:absolute; width:22px; height:22px; border-color:rgba(255,255,255,0.45); border-style:solid; }
.cc.tl { top:14px; right:14px; border-width:2px 0 0 2px; }
.cc.tr { top:14px; left:14px;  border-width:2px 2px 0 0; }
.cc.bl { bottom:14px; right:14px; border-width:0 0 2px 2px; }
.cc.br { bottom:14px; left:14px;  border-width:0 2px 2px 0; }
.cam-dots {
  position:absolute; inset:0; background-image:radial-gradient(rgba(160,140,255,0.07) 1px,transparent 1px);
  background-size:26px 26px;
}
.guide-sq {
  position:absolute; top:50%; left:50%; transform:translate(-50%,-50%);
  width:62%; aspect-ratio:1; border-radius:22px; border:2.5px solid rgba(200,185,255,0.9);
  animation:glow-pulse 2.2s ease-in-out infinite;
}
.guide-lbl {
  position:absolute; bottom:-24px; left:50%; transform:translateX(-50%);
  font-size:13px; font-weight:600; color:rgba(210,200,255,0.9); white-space:nowrap;
}
@keyframes glow-pulse {
  0%,100% { box-shadow:0 0 0 3px rgba(160,140,255,0.18),0 0 18px 4px rgba(160,140,255,0.32),inset 0 0 18px 2px rgba(160,140,255,0.08); }
  50%      { box-shadow:0 0 0 5px rgba(160,140,255,0.32),0 0 32px 10px rgba(160,140,255,0.50),inset 0 0 24px 6px rgba(160,140,255,0.18); }
}
.cam-error {
  position:absolute; inset:0; background:rgba(20,18,48,0.92); display:flex; flex-direction:column;
  align-items:center; justify-content:center; gap:14px; text-align:center; padding:28px; border-radius:inherit;
}
.cam-error-icon { font-size:52px; }
.cam-error-text { font-size:15px; font-weight:600; color:rgba(200,185,255,0.9); line-height:1.5; }
.nq-controls { display:flex; align-items:center; justify-content:center; gap:36px; margin-bottom:16px; }
.icon-btn {
  width:50px; height:50px; border-radius:50%; background:rgba(255,255,255,0.82);
  display:flex; align-items:center; justify-content:center; font-size:24px; box-shadow:0 2px 12px rgba(123,111,212,0.13);
}
.shutter {
  width:76px; height:76px; border-radius:50%; background:var(--white); border:5px solid var(--purple-light);
  display:flex; align-items:center; justify-content:center; box-shadow:0 4px 22px rgba(123,111,212,0.32);
}
.shutter-inner {
  width:56px; height:56px; border-radius:50%; background:linear-gradient(135deg,var(--purple),var(--purple-dark));
}
.nq-learn-btn {
  display:flex; align-items:center; justify-content:center; gap:12px; width:100%; padding:18px;
  border-radius:24px; background:linear-gradient(135deg,var(--btn-blue),var(--btn-blue-dark));
  color:white; font-size:19px; font-weight:800; box-shadow:0 5px 22px rgba(91,141,232,0.42);
  margin-bottom:12px;
}
.nq-learn-icon {
  width:30px; height:30px; background:rgba(255,255,255,0.24); border-radius:50%;
  display:flex; align-items:center; justify-content:center; font-size:17px;
}
.nq-img-card {
  width:100%; border-radius:28px; overflow:hidden; position:relative;
  box-shadow:0 6px 32px rgba(91,71,180,0.18); margin-bottom:16px;
}
.nq-img-placeholder {
  width:100%; aspect-ratio:4/3; background:linear-gradient(135deg,#e8e4fc,#f5e8f8);
  display:flex; flex-direction:column; align-items:center; justify-content:center; gap:10px; color:var(--text-mid);
  font-size:15px; font-weight:500;
}
.nq-seg-badge {
  position:absolute; top:14px; right:14px; background:rgba(76,175,125,0.92); color:white;
  font-size:13px; font-weight:700; padding:6px 14px; border-radius:20px;
}
.nq-word-card, .nq-spell-card {
  background:var(--white); border-radius:28px; box-shadow:var(--card-shadow); padding:22px; margin-bottom:16px;
  position:relative; overflow:hidden; direction:rtl;
}
.nq-word-card::before {
  content:''; position:absolute; top:0; right:0; width:90px; height:90px;
  background:linear-gradient(135deg,rgba(195,184,245,0.28),transparent); border-radius:0 28px 0 90px;
}
.word-lbl, .audio-lbl, .spell-hdr-lbl, .spell-hint {
  font-size:14px; font-weight:600; color:var(--text-mid);
}
.word-row { display:flex; align-items:center; justify-content:space-between; gap:14px; margin-bottom:18px; }
.word-left { display:flex; align-items:center; gap:16px; }
.word-emoji { font-size:48px; }
.word-arabic { font-size:40px; font-weight:900; color:var(--text-dark); }
.conf-pill {
  background:linear-gradient(135deg,#eaf7f0,#d4f0e4); color:#2e7d5a; font-size:14px; font-weight:700;
  padding:8px 16px; border-radius:20px; flex-shrink:0;
}
.audio-row { display:flex; align-items:center; gap:14px; }
.play-btn {
  width:56px; height:56px; border-radius:50%; flex-shrink:0; background:linear-gradient(135deg,var(--purple),var(--purple-dark));
  display:flex; align-items:center; justify-content:center; box-shadow:0 4px 18px rgba(123,111,212,0.38); color:white; font-size:20px;
}
.audio-wave { flex:1; display:flex; align-items:center; gap:5px; height:42px; }
.wbar { flex:1; background:var(--purple-light); border-radius:3px; opacity:0.5; }
.wbar:nth-child(1){height:20%} .wbar:nth-child(2){height:50%} .wbar:nth-child(3){height:80%} .wbar:nth-child(4){height:40%}
.wbar:nth-child(5){height:70%} .wbar:nth-child(6){height:55%} .wbar:nth-child(7){height:30%} .wbar:nth-child(8){height:65%}
.wbar:nth-child(9){height:45%} .wbar:nth-child(10){height:25%}
.audio-time { font-size:14px; color:var(--text-mid); font-weight:600; min-width:40px; text-align:left; }
.spell-hdr { display:flex; align-items:center; gap:10px; margin-bottom:14px; }
.spell-bubbles { display:flex; flex-wrap:wrap; gap:10px; flex-direction:row; justify-content:flex-end; margin-bottom:12px; }
.spell-bubble {
  width:52px; height:56px; border-radius:16px; background:linear-gradient(145deg,#ede9fc,#ddd5f8);
  border:1.5px solid rgba(123,111,212,0.17); display:flex; flex-direction:column; align-items:center; justify-content:center;
  gap:2px; font-size:24px; font-weight:900; color:var(--purple-dark); box-shadow:0 3px 10px rgba(91,71,180,0.10);
}
.ltr-num { font-size:10px; font-weight:600; color:var(--purple-light); line-height:1; }
.nq-pink-btn, .nq-outline-btn {
  display:flex; align-items:center; justify-content:center; gap:12px; width:100%; text-align:center; border-radius:24px;
}
.nq-pink-btn {
  padding:18px; background:linear-gradient(135deg,var(--btn-pink),var(--btn-pink-dark)); color:white; font-size:19px; font-weight:800;
  box-shadow:0 5px 20px rgba(232,111,160,0.38); margin-bottom:12px;
}
.nq-outline-btn {
  padding:15px; background:var(--white); border:1.5px solid var(--purple-light); color:var(--purple); font-size:16px; font-weight:700;
}
[data-testid="stFileUploaderDropzone"] {
  border:1.5px dashed var(--purple-light) !important; border-radius:16px !important; background:rgba(255,255,255,0.6) !important;
}
/* الأزرار رجعتها أقرب للشكل القديم */
div.stButton > button {
  width: 100%;
  border: none;
  border-radius: 18px;
  padding: 0.85rem 1rem;
  font-size: 18px;
  font-weight: 800;
  color: white;
  background: linear-gradient(135deg, #745cff, #4d96ff);
  box-shadow: 0 12px 24px rgba(91,110,255,0.24);
  transition: 0.18s ease;
}
.selected-avatar-badge {
  position: fixed;
  top: 14px;
  left: 14px;
  width: 64px;
  height: 64px;
  border-radius: 50%;
  background: #ffffff;
  box-shadow: 0 8px 20px rgba(91,71,180,0.20);
  padding: 4px;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
}

.selected-avatar-badge img {
  width: 100%;
  height: 100%;
  border-radius: 50%;
  object-fit: cover;
}

.welcome-title {
  font-size: 42px;
  text-align: center;
}

.welcome-subtitle {
  font-size: 22px;
  text-align: center;
}

.welcome-desc {
  font-size: 18px;
  text-align: center;
  line-height: 1.9;
}

.main-title {
  font-size: 34px;
  text-align: center;
}

.sub-text {
  font-size: 17px;
  text-align: center;
}

.section-title {
  font-size: 24px;
}

.pill {
  font-size: 15px;
  padding: 10px 16px;
}

.message-box {
  font-size: 18px;
  padding: 14px;
}

.char-name {
    font-size: 20px;
    font-weight: 900;
    color: #18264a;
    margin: 8px 0;
    text-align: center;
}

.char-desc {
    font-size: 14px;
    color: #6d7792;
    line-height: 1.7;
    text-align: center;
    margin-bottom: 10px;
}

.start-btn {
  max-width: 200px;
  margin: 20px auto 0 auto;
}

.back-btn {
  max-width: 140px;
  margin-bottom: 14px;
}

div.stButton > button {
  border-radius: 16px;
  padding: 0.8rem 1rem;
  font-size: 16px;
}
div.stButton > button:hover { transform: translateY(-2px); }
.start-btn { max-width: 220px; margin: 28px auto 0 auto; }
.back-btn { max-width: 170px; margin-bottom: 20px; }
[data-testid="stImage"] img { border-radius:22px; box-shadow:0 4px 20px rgba(91,71,180,0.14); }
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
        st.image(logo_path, width=190)
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
# Camera page
# =============================

def show_camera_page():
    show_selected_character_badge()
    # Camera page styling from kidsApp.py (mobile-friendly preview + guide square + shutter)
    st.markdown("""
    <style>
    /* Dark frame = the camera widget itself */
    [data-testid="stCameraInput"] {
        position: relative !important;
        background: #1a1a2e !important;
        border-radius: 28px !important;
        box-shadow: 0 8px 32px rgba(91,71,180,0.30) !important;
        padding: 12px !important;
        max-width: 460px !important;
        margin: 0 auto 12px !important;
        overflow: hidden !important;
    }

    /* The inner wrapper around the video — force 3:4 block */
    [data-testid="stCameraInput"] > div:first-child {
        width: 100% !important;
        aspect-ratio: 3 / 4 !important;
        position: relative !important;
        border-radius: 20px !important;
        overflow: hidden !important;
        background: #000 !important;
    }

    /* Make video + captured still actually FILL the frame (fixes the tiny preview) */
    [data-testid="stCameraInput"] video,
    [data-testid="stCameraInput"] img {
        position: absolute !important;
        inset: 0 !important;
        width: 100% !important;
        height: 100% !important;
        object-fit: cover !important;
        border-radius: 20px !important;
        display: block !important;
    }

    /* ==== CORNER MARKS (four L-shaped corners on the inside) ==== */
    [data-testid="stCameraInput"]::before {
        content: "";
        position: absolute;
        top: 22px; left: 22px; right: 22px; bottom: 90px;
        pointer-events: none;
        z-index: 4;
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

    /* ==== GLOWING GUIDE SQUARE — centered over the video area ==== */
    [data-testid="stCameraInput"]::after {
        content: "ضع الشيء هنا";
        position: absolute;
        top: calc(50% - 45px);
        left: 50%;
        transform: translate(-50%, -50%);
        width: 52%;
        aspect-ratio: 1;
        border-radius: 22px;
        border: 2.5px solid rgba(200,185,255,0.9);
        pointer-events: none;
        z-index: 5;
        animation: nq-glow-pulse 2.2s ease-in-out infinite;
        display: flex;
        align-items: flex-end;
        justify-content: center;
        padding-bottom: 8px;
        font-family: 'Tajawal', sans-serif;
        font-size: 13px;
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

    /* Primary shutter button */
    [data-testid="stCameraInput"] button[kind="primary"],
    [data-testid="stCameraInput"] button[kind="primaryFormSubmit"],
    [data-testid="stCameraInput"] > div > button:first-of-type {
        width: 72px !important;
        height: 72px !important;
        min-width: 72px !important;
        max-width: 72px !important;
        border-radius: 50% !important;
        border: 5px solid #a89de8 !important;
        background: #ffffff !important;
        color: transparent !important;
        font-size: 0 !important;
        padding: 0 !important;
        margin: 14px auto 6px !important;
        display: block !important;
        box-shadow: 0 4px 22px rgba(123,111,212,0.38) !important;
        transition: transform 0.12s ease !important;
        position: relative !important;
    }
    [data-testid="stCameraInput"] button[kind="primary"]:active,
    [data-testid="stCameraInput"] button[kind="primaryFormSubmit"]:active,
    [data-testid="stCameraInput"] > div > button:first-of-type:active {
        transform: scale(0.92) !important;
    }
    [data-testid="stCameraInput"] button[kind="primary"]::before,
    [data-testid="stCameraInput"] button[kind="primaryFormSubmit"]::before,
    [data-testid="stCameraInput"] > div > button:first-of-type::before {
        content: "";
        position: absolute;
        top: 50%; left: 50%;
        transform: translate(-50%, -50%);
        width: 52px; height: 52px;
        border-radius: 50%;
        background: linear-gradient(135deg, #7b6fd4, #5a4fb0);
    }

    /* Switch camera / clear — subtle, not a second shutter */
    [data-testid="stCameraInput"] button:not([kind="primary"]):not([kind="primaryFormSubmit"]):not(:first-of-type) {
        width: auto !important;
        height: 32px !important;
        min-width: auto !important;
        max-width: none !important;
        background: rgba(255,255,255,0.12) !important;
        color: rgba(255,255,255,0.8) !important;
        border: none !important;
        border-radius: 10px !important;
        font-size: 12px !important;
        font-weight: 600 !important;
        padding: 4px 12px !important;
        margin: 6px auto !important;
        box-shadow: none !important;
        display: inline-flex !important;
    }
    [data-testid="stCameraInput"] button:not([kind="primary"]):not([kind="primaryFormSubmit"]):not(:first-of-type)::before {
        display: none !important;
    }

    [data-testid="stCameraInput"] label,
    [data-testid="stCameraInput"] [data-testid="stWidgetLabel"] {
        display: none !important;
    }

    /* Loader card during API call */
    .nq-loader-card {
        background: #ffffff; border-radius: 28px; padding: 36px 24px;
        text-align: center; box-shadow: 0 10px 32px rgba(91,71,180,0.15);
        margin: 24px auto; max-width: 520px;
    }
    .nq-loader-emoji {
        font-size: 72px;
        animation: nq-loader-bounce 1.4s ease-in-out infinite;
        display: inline-block;
    }
    @keyframes nq-loader-bounce {
        0%,100% { transform: translateY(0) rotate(-6deg); }
        50%     { transform: translateY(-12px) rotate(6deg); }
    }
    .nq-loader-text { font-size: 24px; font-weight: 800; color: #4a3ea0; margin-top: 16px; }
    .nq-loader-bar {
        margin: 20px auto 0; height: 10px; width: 85%; max-width: 360px;
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

    st.markdown(f"""
    <div class="nq-header">
      <div class="nq-avatar">{get_character_emoji()}</div>
      <span class="nq-title">📸 وقت التصوير!</span>
      <div style="width:44px;"></div>
    </div>
    """, unsafe_allow_html=True)

    # ========================================================================
    # STATE MACHINE:
    #   pending_capture (bytes) → confirm screen (✅ / 🔄)
    #   captured_image  (bytes) → processed by API, show next-step buttons
    #   neither                 → live camera
    # ========================================================================
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

        col1, col2, col3 = st.columns([1.1, 1.9, 1])
        with col1:
            if st.button("⬅ رجوع", use_container_width=True, key="camera_back"):
                go_to_page("characters")
        with col2:
            if st.button("✨ تعلّم هذه الكلمة!", use_container_width=True, type="primary", key="learn_word"):
                go_to_page("results")
        with col3:
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

        col_use, col_retake = st.columns(2, gap="large")
        with col_use:
            confirm_clicked = st.button(
                "✅ استخدم هذه الصورة",
                use_container_width=True,
                type="primary",
                key="confirm_pic",
            )
        with col_retake:
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

    # On snap: crop to 62% centered square (matches the visual framing) and stash as pending
    if cam_shot is not None:
        cropped_bytes = _center_square_crop(cam_shot.getvalue())
        st.session_state.pending_capture = cropped_bytes
        st.rerun()

    # Back button
    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
    if st.button("⬅ رجوع", use_container_width=True, key="camera_back_empty"):
        go_to_page("characters")

# =============================
# Results page
# =============================
def to_eastern(n: int) -> str:
    return str(n).translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩"))


def show_results_page():
    show_selected_character_badge()
    st.markdown(f"""
    <div class="nq-header">
      <div class="nq-avatar">{get_character_emoji()}</div>
      <span class="nq-title">✨ تعلّمت كلمة جديدة!</span>
      <div class="nq-back">›</div>
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

    # --- Image card: toggle between the original and the segmented version
    st.markdown('<div class="nq-img-card">', unsafe_allow_html=True)
    show_seg = st.toggle("عرض الصورة مع تمييز الجزء المكتشف", value=True, key="show_seg_toggle")
    if show_seg and annotated:
        st.image(annotated, use_container_width=True)
    elif captured:
        st.image(captured, use_container_width=True)
    else:
        st.markdown("""
        <div class="nq-img-placeholder">
          <div style="font-size:56px">🖼️</div>
          <span>الصورة الملتقطة تظهر هنا</span>
        </div>
        """, unsafe_allow_html=True)
    st.markdown(f'<div class="nq-seg-badge">✓ تم التعرف ({coverage:.1f}%)</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # --- Word card
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
    </div>
    """, unsafe_allow_html=True)

    # --- Main audio: word → letters → word, as one track
    main_audio = audio_combined or audio_word
    if main_audio:
        st.audio(_decode_data_uri(main_audio), format="audio/mp3")
    else:
        st.info("🔇 لم يتوفر صوت لهذه الكلمة")

    # --- Spelling bubbles (visual)
    letters = st.session_state.get("predicted_spelling", []) or list(word)
    bubbles = "".join(
        f'<div class="spell-bubble"><span>{ch}</span><span class="ltr-num">{to_eastern(i + 1)}</span></div>'
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

    # --- Per-letter audio (one player per letter)
    if audio_letters:
        letter_cols = st.columns(min(len(audio_letters), 6))
        for i, item in enumerate(audio_letters):
            col = letter_cols[i % len(letter_cols)]
            with col:
                st.markdown(f"<div style='text-align:center;font-size:28px;font-weight:900;color:#18264a'>{item.get('letter','')}</div>", unsafe_allow_html=True)
                audio_data = _decode_data_uri(item.get("audio", ""))
                if audio_data:
                    st.audio(audio_data, format="audio/mp3")

    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        if st.button("⬅ رجوع", use_container_width=True, key="results_back"):
            go_to_page("camera")
    with col2:
        if st.button("📷 التقط صورة أخرى", use_container_width=True, key="capture_again"):
            reset_prediction()
            go_to_page("camera")
    with col3:
        if st.button("⭐ احفظ الكلمة", use_container_width=True, type="primary", key="save_word"):
            st.success("✅ تم الحفظ!")

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