import difflib
import json
import os
import random
import re
import sqlite3
import string
from datetime import datetime
from zoneinfo import ZoneInfo

import langextract as lx
import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI
from utils.logger_config import logger

# Set BD timezone
bd_tz = ZoneInfo("Asia/Dhaka")

# -----------------------------
# OpenAI setup
# -----------------------------
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY is not set in the .env file or environment")
client = OpenAI(api_key=OPENAI_API_KEY)

# -----------------------------
# Database setup (SQLite)
# -----------------------------
DB_FILE = "./patients_file.db"
MODEL_ID = "gpt-4o-mini"


def _generate_next_patient_id(cursor):
    """
    Generates a random 7-character uppercase alphanumeric patient ID.
    Ensures uniqueness by checking against existing IDs.
    """
    chars = string.ascii_uppercase + string.digits
    while True:
        patient_id = "".join(random.choice(chars) for _ in range(7))
        cursor.execute(
            "SELECT patient_id FROM history WHERE patient_id = ?", (patient_id,)
        )
        if not cursor.fetchone():
            break
    logger.debug(f"Generated new patient ID: {patient_id}")
    return patient_id


def init_db():
    """Initializes the SQLite database table with flattened fields and history."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS history (
                patient_id TEXT PRIMARY KEY,
                spoken_text TEXT,
                extracted_json TEXT,

                -- Patient Fields
                patient_name TEXT,
                age TEXT,
                sex TEXT,
                patient_phone_number TEXT,
                symptoms_and_signs TEXT, -- Comma-separated list
                referred_hospital TEXT,
                
                -- Referrer Fields
                referrer_name TEXT,
                referrer_designation TEXT,
                referrer_organization TEXT,
                referrer_phone_number TEXT,

                -- Additional Fields
                examination_findings TEXT,
                investigations_with_results TEXT,
                diagnosis TEXT,
                icd10_code TEXT,
                treatment_given TEXT,
                drug_hypersensitivity TEXT,
                reason_for_referral TEXT,
                advice_to_patient TEXT,
                transport TEXT,
                comments TEXT,

                timestamp TEXT
            )
        """
        )

        conn.commit()
        conn.close()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        raise


def save_to_db(spoken_text, extracted_json):
    """Saves the transcribed text and all flattened fields to the database."""

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    try:
        # Generate the random patient ID
        patient_id = _generate_next_patient_id(cursor)

        # 1. Prepare data for insertion by flattening the JSON structure
        p_info = extracted_json.get("patient_info", {})
        r_info = extracted_json.get("referrer_info", {})

        # Extract individual fields
        patient_name = p_info.get("name")
        age = p_info.get("age")
        sex = p_info.get("sex")
        patient_phone_number = p_info.get("phone_number")

        referred_hospital = extracted_json.get("referred_hospital")

        referrer_name = r_info.get("name")
        referrer_designation = r_info.get("designation")
        referrer_organization = r_info.get("referrer_hospital")
        referrer_phone_number = r_info.get("phone_number")

        # Combined symptoms and signs
        symptoms_and_signs = ", ".join(extracted_json.get("symptoms_and_signs", []))

        # Additional fields
        examination_findings = extracted_json.get("examination_findings", "")
        investigations_with_results = ", ".join(
            extracted_json.get("investigations_with_results", [])
        )
        diagnosis = extracted_json.get("diagnosis", "")
        icd10_code = extracted_json.get("icd10_code", "")
        treatment_given = ", ".join(extracted_json.get("treatment_given", []))
        drug_hypersensitivity = extracted_json.get("drug_hypersensitivity", "")
        reason_for_referral = extracted_json.get("reason_for_referral", "")
        advice_to_patient = extracted_json.get("advice_to_patient", "")
        transport = extracted_json.get("transport", "")
        comments = extracted_json.get("comments", "")

        # Serialize the full JSON object to save in the 'extracted_json' column
        extracted_json_str = json.dumps(extracted_json, ensure_ascii=False)

        # Define the columns and corresponding values
        columns = (
            "patient_id",
            "spoken_text",
            "extracted_json",
            "patient_name",
            "age",
            "sex",
            "patient_phone_number",
            "symptoms_and_signs",
            "referred_hospital",
            "referrer_name",
            "referrer_designation",
            "referrer_organization",
            "referrer_phone_number",
            "examination_findings",
            "investigations_with_results",
            "diagnosis",
            "icd10_code",
            "treatment_given",
            "drug_hypersensitivity",
            "reason_for_referral",
            "advice_to_patient",
            "transport",
            "comments",
            "timestamp",
        )

        values = (
            patient_id,
            spoken_text,
            extracted_json_str,
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
            datetime.now(bd_tz),
        )

        # Create the INSERT statement dynamically based on the number of columns
        placeholders = ", ".join(["?"] * len(columns))
        column_names = ", ".join(columns)

        cursor.execute(
            f"""
            INSERT INTO history ({column_names})
            VALUES ({placeholders})
        """,
            values,
        )

        conn.commit()
        logger.info(f"Patient {patient_id} saved to database successfully.")
    except Exception as e:
        logger.error(f"Error saving to database: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


def get_all_history():
    """Fetches all history rows including the new test result."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        # Select all fields
        cursor.execute(
            """
            SELECT 
                patient_id, patient_name, age, sex,
                patient_phone_number, symptoms_and_signs, referred_hospital, 
                referrer_name, referrer_designation, referrer_organization, referrer_phone_number, 
                examination_findings, investigations_with_results, diagnosis, icd10_code,
                treatment_given, drug_hypersensitivity, reason_for_referral, advice_to_patient,
                transport, comments,
                timestamp, spoken_text, extracted_json
            FROM history 
            ORDER BY timestamp DESC 
            LIMIT 20
        """
        )
        rows = cursor.fetchall()
        logger.debug(f"Fetched {len(rows)} history rows.")
        return rows
    except Exception as e:
        logger.error(f"Error fetching history: {e}")
        return []
    finally:
        conn.close()


# -----------------------------
# LangExtract Prompt for English Patient Referrals
# -----------------------------
prompt = """
Extract structured information from the English patient referral text.
Return a JSON object with the following keys and nested structures:
- text: The original referral text.
- referrer_info: Information about the person making the referral.
    - name: Referrer's full name.
    - designation: Referrer's job title (e.g., Community Health Worker).
    - referrer_hospital: The hospital the referrer works for (e.g., Govt).
    - phone_number: Referrer's phone number.
- patient_info: Information about the referred patient.
    - name: Patient's full name.
    - age: Patient's age (as a number or string).
    - sex: Patient's sex (e.g., male, female).
    - phone_number: Patient's phone number.
- symptoms_and_signs: A list of the patient's reported symptoms and signs (e.g., ["high fever", "dizziness", "frequent urination"]).
- referred_hospital: The name of the hospital or health center the patient is being referred to.
- examination_findings: A string describing examination findings (e.g., "temperature 102°F, pulse 110 bpm").
- investigations_with_results: A list of investigations with results (e.g., ["random blood sugar: 14.8 mmol/L", "urine glucose: +++"]).
- diagnosis: The provisional or confirmatory diagnosis (e.g., "gestational diabetes").
- icd10_code: The ICD10 code (e.g., "O24.4").
- treatment_given: A list of treatments given (e.g., ["paracetamol 500 mg", "insulin 6 units"]).
- drug_hypersensitivity: Known drug hypersensitivity (e.g., "None reported").
- reason_for_referral: Reason for the referral (e.g., "further evaluation and management").
- advice_to_patient: Advice given to the patient (e.g., "maintain hydration, avoid sugary foods").
- transport: Type of transport arranged (e.g., "Govt Ambulance").
- comments: Any additional comments.
"""

# -----------------------------
# LangExtract Example for English Patient Referrals
# -----------------------------
# Using the structured prompt with explicit village, upazilla, district keywords for high accuracy.

examples = [
    lx.data.ExampleData(
        # Example text uses the new structured format
        text="I am Rahim Uddin, Community Health Worker, Govt, phone 017xxxxxxxx, referring patient Fatima Akter, a 32-year-old female, phone number 019xxxxxxxx, who is showing symptoms of persistent cough, fever, and weight loss, to Mirzapur Health Complex.",
        extractions=[
            lx.data.Extraction(
                extraction_class="patient_referral",
                extraction_text="I am Rahim Uddin, Community Health Worker, Govt, phone 017xxxxxxxx, referring patient Fatima Akter, a 32-year-old female, phone number 019xxxxxxxx, who is showing symptoms of persistent cough, fever, and weight loss, to Mirzapur Health Complex.",
                attributes={
                    "text": "I am Rahim Uddin, Community Health Worker, Govt, phone 017xxxxxxxx, referring patient Fatima Akter, a 32-year-old female, phone number 019xxxxxxxx, who is showing symptoms of persistent cough, fever, and weight loss, to Mirzapur Health Complex.",
                    "referrer_info": {
                        "name": "Rahim Uddin",
                        "designation": "Community Health Worker",
                        "referrer_hospital": "Govt",
                        "phone_number": "017xxxxxxxx",
                    },
                    "patient_info": {
                        "name": "Fatima Akter",
                        "age": "32",
                        "sex": "female",
                        "phone_number": "019xxxxxxxx",
                    },
                    "symptoms_and_signs": ["persistent cough", "fever", "weight loss"],
                    "referred_hospital": "Mirzapur Health Complex",
                    "examination_findings": "",
                    "investigations_with_results": [],
                    "diagnosis": "",
                    "icd10_code": "",
                    "treatment_given": [],
                    "drug_hypersensitivity": "",
                    "reason_for_referral": "",
                    "advice_to_patient": "",
                    "transport": "",
                    "comments": "",
                },
            )
        ],
    ),
    lx.data.ExampleData(
        # Additional example text for varied structure (no address or phone numbers)
        text="I am Dr. Rabeya Khatun, Emergency Medical Officer at Bhashan Char Community Clinic, referring Halima Khatun, a 24-year-old pregnant woman, to Khulna 250 Bed Hospital. The patient presents with high fever, dizziness, frequent urination, and fatigue for the last three days. On examination, her temperature was 102°F, pulse 110 bpm, blood pressure 130/90 mmHg, and mild dehydration was noted. Investigations revealed a random blood sugar of 14.8 mmol/L, urine glucose +++, and hemoglobin 10.2 g/dl. The provisional diagnosis is gestational diabetes with fever due to possible infection (ICD10 Code: O24.4). She has been given paracetamol 500 mg for fever, oral rehydration, and insulin 6 units subcutaneously. No known drug hypersensitivity reported. The referral is made for further evaluation, obstetric consultation, and hospital-based management for high blood sugar during pregnancy. The patient has been advised to maintain hydration, avoid sugary foods, and proceed immediately to the referral hospital. Government ambulance has been arranged for transport. The patient is currently stable but requires close monitoring and inpatient management.",
        extractions=[
            lx.data.Extraction(
                extraction_class="patient_referral",
                extraction_text="I am Dr. Rabeya Khatun, Emergency Medical Officer at Bhashan Char Community Clinic, referring Halima Khatun, a 24-year-old pregnant woman, to Khulna 250 Bed Hospital. The patient presents with high fever, dizziness, frequent urination, and fatigue for the last three days. On examination, her temperature was 102°F, pulse 110 bpm, blood pressure 130/90 mmHg, and mild dehydration was noted. Investigations revealed a random blood sugar of 14.8 mmol/L, urine glucose +++, and hemoglobin 10.2 g/dl. The provisional diagnosis is gestational diabetes with fever due to possible infection (ICD10 Code: O24.4). She has been given paracetamol 500 mg for fever, oral rehydration, and insulin 6 units subcutaneously. No known drug hypersensitivity reported. The referral is made for further evaluation, obstetric consultation, and hospital-based management for high blood sugar during pregnancy. The patient has been advised to maintain hydration, avoid sugary foods, and proceed immediately to the referral hospital. Government ambulance has been arranged for transport. The patient is currently stable but requires close monitoring and inpatient management.",
                attributes={
                    "text": "I am Dr. Rabeya Khatun, Emergency Medical Officer at Bhashan Char Community Clinic, referring Halima Khatun, a 24-year-old pregnant woman, to Khulna 250 Bed Hospital. The patient presents with high fever, dizziness, frequent urination, and fatigue for the last three days. On examination, her temperature was 102°F, pulse 110 bpm, blood pressure 130/90 mmHg, and mild dehydration was noted. Investigations revealed a random blood sugar of 14.8 mmol/L, urine glucose +++, and hemoglobin 10.2 g/dl. The provisional diagnosis is gestational diabetes with fever due to possible infection (ICD10 Code: O24.4). She has been given paracetamol 500 mg for fever, oral rehydration, and insulin 6 units subcutaneously. No known drug hypersensitivity reported. The referral is made for further evaluation, obstetric consultation, and hospital-based management for high blood sugar during pregnancy. The patient has been advised to maintain hydration, avoid sugary foods, and proceed immediately to the referral hospital. Government ambulance has been arranged for transport. The patient is currently stable but requires close monitoring and inpatient management.",
                    "referrer_info": {
                        "name": "Dr. Rabeya Khatun",
                        "designation": "Emergency Medical Officer",
                        "referrer_hospital": "Bhashan Char Community Clinic",
                        "phone_number": "",
                    },
                    "patient_info": {
                        "name": "Halima Khatun",
                        "age": "24",
                        "sex": "female",
                        "phone_number": "",
                    },
                    "symptoms_and_signs": [
                        "high fever",
                        "dizziness",
                        "frequent urination",
                        "fatigue",
                    ],
                    "referred_hospital": "Khulna 250 Bed Hospital",
                    "examination_findings": "temperature was 102°F, pulse 110 bpm, blood pressure 130/90 mmHg, and mild dehydration was noted",
                    "investigations_with_results": [
                        "random blood sugar of 14.8 mmol/L",
                        "urine glucose +++",
                        "hemoglobin 10.2 g/dl",
                    ],
                    "diagnosis": "gestational diabetes with fever due to possible infection",
                    "icd10_code": "O24.4",
                    "treatment_given": [
                        "paracetamol 500 mg for fever",
                        "oral rehydration",
                        "insulin 6 units subcutaneously",
                    ],
                    "drug_hypersensitivity": "No known drug hypersensitivity reported",
                    "reason_for_referral": "further evaluation, obstetric consultation, and hospital-based management for high blood sugar during pregnancy",
                    "advice_to_patient": "maintain hydration, avoid sugary foods, and proceed immediately to the referral hospital",
                    "transport": "Government ambulance",
                    "comments": "The patient is currently stable but requires close monitoring and inpatient management",
                },
            )
        ],
    ),
]


def preprocess_location(name):
    """
    Preprocess the name to extract key location terms by discarding common non-location words.
    """

    discard = {
        "hospital",
        "bed",
        "govt",
        "government",
        "clinic",
        "upazila",
        "district",
        "general",
        "sadar",
        "medical",
        "college",
        "rhc",
        "uhc",
        "dh",
        "and",
        "of",
        "the",
        "in",
        "and",
        "disease",
        "center",
        "specialized",
        "maternal",
        "child",
        "health",
        "training",
        "institute",
        "national",
        "bangladesh",
        "principal",
        "director",
        "10",
        "20",
        "25",
        "30",
        "31",
        "50",
        "250",
        "300",
        "500",
    }
    name_lower = name.lower().strip()
    # Remove parenthetical expressions like (RHC)
    name_lower = re.sub(r"\([^)]*\)", "", name_lower)
    # Replace punctuation with spaces
    name_lower = re.sub(r"[,./-]", " ", name_lower)
    # Split and filter words
    words = [w for w in name_lower.split() if w and w not in discard]
    return " ".join(words).strip()


def lookup_short_name_to_full(
    csv_path,
    short_name,
    short_col="Facility_short_name",
    full_col="Facility Name",
    threshold=80.0,
):
    """
    Looks up the short name in the CSV using fuzzy matching and returns the corresponding full facility name if a match above threshold is found.
    Matching is case-insensitive using difflib.SequenceMatcher.
    """
    if not short_name or not short_name.strip():
        return None

    try:
        df = pd.read_csv(csv_path)
        if short_col not in df.columns or full_col not in df.columns:
            logger.warning(
                f"Columns '{short_col}' or '{full_col}' not found in {csv_path}"
            )
            return None

        short_names = df[short_col].dropna().astype(str).tolist()
        if not short_names:
            logger.debug(f"No short names found in column '{short_col}'")
            return None

        best_match = None
        best_score = 0.0

        for short in short_names:
            score = (
                difflib.SequenceMatcher(
                    None, short_name.strip().lower(), short.strip().lower()
                ).ratio()
                * 100
            )
            if score > best_score and score >= threshold:
                best_score = score
                best_match = df[df[short_col].astype(str) == short].iloc[0][full_col]

        if best_match:
            logger.debug(
                f"Found fuzzy short name match: '{short_name}' -> '{best_match}' (score: {best_score:.1f}%)"
            )
            return best_match
        else:
            logger.debug(
                f"No short name match found for '{short_name}' above threshold {threshold}% (best score: {best_score:.1f}%)"
            )
            return None
    except Exception as e:
        logger.error(f"Error in lookup_short_name_to_full: {e}")
        return None


def compare_all_names_difflib(input_name, csv_path, column_name, threshold=50.0):
    """
    Compares the input name against all facility names in the CSV using location-based preprocessing.
    First matches on preprocessed location keys (with District Name if available), then on full names.
    Returns the best match if the combined confidence score exceeds the threshold; otherwise, returns the original input_name.
    """
    if not input_name or not input_name.strip():
        return input_name

    try:
        # Load facility data
        df = pd.read_csv(csv_path)
        names = df[column_name].dropna().astype(str).tolist()

        if not names:
            logger.warning(f"No names found in CSV column '{column_name}'")
            return input_name

        input_key = preprocess_location(input_name)
        if not input_key:
            logger.debug(f"No key terms extracted from '{input_name}'")
            return input_name

        candidates = []
        has_district = "District Name" in df.columns

        for _, row in df.iterrows():
            facility_name = row[column_name]
            facility_key = preprocess_location(facility_name)

            # Base full similarity
            full_sim = difflib.SequenceMatcher(
                None, input_name.lower(), facility_name.lower()
            ).ratio()

            # Location similarity
            key_sim = difflib.SequenceMatcher(None, input_key, facility_key).ratio()

            # District similarity if available
            dist_sim = 0.0
            if has_district:
                district = str(row["District Name"]).lower()
                dist_sim = difflib.SequenceMatcher(None, input_key, district).ratio()
                location_sim = max(key_sim, dist_sim)
            else:
                location_sim = key_sim

            # Combined score: weight location higher for district-level matching
            combined_score = (location_sim * 0.6 + full_sim * 0.4) * 100

            if combined_score > threshold:
                candidates.append((facility_name, round(combined_score, 2)))

        if candidates:
            # Select the best match
            candidates.sort(key=lambda x: x[1], reverse=True)
            best_match, best_score = candidates[0]
            logger.debug(
                f"Correcting '{input_name}' to '{best_match}' (combined score: {best_score}%)"
            )
            return best_match
        else:
            logger.debug(
                f"Keeping original '{input_name}' (best combined score below threshold)"
            )
            return input_name

    except Exception as e:
        logger.error(f"Error in compare_all_names_difflib: {e}")
        return input_name


def run_langextract(
    input_text,
    model_id=MODEL_ID,
    facilities_csv="facilities.csv",
    health_complex_csv="upazila_health_complexes.csv",
    threshold=50.0,
):
    """
    Runs langextract on a single English referral text and corrects the 'referred_hospital' attribute
    using difflib-based mapping from a facilities CSV file if the confidence score exceeds the threshold.
    Also corrects the 'referrer_hospital' in referrer_info using a health_complex CSV.
    """
    if not input_text.strip():
        logger.warning("Empty input text provided to run_langextract")
        return {}

    try:
        result = lx.extract(
            text_or_documents=input_text,
            prompt_description=prompt,
            examples=examples,
            model_id=model_id,
            api_key=OPENAI_API_KEY,
            debug=False,
        )
        if not result.extractions:
            logger.warning("No extractions found from langextract")
            return {}

        attributes = result.extractions[0].attributes

        # Correct 'referred_hospital' if present
        if "referred_hospital" in attributes and attributes["referred_hospital"]:
            short_to_full = lookup_short_name_to_full(
                facilities_csv, attributes["referred_hospital"]
            )
            if short_to_full:
                attributes["referred_hospital"] = short_to_full
            else:
                corrected_hospital = compare_all_names_difflib(
                    attributes["referred_hospital"],
                    facilities_csv,
                    "Facility Name",
                    threshold,
                )
                attributes["referred_hospital"] = corrected_hospital

        # Correct 'referrer_hospital' in referrer_info if present
        if (
            "referrer_info" in attributes
            and "referrer_hospital" in attributes["referrer_info"]
            and attributes["referrer_info"]["referrer_hospital"]
        ):
            corrected_referrer_hospital = compare_all_names_difflib(
                attributes["referrer_info"]["referrer_hospital"],
                health_complex_csv,
                "Facility Name",
                threshold,
            )
            attributes["referrer_info"][
                "referrer_hospital"
            ] = corrected_referrer_hospital

        logger.debug("LangExtract completed successfully")
        return attributes
    except Exception as e:
        logger.error(f"Error in run_langextract: {e}")
        return {}


import io
import os
from datetime import datetime

from pydub import AudioSegment


# # -----------------------------
# # Transcription (Speech-to-Text - STT)
# # -----------------------------
# def transcribe_with_openai(audio_bytes):
#     """
#     Transcribe audio from bytes (e.g., received from a Streamlit microphone).
#     Converts WAV to MP3 to reduce file size, saves MP3 copy locally, then uses Whisper for English (en) transcription.
#     """
#     if not audio_bytes:
#         logger.warning("Empty audio bytes provided to transcribe_with_openai")
#         return ""

#     # Handle UploadedFile from Streamlit by extracting bytes
#     if hasattr(audio_bytes, "getvalue"):
#         audio_bytes = audio_bytes.getvalue()

#     # Create local directory for audio files if it doesn't exist
#     audio_dir = "./audio_files"
#     os.makedirs(audio_dir, exist_ok=True)

#     try:
#         # Load WAV bytes into AudioSegment
#         audio_segment = AudioSegment.from_wav(io.BytesIO(audio_bytes))

#         # Export to MP3 (128 kbps for good quality/size balance for voice)
#         mp3_buffer = io.BytesIO()
#         audio_segment.export(mp3_buffer, format="mp3", bitrate="128k")
#         mp3_bytes = mp3_buffer.getvalue()

#         # Generate unique filename with timestamp
#         timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
#         mp3_filename = f"{audio_dir}/recording_{timestamp_str}.mp3"

#         # Save MP3 copy locally
#         with open(mp3_filename, "wb") as f:
#             f.write(mp3_bytes)
#         logger.info(f"MP3 audio saved locally: {mp3_filename}")

#         # Transcribe the MP3 with OpenAI Whisper
#         response = client.audio.transcriptions.create(
#             model="whisper-1", file=("audio_input.mp3", mp3_bytes), language="en"
#         )
#         logger.info("Audio transcription completed successfully")
#         return response.text
#     except Exception as e:
#         logger.error(f"Transcription Error: {e}")
#         return ""
