import streamlit as st
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from styles import SHARED_CSS

st.set_page_config(
    page_title="نطوق – الكاميرا",
    page_icon="📸",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown(SHARED_CSS, unsafe_allow_html=True)

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="nq-header">
  <div class="nq-avatar">🐥</div>
  <span class="nq-title">📸 وقت التصوير!</span>
  <div class="nq-back">›</div>
</div>
""", unsafe_allow_html=True)

# ── Instruction strip ─────────────────────────────────────────────────────────
captured = st.session_state.get("captured_image")
instr = "رائع! 🎉 هل تريد تعلّم اسم هذا الشيء؟" if captured else "ضع الشيء داخل المربع المضيء ثم التقط الصورة"

st.markdown(f"""
<div class="nq-instruction">
  <span class="nq-instruction-icon">🎯</span>
  <p class="nq-instruction-text">{instr}</p>
</div>
""", unsafe_allow_html=True)

# ── Camera frame OR captured preview ─────────────────────────────────────────
if captured:
    # Show captured image inside a styled card
    st.markdown('<div class="nq-img-card">', unsafe_allow_html=True)
    st.image(captured, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)
else:
    # Static camera frame with glowing guide square + error state
    st.markdown("""
    <div class="nq-cam-frame">
      <div class="cam-dots"></div>
      <div class="cc tl"></div><div class="cc tr"></div>
      <div class="cc bl"></div><div class="cc br"></div>
      <div class="guide-sq">
        <span class="guide-lbl">ضع الشيء هنا</span>
      </div>
      <div class="cam-error">
        <div class="cam-error-icon">📷</div>
        <div class="cam-error-text">لم نتمكن من فتح الكاميرا<br>تأكد من إذن الكاميرا</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

# ── File uploader (gallery replacement) ──────────────────────────────────────
uploaded = st.file_uploader(
    "اختر صورة من جهازك 🖼️",
    type=["jpg", "jpeg", "png", "webp"],
    label_visibility="visible",
)
if uploaded:
    data = uploaded.read()
    st.session_state["captured_image"] = data
    st.session_state["captured_name"]  = uploaded.name
    st.rerun()

# ── Shutter controls row (decorative) ────────────────────────────────────────
st.markdown("""
<div class="nq-controls">
  <div class="icon-btn">🔄</div>
  <div class="shutter"><div class="shutter-inner"></div></div>
  <div class="icon-btn">🖼️</div>
</div>
""", unsafe_allow_html=True)

# ── Learn / Retake buttons ────────────────────────────────────────────────────
if captured:
    col1, col2 = st.columns([3, 1])
    with col1:
        if st.button("✨ تعلّم هذه الكلمة!", use_container_width=True, type="primary"):
            st.switch_page("result_page.py")
    with col2:
        if st.button("↩️ إعادة", use_container_width=True):
            del st.session_state["captured_image"]
            st.rerun()
else:
    st.markdown("""
    <div class="nq-learn-btn" style="opacity:0.45">
      <div class="nq-learn-icon">✨</div>
      تعلّم هذه الكلمة!
    </div>
    """, unsafe_allow_html=True)
