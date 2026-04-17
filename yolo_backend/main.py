from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import Response
from ultralytics import YOLO
from PIL import Image, ImageDraw, ImageFont
from deep_translator import GoogleTranslator
from functools import lru_cache
import arabic_reshaper
from bidi.algorithm import get_display
import io

app = FastAPI()

# Load model once at startup
model = YOLO("best.pt")
FONT = ImageFont.truetype("NotoNaskhArabic-Regular.ttf", 48)
translator = GoogleTranslator(source="en", target="ar")


@lru_cache(maxsize=512)
def to_arabic(en_name: str) -> str:
    """Translate English class name to Arabic. Cached per class."""
    try:
        return translator.translate(en_name.replace("_", " "))
    except Exception:
        return en_name


def shape_ar(text: str) -> str:
    """Reshape Arabic text so it renders correctly (right-to-left, connected letters)."""
    return get_display(arabic_reshaper.reshape(text))


@app.get("/")
def health():
    return {"status": "ok"}


@app.post("/segment")
async def segment(file: UploadFile = File(...)):
    try:
        img = Image.open(io.BytesIO(await file.read())).convert("RGB")
    except Exception:
        raise HTTPException(400, "Invalid image")

    # Run YOLO-seg on CPU
    results = model.predict(img, device="cpu", verbose=False, imgsz=640)[0]

    # YOLO's built-in plot gives us boxes + masks drawn on the image
    annotated = Image.fromarray(results.plot()[:, :, ::-1])  # BGR -> RGB

    # Find the dominant class (largest total mask area)
    if results.masks is not None and len(results.masks) > 0:
        masks = results.masks.data.cpu().numpy()            # (N, H, W)
        cls_ids = results.boxes.cls.cpu().numpy().astype(int)

        areas = {}
        for m, c in zip(masks, cls_ids):
            areas[c] = areas.get(c, 0) + float(m.sum())

        top_cls = max(areas, key=areas.get)
        en_name = model.names[top_cls]
        ar_name = to_arabic(en_name)

        # Calculate percentage of image covered by the dominant class
        total_pixels = annotated.width * annotated.height
        pct = 100.0 * areas[top_cls] / total_pixels
        label = shape_ar(f"{ar_name} ({pct:.1f}%)")

        # Draw Arabic label in the top-right corner with a dark background
        draw = ImageDraw.Draw(annotated, "RGBA")
        bbox = draw.textbbox((0, 0), label, font=FONT)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x, y = annotated.width - w - 20, 20
        draw.rectangle(
            [x - 10, y - 10, x + w + 10, y + h + 10],
            fill=(0, 0, 0, 180),
        )
        draw.text((x, y), label, font=FONT, fill=(255, 255, 255))

    buf = io.BytesIO()
    annotated.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")