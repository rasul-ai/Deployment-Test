# Patient Referral Audio Processing App

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Backend: FastAPI](https://img.shields.io/badge/Backend-FastAPI-blue)](https://fastapi.tiangolo.com/)
[![Frontend: React](https://img.shields.io/badge/Frontend-React-green)](https://react.dev/)

## Overview

This is a full-stack web application for processing patient referral audio recordings. It allows healthcare professionals to record spoken patient details via a microphone, transcribe the audio using OpenAI's Whisper, extract structured data (e.g., patient name, symptoms, referral hospital), save it to a database, and display the results as JSON.

- **Backend**: FastAPI server that handles audio uploads (MP3/WebM), transcription, data extraction, and database storage.
- **Frontend**: React app with real-time audio recording, device selection, preview playback, and JSON visualization.

The app is designed for local development and can be extended for production (e.g., deploy backend to Heroku/Vercel, frontend to Netlify).

## Features

- **Audio Recording**: Browser-based recording with microphone permission handling and device selection (supports multiple mics like built-in or USB headset).
- **Format Support**: Handles MP3 and WebM audio files.
- **Transcription**: Automatic speech-to-text using OpenAI Whisper (English, customizable).
- **Data Extraction**: Uses `langextract` to parse transcribed text into structured fields (e.g., patient ID, name, age, symptoms, referral details).
- **Database Integration**: SQLite for storing referrals (with history fetch).
- **Preview & Upload**: Play back recording before sending; displays extracted JSON with black text for visibility.
- **Error Handling**: User-friendly messages for mic access, empty recordings, or backend failures.
- **CORS Enabled**: Frontend on `localhost:3000` can communicate with backend on `localhost:8000`.

## Tech Stack

### Backend
- **Framework**: FastAPI
- **Server**: Uvicorn (with auto-reload for dev)
- **Transcription**: OpenAI Whisper API
- **Data Extraction**: Custom `langextract` module (from `utils.data_extraction`)
- **Database**: SQLite (via `init_db` and custom utils)
- **Logging**: Custom logger (`utils.logger_config`)
- **Dependencies**: `fastapi`, `uvicorn`, `openai`, `python-dotenv`, `pydub` (optional for MP3, but not used now)

### Frontend
- **Framework**: React (Create React App)
- **Recording**: RecordRTC (for reliable WebM audio capture)
- **Icons**: react-icons (FaMicrophone, etc.)
- **Styling**: Custom CSS (App.css)
- **Dependencies**: `react-scripts`, `recordrtc`, `react-icons`

## Prerequisites

- Python 3.8+ (for backend)
- Node.js 18+ (for frontend)
- OpenAI API Key (set in `.env`: `OPENAI_API_KEY=your_key`)
- FFmpeg (optional, if using MP3 processing: `sudo apt install ffmpeg` on Ubuntu)

## Setup

### Backend
1. Clone the repo and navigate to `backend/`:

2. Create virtual environment and install deps:
```
source pr_app/bin/activate  # On Windows: pr_app\Scripts\activate
pip install fastapi uvicorn openai python-dotenv pydub
```

3. Set up `.env`:
```
OPENAI_API_KEY=sk-your-openai-key-here
```

4. Run the server:
```
python main.py or uvicorn main:app --reload --host 0.0.0.0 --port 8000
Access docs at http://localhost:8000/docs
Health check: http://localhost:8000/health
```


### Frontend
Navigate to `frontend/`
```
cd frontend
npm install
npm start
Opens at http://localhost:3000
```

### Database
- Auto-initialized on backend startup (`init_db()` in `main.py`).
- Data stored in SQLite (check `utils/data_extraction.py` for schema).

## Usage

1. **Record & Process**:
- Open `http://localhost:3000`.
- Grant mic permission → Select device (if multiple).
- Click "Start Recording" → Speak patient details (e.g., "Patient John Doe, age 45, headache, refer to City Hospital").
- Click "Stop (Xs)" → Preview audio plays (new recording each time).
- Click "Upload" → Backend processes → JSON displays (e.g., `{"patient_name": "John Doe", "age": 45, ...}`).

2. **Test Backend Directly** (via curl):
- Returns JSON or error.

3. **View History**:
- Frontend doesn't have it yet—add a button to fetch `/history` if needed.

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/process-referral` | Upload audio (MP3/WebM), transcribe, extract, save to DB, return JSON. |
| GET | `/history?limit=20` | Fetch last N referral entries as JSON array. |
| GET | `/health` | Health check: `{"status": "healthy"}`. |

- Full docs: `http://localhost:8000/docs` (Swagger UI).

## Project Structure
```
Patient_Referral_App/
├── backend/
│   ├── main.py                 # FastAPI app
│   ├── utils/
│   │   ├── data_extraction.py  # DB, transcription, extraction logic
│   │   └── logger_config.py    # Logging setup
│   └── .env.example            # Env template
├── frontend/
│   ├── src/
│   │   ├── App.js              # React component
│   │   └── App.css             # Styles
│   └── package.json
└── README.md
```