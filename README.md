# 🌟 Smart Explorer | المستكشف الذكي

![Python](https://img.shields.io/badge/Python-3.10-blue)
![Streamlit](https://img.shields.io/badge/Frontend-Streamlit-red)
![FastAPI](https://img.shields.io/badge/Backend-FastAPI-green)
![YOLO](https://img.shields.io/badge/AI-YOLO-orange)

An **AI-powered interactive learning application** designed for children (ages 5–10), combining **Computer Vision and Audio Learning** to make education fun, visual, and engaging.

---

## 🎯 Overview

**Smart Explorer** transforms traditional learning into an interactive experience where children explore the world around them using AI.

📸 The child captures or uploads an image →  
🤖 The system detects the object →  
🔊 The app teaches the word with sound, spelling, and visuals  

> 💡 Goal: Make learning **simple, visual, and enjoyable for kids**

---

## ✨ Features

- 🎨 Kid-friendly Arabic UI  
- 👧👦 Character selection  
- 📸 Image upload or camera input  
- 🤖 AI-powered object detection (YOLO)  
- 🔤 Word spelling display  
- 🔊 Arabic pronunciation (Text-to-Speech)  

---

## 🧠 Tech Stack

### 🖥️ Frontend
- Streamlit  
- Custom CSS  

### ⚙️ Backend
- FastAPI  
- Uvicorn  

### 🤖 AI & Vision
- Ultralytics YOLO  

### 🔊 Audio
- Google Text-to-Speech (gTTS)

---

## 📁 Project Structure

```

project/
│
├── kidsapp.py              # Streamlit Frontend
├── logo.png
├── kids.png               # Background
├── girl.png
├── boy.png
│
├── yolo_backend/
│   ├── main.py            # FastAPI Backend
│   ├── best.pt            # Trained YOLO Model
│   ├── requirements.txt
│
└── README.md

````

---

## ⚙️ How It Works

1. **Welcome Screen** → Start the journey  
2. **Character Selection** → Choose avatar  
3. **Upload / Capture Image**  
4. **Send to Backend API**  
5. **YOLO Model Detects Object**  
6. **Display Result**:
   - Arabic word  
   - Spelling  
   - Audio pronunciation  

---

## 🚀 Running the Project

### 1️⃣ Backend (FastAPI)

```bash
cd yolo_backend
pip install -r requirements.txt
python -m uvicorn main:app --reload
````

Open API docs:

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

| Endpoint   | Method | Description          |
| ---------- | ------ | -------------------- |
| `/`        | GET    | Root                 |
| `/health`  | GET    | Server status        |
| `/labels`  | GET    | Available classes    |
| `/segment` | POST   | Detect object (YOLO) |
| `/tts`     | GET    | Generate audio       |

---

## 📊 Example Response

```json
{
  "label_ar": "موز",
  "label_en": "banana",
  "confidence": 0.94,
  "spelling": ["م", "و", "ز"]
}
```

---

## ⚠️ Notes

* Start the backend before the frontend
* Ensure `best.pt` model exists
* Camera may not work in some browsers → use image upload
* If the API fails → fallback/demo mode may run

---

## 🔮 Future Improvements

* 🎮 Interactive mini-games
* 🌍 Multi-language support
* ☁️ Cloud deployment
* 🧠 More object categories (100+)

---

## 👩‍💻 Team

* Lana Aljuaid
* Abdularhmn
* Abrar
* Mohamed

---

## 🏷️ Project Name

**Smart Explorer**

> Making learning fun for kids 💡✨


**Smart Explorer**

Making learning fun for kids 💡✨
