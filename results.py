import streamlit as st
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from styles import SHARED_CSS

st.set_page_config(
    page_title="نطوق – النتيجة",
    page_icon="✨",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown(SHARED_CSS, unsafe_allow_html=True)

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="nq-header">
  <div class="nq-avatar">🐥</div>
  <span class="nq-title">✨ تعلّمت كلمة جديدة!</span>
  <div class="nq-back">›</div>
</div>
""", unsafe_allow_html=True)

# ── Image card ────────────────────────────────────────────────────────────────
captured = st.session_state.get("captured_image")

st.markdown('<div class="nq-img-card">', unsafe_allow_html=True)
if captured:
    st.image(captured, use_container_width=True)
else:
    st.markdown("""
    <div class="nq-img-placeholder">
      <div style="font-size:clamp(36px,8vw,56px)">🖼️</div>
      <span>الصورة الملتقطة تظهر هنا</span>
    </div>
    """, unsafe_allow_html=True)
st.markdown('<div class="nq-seg-badge">✓ تم التعرف</div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

# ── Word card ─────────────────────────────────────────────────────────────────
st.markdown("""
<div class="nq-word-card">
  <div class="word-lbl">تعرّفت على:</div>
  <div class="word-row">
    <div class="word-left">
      <div class="word-emoji">👤</div>
      <div class="word-arabic">شخص</div>
    </div>
    <div class="conf-pill">٩٤٪</div>
  </div>
  <div class="audio-lbl">🔊 استمع للكلمة</div>
  <div class="audio-row">
    <div class="audio-time">0:00</div>
    <div class="audio-wave">
      <div class="wbar"></div><div class="wbar"></div><div class="wbar"></div>
      <div class="wbar"></div><div class="wbar"></div><div class="wbar"></div>
      <div class="wbar"></div><div class="wbar"></div><div class="wbar"></div>
      <div class="wbar"></div>
    </div>
    <div class="play-btn">▶</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Spelling card ─────────────────────────────────────────────────────────────
def to_eastern(n: int) -> str:
    return str(n).translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩"))

word    = "شخص"
letters = list(word)
bubbles = "".join(
    f'<div class="spell-bubble">'
    f'  <span>{ch}</span>'
    f'  <span class="ltr-num">{to_eastern(i + 1)}</span>'
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
  <div class="spell-hint">اضغط على أي حرف لسماعه</div>
</div>
""", unsafe_allow_html=True)

# ── Bottom buttons (decorative + functional) ──────────────────────────────────
st.markdown("""
<div class="nq-pink-btn">📷 التقط صورة أخرى!</div>
<div class="nq-outline-btn">⭐ احفظ هذه الكلمة</div>
<br>
""", unsafe_allow_html=True)

col1, col2 = st.columns(2)
with col1:
    if st.button("📷 التقط صورة أخرى", use_container_width=True):
        st.switch_page("camera_page.py")
with col2:
    if st.button("⭐ احفظ الكلمة", use_container_width=True, type="primary"):
        st.success("✅ تم الحفظ!")
