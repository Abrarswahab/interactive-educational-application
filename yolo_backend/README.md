# YOLO-Seg Backend

FastAPI backend that runs a YOLO segmentation model on CPU and returns the
annotated image with the dominant object's name labeled in Arabic.

## Endpoints

- `GET  /`         → health check
- `POST /segment`  → upload an image (`multipart/form-data`, field name `file`),
                     returns `image/png`

## Files

- `main.py` — FastAPI app
- `best.pt` — trained YOLO-seg model weights
- `NotoNaskhArabic-Regular.ttf` — Arabic font for rendering labels
- `Dockerfile` — container build
- `requirements.txt` — Python deps (CPU-only PyTorch)

## Deploy on Railway

1. Push this folder to a GitHub repository
2. Create a Railway project from the repo
3. Railway auto-detects the Dockerfile and builds
4. Go to Settings → Networking → Generate Domain
5. Your backend is live at the generated URL

## Local testing

```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Then test:
```bash
curl -X POST -F "file=@test.jpg" http://localhost:8000/segment --output result.png
```
