import streamlit as st
import requests

st.set_page_config(page_title="Segmentation", page_icon="🖼️")
st.title("Image Segmentation")

# Replace with your Railway URL after deployment
BACKEND_URL = "https://YOUR-APP.up.railway.app/segment"

uploaded = st.file_uploader("Upload an image", type=["jpg", "jpeg", "png"])

if uploaded:
    st.image(uploaded, caption="Input", use_container_width=True)

    if st.button("Run segmentation"):
        with st.spinner("Processing... (first request may take ~60s on cold start)"):
            try:
                r = requests.post(
                    BACKEND_URL,
                    files={"file": (uploaded.name, uploaded.getvalue(), uploaded.type)},
                    timeout=180,
                )
                if r.ok:
                    st.image(r.content, caption="Result", use_container_width=True)
                else:
                    st.error(f"Backend error {r.status_code}: {r.text[:200]}")
            except requests.Timeout:
                st.error("Request timed out. Try again — the server may have been cold.")
            except Exception as e:
                st.error(f"Error: {e}")
