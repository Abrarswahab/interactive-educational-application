"""
نطوق 🤖 - FastAPI Backend
=====================================================
خادم REST API لتطبيق التعرف على الصور للأطفال
يستخدم نموذج YOLOv11 Segmentation (best.pt)

تشغيل الخادم:
    python main.py
    أو
    uvicorn main:app --reload --host 127.0.0.1 --port 8000

المتطلبات:
    pip install fastapi uvicorn pillow numpy ultralytics
"""

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from PIL import Image
import io
import numpy as np
import os
import logging
import urllib.request
import urllib.parse

# ===================================
# إعداد السجلات
# ===================================
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("natooq")

# ===================================
# تحميل نموذج YOLO عند البدء
# ===================================
MODEL_PATH = os.path.join(os.path.dirname(__file__), "best.pt")
model = None

def load_model():
    global model
    try:
        from ultralytics import YOLO
        if not os.path.exists(MODEL_PATH):
            log.warning(f"⚠️  النموذج غير موجود في: {MODEL_PATH} — سيتم استخدام وضع التجريب")
            return
        model = YOLO(MODEL_PATH)
        log.info(f"✅ تم تحميل النموذج بنجاح: {MODEL_PATH}")
        log.info(f"   الفئات: {model.names}")
    except ImportError:
        log.error("❌ مكتبة ultralytics غير مثبتة. شغّل: pip install ultralytics")
    except Exception as e:
        log.error(f"❌ خطأ في تحميل النموذج: {e}")

load_model()

# ===================================
# إنشاء تطبيق FastAPI
# ===================================
app = FastAPI(
    title="نطوق 🤖 - API",
    description="API للتعرف على الصور بالعربية للأطفال - يعتمد YOLOv11 Segmentation",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===================================
# قاموس الترجمة: اسم الفئة (إنجليزي) → عربي + إيموجي
# ===================================
ARABIC_LABELS: dict = {
    # فواكه
    "apple":         {"label": "تفاح",        "emoji": "🍎"},
    "orange":        {"label": "برتقال",       "emoji": "🍊"},
    "banana":        {"label": "موز",          "emoji": "🍌"},
    "strawberry":    {"label": "فراولة",       "emoji": "🍓"},
    "grape":         {"label": "عنب",          "emoji": "🍇"},
    "watermelon":    {"label": "بطيخ",         "emoji": "🍉"},
    "pear":          {"label": "كمثرى",        "emoji": "🍐"},
    "peach":         {"label": "خوخ",          "emoji": "🍑"},
    "lemon":         {"label": "ليمون",        "emoji": "🍋"},
    "mango":         {"label": "مانجو",        "emoji": "🥭"},
    # حيوانات
    "cat":           {"label": "قط",           "emoji": "🐱"},
    "dog":           {"label": "كلب",          "emoji": "🐶"},
    "rabbit":        {"label": "أرنب",         "emoji": "🐰"},
    "fish":          {"label": "سمكة",         "emoji": "🐠"},
    "bird":          {"label": "طائر",         "emoji": "🐦"},
    "horse":         {"label": "حصان",         "emoji": "🐴"},
    "cow":           {"label": "بقرة",         "emoji": "🐄"},
    "sheep":         {"label": "خروف",         "emoji": "🐑"},
    "elephant":      {"label": "فيل",          "emoji": "🐘"},
    "lion":          {"label": "أسد",          "emoji": "🦁"},
    # مركبات
    "car":           {"label": "سيارة",        "emoji": "🚗"},
    "truck":         {"label": "شاحنة",        "emoji": "🚚"},
    "bus":           {"label": "باص",          "emoji": "🚌"},
    "train":         {"label": "قطار",         "emoji": "🚂"},
    "airplane":      {"label": "طائرة",        "emoji": "✈️"},
    "bicycle":       {"label": "دراجة",        "emoji": "🚲"},
    "motorcycle":    {"label": "دراجة نارية",  "emoji": "🏍️"},
    "boat":          {"label": "قارب",         "emoji": "⛵"},
    # أدوات مدرسية وألعاب
    "book":          {"label": "كتاب",         "emoji": "📚"},
    "pen":           {"label": "قلم",          "emoji": "✏️"},
    "pencil":        {"label": "قلم رصاص",     "emoji": "✏️"},
    "scissors":      {"label": "مقص",          "emoji": "✂️"},
    "ball":          {"label": "كرة",          "emoji": "⚽"},
    "teddy bear":    {"label": "دمية دب",      "emoji": "🧸"},
    "clock":         {"label": "ساعة",         "emoji": "⏰"},
    # طعام آخر
    "pizza":         {"label": "بيتزا",        "emoji": "🍕"},
    "sandwich":      {"label": "ساندوتش",      "emoji": "🥪"},
    "cake":          {"label": "كيكة",         "emoji": "🎂"},
    "bottle":        {"label": "زجاجة",        "emoji": "🍼"},
    "cup":           {"label": "كوب",          "emoji": "☕"},
    # أغراض المنزل
    "chair":         {"label": "كرسي",         "emoji": "🪑"},
    "couch":         {"label": "كنبة",         "emoji": "🛋️"},
    "bed":           {"label": "سرير",         "emoji": "🛏️"},
    "lamp":          {"label": "مصباح",        "emoji": "💡"},
    "refrigerator":  {"label": "ثلاجة",        "emoji": "🧊"},
    "tv":            {"label": "تلفاز",        "emoji": "📺"},
    "laptop":        {"label": "لابتوب",       "emoji": "💻"},
    "cell phone":    {"label": "هاتف",         "emoji": "📱"},
    "keyboard":      {"label": "لوحة مفاتيح",  "emoji": "⌨️"},
    "mouse":         {"label": "ماوس",         "emoji": "🖱️"},
    "backpack":      {"label": "حقيبة",        "emoji": "🎒"},
    "umbrella":      {"label": "مظلة",         "emoji": "☂️"},
    "hat":           {"label": "قبعة",         "emoji": "👒"},
    "shoe":          {"label": "حذاء",         "emoji": "👟"},
    # طبيعة
    "tree":          {"label": "شجرة",         "emoji": "🌳"},
    "flower":        {"label": "زهرة",         "emoji": "🌸"},
    # COCO classes شائعة في YOLO
    "person":        {"label": "شخص",          "emoji": "🧑"},
    "potted plant":  {"label": "نبتة",         "emoji": "🌿"},
    "vase":          {"label": "مزهرية",       "emoji": "🏺"},
    "toothbrush":    {"label": "فرشاة أسنان",  "emoji": "🪥"},
    "sports ball":   {"label": "كرة",          "emoji": "⚽"},
    "stop sign":     {"label": "إشارة وقوف",   "emoji": "🛑"},
    "traffic light": {"label": "إشارة مرور",   "emoji": "🚦"},
    "fire hydrant":  {"label": "صنبور إطفاء",  "emoji": "🚒"},
    "suitcase":      {"label": "حقيبة سفر",    "emoji": "🧳"},
    "handbag":       {"label": "حقيبة يد",     "emoji": "👜"},
    "tie":           {"label": "ربطة عنق",     "emoji": "👔"},
    "fork":          {"label": "شوكة",         "emoji": "🍴"},
    "knife":         {"label": "سكين",         "emoji": "🔪"},
    "spoon":         {"label": "ملعقة",        "emoji": "🥄"},
    "bowl":          {"label": "طبق",          "emoji": "🍜"},
    "hot dog":       {"label": "هوت دوج",      "emoji": "🌭"},
    "donut":         {"label": "دونات",        "emoji": "🍩"},
    "bench":         {"label": "مقعد",         "emoji": "🪑"},
    "kite":          {"label": "طائرة ورقية",  "emoji": "🪁"},
    "skis":          {"label": "تزلج",         "emoji": "⛷️"},
    "skateboard":    {"label": "لوح تزلج",     "emoji": "🛹"},
    "surfboard":     {"label": "لوح ركوب الأمواج", "emoji": "🏄"},
    "tennis racket": {"label": "مضرب تنس",     "emoji": "🎾"},
    "baseball bat":  {"label": "مضرب بيسبول",  "emoji": "⚾"},
    "frisbee":       {"label": "فريسبي",       "emoji": "🥏"},
}

# ===================================
# دالة مساعدة: ترجمة اسم الفئة
# ===================================
def translate(class_name: str) -> dict:
    key = class_name.lower().strip()
    if key in ARABIC_LABELS:
        return ARABIC_LABELS[key]
    for eng, data in ARABIC_LABELS.items():
        if eng in key or key in eng:
            return data
    return {"label": class_name, "emoji": "❓"}

# ===================================
# دالة مساعدة: تهجئة الكلمة العربية
# ===================================
def spell_word(word: str) -> list:
    """
    يُعيد قائمة بالحروف الفردية للكلمة العربية،
    مع تخطي المسافات والتشكيل (الحركات).
    مثال: 'تفاح' → ['ت', 'ف', 'ا', 'ح']
    """
    diacritics = set('ًٌٍَُِّْٰٱؐؑؒؓؔؕؖؗ')
    return [ch for ch in word if ch.strip() and ch not in diacritics]

# ===================================
# نماذج البيانات
# ===================================
class PredictionResponse(BaseModel):
    label: str
    confidence: float
    emoji: str
    class_en: str = ""
    detection_count: int = 1
    spelling: list = []

# ===================================
# نقطة النهاية الأساسية
# ===================================
@app.get("/")
async def root():
    model_status = "✅ محمّل" if model else "⚠️ غير محمّل (وضع تجريبي)"
    return {
        "message": "🤖 مرحباً بك في نطوق!",
        "status": "✅ الخادم يعمل",
        "model": model_status,
        "model_path": MODEL_PATH,
        "endpoints": {
            "predict": "POST /predict",
            "tts":     "GET /tts?word=كلمة",
            "health":  "GET /health",
            "labels":  "GET /labels",
            "docs":    "GET /docs",
        }
    }

@app.get("/health")
async def health():
    return {
        "status": "✅ healthy",
        "model_loaded": model is not None,
        "model_path": MODEL_PATH,
    }

@app.get("/labels")
async def get_labels():
    yolo_classes = list(model.names.values()) if (model and hasattr(model, "names")) else []
    return {
        "yolo_classes": yolo_classes,
        "arabic_dictionary_size": len(ARABIC_LABELS),
        "arabic_labels": ARABIC_LABELS,
    }

# ===================================
# نقطة النهاية للصوت - Google Translate TTS
# ===================================
@app.get("/tts")
async def text_to_speech(word: str):
    """
    يستخدم Google Translate TTS لتوليد صوت عربي للكلمة.
    يعيد ملف MP3 مباشرة — لا يحتاج مفتاح API.

    مثال: GET /tts?word=تفاح
    """
    if not word or len(word.strip()) == 0:
        raise HTTPException(status_code=400, detail="الكلمة فارغة")
    if len(word) > 200:
        raise HTTPException(status_code=400, detail="الكلمة طويلة جداً")

    encoded = urllib.parse.quote(word.strip())
    url = (
        f"https://translate.google.com/translate_tts"
        f"?ie=UTF-8&q={encoded}&tl=ar&client=tw-ob"
    )

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://translate.google.com/",
    }

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            audio_data = response.read()

        log.info(f"🔊 TTS: '{word}' — {len(audio_data)} bytes")

        return StreamingResponse(
            io.BytesIO(audio_data),
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": f'inline; filename="{word}.mp3"',
                "Cache-Control": "public, max-age=86400",
                "Access-Control-Allow-Origin": "*",
            }
        )

    except urllib.error.HTTPError as e:
        log.error(f"❌ Google TTS HTTP error: {e.code} for word '{word}'")
        raise HTTPException(status_code=502, detail=f"خطأ من Google TTS: {e.code}")
    except Exception as e:
        log.error(f"❌ خطأ في TTS: {e}")
        raise HTTPException(status_code=502, detail=f"تعذّر توليد الصوت: {str(e)}")

# ===================================
# نقطة النهاية الرئيسية - التنبؤ
# ===================================
@app.post("/predict", response_model=PredictionResponse)
async def predict(file: UploadFile = File(...)):
    """
    يستقبل صورة ويعيد:
    - label           : اسم الكائن بالعربية
    - confidence      : درجة الثقة (0-1)
    - emoji           : رمز تعبيري
    - class_en        : الاسم الإنجليزي للفئة
    - detection_count : عدد الكائنات المكتشفة في الصورة
    - spelling        : قائمة حروف الكلمة العربية
    """

    allowed = {"image/jpeg", "image/png", "image/jpg", "image/webp"}
    if file.content_type not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"❌ نوع الملف غير مدعوم ({file.content_type}). المسموح: JPG, PNG, WEBP"
        )

    contents = await file.read()
    try:
        image = Image.open(io.BytesIO(contents)).convert("RGB")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"❌ خطأ في قراءة الصورة: {e}")

    # ===================================
    # التنبؤ باستخدام YOLOv11
    # ===================================
    if model is not None:
        try:
            results = model(image, verbose=False)

            best_class = None
            best_conf  = 0.0
            det_count  = 0

            for result in results:
                if result.boxes is not None and len(result.boxes) > 0:
                    for box in result.boxes:
                        conf = float(box.conf[0])
                        cls  = int(box.cls[0])
                        det_count += 1
                        if conf > best_conf:
                            best_conf  = conf
                            best_class = model.names[cls]

            if best_class is None:
                raise HTTPException(
                    status_code=422,
                    detail="لم أتمكن من التعرف على أي شيء. حاول مع صورة أوضح!"
                )

            translation = translate(best_class)
            letters     = spell_word(translation["label"])

            log.info(
                f"✅ {best_class} → {translation['label']} "
                f"({best_conf:.1%}) — {det_count} كائن — تهجئة: {letters}"
            )

            return PredictionResponse(
                label=translation["label"],
                confidence=round(best_conf, 3),
                emoji=translation["emoji"],
                class_en=best_class,
                detection_count=det_count,
                spelling=letters,
            )

        except HTTPException:
            raise
        except Exception as e:
            log.error(f"❌ خطأ في التنبؤ: {e}")
            raise HTTPException(status_code=500, detail=f"❌ خطأ في تشغيل النموذج: {e}")

    # ===================================
    # وضع تجريبي (best.pt غير موجود بعد)
    # ===================================
    else:
        import random
        log.warning("⚠️ النموذج غير محمّل — إرجاع نتيجة تجريبية عشوائية")
        chosen = random.choice(list(ARABIC_LABELS.keys()))
        conf   = round(random.uniform(0.80, 0.97), 3)
        t      = ARABIC_LABELS[chosen]
        letters = spell_word(t["label"])
        return PredictionResponse(
            label=t["label"],
            confidence=conf,
            emoji=t["emoji"],
            class_en=chosen + " (demo)",
            detection_count=1,
            spelling=letters,
        )

# ===================================
# معالج الأخطاء العام
# ===================================
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    log.error(f"❌ خطأ غير متوقع: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": "❌ حدث خطأ غير متوقع", "message": str(exc)}
    )

# ===================================
# تشغيل الخادم
# ===================================
if __name__ == "__main__":
    import uvicorn

    print("=" * 65)
    print("🤖  نطوق — FastAPI + YOLOv11 Segmentation + Google TTS")
    print("=" * 65)
    if model:
        names_preview = ", ".join(list(model.names.values())[:8])
        print(f"✅  النموذج محمّل: {MODEL_PATH}")
        print(f"   الفئات ({len(model.names)}): {names_preview} ...")
    else:
        print(f"⚠️  best.pt غير موجود — وضع تجريبي مفعّل")
        print(f"   ضع الملف هنا: {MODEL_PATH}")
    print()
    print(f"📖  التوثيق:  http://127.0.0.1:8000/docs")
    print(f"🔗  التنبؤ:   POST http://127.0.0.1:8000/predict")
    print(f"🔊  الصوت:    GET  http://127.0.0.1:8000/tts?word=تفاح")
    print(f"🏷️   الفئات:   GET  http://127.0.0.1:8000/labels")
    print("=" * 65 + "\n")

    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")