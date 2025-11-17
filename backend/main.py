import io
import json
import os
from datetime import datetime
from typing import Optional

import uvicorn
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from utils.data_extraction import get_all_history, init_db, run_langextract, save_to_db
from utils.logger_config import logger

# Initialize the database on startup
init_db()

# Create FastAPI app
app = FastAPI(
    title="Patient Referral API",
    description="API for processing audio referrals",
    version="1.0.0",
)

# Add CORS middleware to allow requests from your React app (adjust origins as needed)
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=[
#         "http://localhost:3000",
#         "http://127.0.0.1:3000",
#     ],  # Replace with your React dev server URL
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "*",  # Temporary wildcard for testing—remove in production
        "http://localhost:3000",  # For local frontend
        "https://your-frontend-domain.onrender.com"  # Add later for deployed frontend
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# Adjust transcribe_mp3_with_openai for MP3 input
# -----------------------------
# OpenAI Whisper supports MP3 directly, so no processing or saving to WAV needed.
# This simplified version passes the raw MP3 bytes straight to the API.


def transcribe_mp3_with_openai(mp3_bytes: bytes) -> str:
    """
    Transcribe MP3 audio bytes using OpenAI Whisper.
    Passes raw MP3 bytes directly to the API (no resampling or conversion).
    """
    if not mp3_bytes:
        logger.warning("Empty MP3 bytes provided to transcribe_mp3_with_openai")
        return ""

    try:
        # Transcribe the raw MP3 with OpenAI Whisper
        from dotenv import load_dotenv
        from openai import OpenAI  # Import here if not already global

        load_dotenv()
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        response = client.audio.transcriptions.create(
            model="whisper-1",
            file=("input.mp3", mp3_bytes),
            language="en",  # Assuming English; adjust if needed
        )
        logger.info("MP3 audio transcription completed successfully")
        return response.text
    except Exception as e:
        logger.error(f"MP3 Transcription Error: {e}")
        return ""


# -----------------------------
# API Endpoints
# -----------------------------


@app.post("/process-referral", summary="Process MP3 audio referral")
async def process_referral(
    audio_file: UploadFile = File(..., description="MP3 audio file from React app")
):
    """
    Receives an MP3 file from the React app, transcribes it, extracts structured info,
    saves to database, and returns the extracted JSON.
    """
    # if audio_file.content_type != "audio/mpeg" and not audio_file.filename.lower().endswith('.mp3'):
    #     raise HTTPException(status_code=400, detail="Only MP3 files are supported")

    if audio_file.content_type not in [
        "audio/mpeg",
        "audio/webm",
    ] and not audio_file.filename.lower().endswith((".mp3", ".webm")):
        raise HTTPException(
            status_code=400, detail="Only MP3 or WebM files are supported"
        )
    try:
        # Read MP3 bytes
        mp3_bytes = await audio_file.read()

        # Transcribe the audio (using the MP3-specific function)
        logger.info(f"Received MP3: {audio_file.filename}")

        spoken_text = transcribe_mp3_with_openai(mp3_bytes)
        if not spoken_text:
            raise HTTPException(status_code=500, detail="Transcription failed")

        # Extract structured info using langextract
        extracted_info = run_langextract(spoken_text)
        if not extracted_info:
            raise HTTPException(status_code=500, detail="Information extraction failed")

        # Save to database
        save_to_db(spoken_text, extracted_info)

        # After DB save, fetch the latest patient ID to name the raw MP3 file
        recent_rows = (
            get_all_history()
        )  # Assumes this returns ordered by timestamp DESC, limited internally
        if recent_rows:
            patient_id = recent_rows[0][
                0
            ]  # First element of the most recent row tuple is patient_id
            audio_dir = "./audio_files"
            os.makedirs(audio_dir, exist_ok=True)
            mp3_filename = f"{audio_dir}/{patient_id}.mp3"
            with open(mp3_filename, "wb") as buffer:
                buffer.write(mp3_bytes)
            logger.info(
                f"Saved raw MP3 with patient ID: {patient_id} -> {mp3_filename}"
            )
        else:
            logger.warning("Could not retrieve patient ID for MP3 save")

        # Return the extracted JSON
        return JSONResponse(content=extracted_info)

    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        logger.error(f"Error processing referral: {e}")
        raise HTTPException(
            status_code=500, detail="Internal server error during processing"
        )


@app.get("/history", summary="Get patient referral history")
async def get_history(limit: Optional[int] = 20):
    """
    Fetches the last N patient history entries from the database.
    Returns a list of dictionaries with flattened fields.
    """
    try:
        rows = (
            get_all_history()
        )  # This already limits to 20 by default; adjust if needed

        history_data = []
        for row in rows:
            (
                patient_id,
                patient_name,
                age,
                sex,
                patient_phone_number,
                symptoms_and_signs,
                referred_hospital,
                referrer_name,
                referrer_designation,
                referrer_organization,
                referrer_phone_number,
                examination_findings,
                investigations_with_results,
                diagnosis,
                icd10_code,
                treatment_given,
                drug_hypersensitivity,
                reason_for_referral,
                advice_to_patient,
                transport,
                comments,
                timestamp,
                spoken_text,
                extracted_json_str,
            ) = row

            history_entry = {
                "patient_id": patient_id,
                "patient_name": patient_name,
                "age": age,
                "sex": sex,
                "patient_phone_number": patient_phone_number,
                "symptoms_and_signs": symptoms_and_signs,
                "referred_hospital": referred_hospital,
                "referrer_name": referrer_name,
                "referrer_designation": referrer_designation,
                "referrer_organization": referrer_organization,
                "referrer_phone_number": referrer_phone_number,
                "examination_findings": examination_findings,
                "investigations_with_results": investigations_with_results,
                "diagnosis": diagnosis,
                "icd10_code": icd10_code,
                "treatment_given": treatment_given,
                "drug_hypersensitivity": drug_hypersensitivity,
                "reason_for_referral": reason_for_referral,
                "advice_to_patient": advice_to_patient,
                "transport": transport,
                "comments": comments,
                "timestamp": timestamp,
                "spoken_text": spoken_text,
                "extracted_info": json.loads(extracted_json_str),  # Parse back to dict
            }
            history_data.append(history_entry)

        return JSONResponse(content=history_data)
    except Exception as e:
        logger.error(f"Error fetching history: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch history")


@app.get("/", summary="Health check")
async def health_check():
    """Simple health check endpoint."""
    return {"status": "healthy", "message": "Patient Referral API is running"}


# -----------------------------
# Run the app with Uvicorn
# -----------------------------
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
