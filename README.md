# 🌟 المستكشف الذكي | Smart Explorer

![Python](https://img.shields.io/badge/Python-3.10-blue)
![Streamlit](https://img.shields.io/badge/Frontend-Streamlit-red)
![FastAPI](https://img.shields.io/badge/Backend-FastAPI-green)
![YOLO](https://img.shields.io/badge/AI-YOLO-orange)

An interactive educational app for kids that uses **Computer Vision** to recognize objects and teach them in a fun and engaging way.

---

## 🎯 Project Idea

The app allows children to:

1. Start a fun learning journey 🎈
2. Choose a character 👧👦
3. Upload an image 📸
4. Let AI detect objects 🤖
5. Learn the word with:

   * Arabic name
   * Emoji
   * Spelling
   * Audio pronunciation 🔊

👉 Goal: Make learning **visual, simple, and fun for kids**.

---

## ✨ Features

* 🎨 Kid-friendly Arabic UI
* 👧👦 Character selection
* 📸 Image upload
* 🤖 AI object detection
* 😀 Emoji-based learning
* 🔤 Word spelling display
* 🔊 Text-to-Speech pronunciation

---

## 🧠 Technologies Used

### Frontend

* Streamlit
* CSS

### Backend

* FastAPI
* Uvicorn

### AI

* Ultralytics YOLO
* Pillow
* NumPy

### Audio

* Google TTS

---

## 📁 Project Structure

```bash
project/
│
├── kidsapp.py
├── logo.png
├── kids.png
├── girl.png
├── boy.png
│
├── yolo_backend/
│   ├── main.py
│   ├── best.pt
│   ├── requirements.txt
│
└── README.md
```

---

## ⚙️ How It Works

1. **Start Page** → Welcome screen
2. **Character Selection** → Choose boy or girl
3. **Upload Image** → User uploads image
4. **Send to API** → `/predict`
5. **YOLO Model** → Detect object
6. **Display Result** → Name + Emoji + Audio

---

## 🚀 Run the Project

### 1️⃣ Backend (FastAPI)

```bash
cd yolo_backend
pip install -r requirements.txt
python -m uvicorn main:app --reload
```

Open:

```
http://127.0.0.1:8000/docs
```

---

### 2️⃣ Frontend (Streamlit)

```bash
streamlit run kidsapp.py
```

---

## 🔗 API Endpoints

| Endpoint   | Method | Description    |
| ---------- | ------ | -------------- |
| `/`        | GET    | Root           |
| `/health`  | GET    | Check status   |
| `/labels`  | GET    | Get classes    |
| `/predict` | POST   | Detect object  |
| `/tts`     | GET    | Text to speech |

---

## 📊 Example Output

```json
{
  "label": "موز",
  "confidence": 0.94,
  "emoji": "🍌",
  "class_en": "banana",
  "spelling": ["م", "و", "ز"]
}
```

---

## ⚠️ Notes

* Start **FastAPI first**
* Ensure `best.pt` exists
* Camera may not work → use upload
* If model fails → demo mode runs

---


## 🔮 Future Work

* 🎮 Mini learning games
* 🌍 Multi-language support
* ☁️ Cloud deployment

---

## 👩‍💻 Team

- Lana Aljuaid
- Abdularhmn
Abrar
Mohamed 
---

## 🏷️ Project Name

**Smart Explorer**

Making learning fun for kids 💡✨
