# tts-backend/main.py
from fastapi import FastAPI, HTTPException, Request, File, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
import logging
import os
from datetime import datetime
from vosk import Model, KaldiRecognizer
import wave
import json
import edge_tts
import subprocess
import uuid
from task_processor import parse_project_tasks_from_transcription


app = FastAPI()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost:8000",
        "http://localhost:8002"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CLIENT_VOICE_DIRECTORY = '.'
TRANSCRIPTION_DIRECTORY = "transcriptions"
VOSK_MODEL_PATH = "models/vosk-model-small-pl-0.22"

# Ensure transcription directory exists
os.makedirs(TRANSCRIPTION_DIRECTORY, exist_ok=True)

# Load Vosk model
try:
    model = Model(VOSK_MODEL_PATH)
    logger.info("Vosk model loaded successfully")
except Exception as e:
    logger.error(f"Failed to load Vosk model: {e}")
    raise Exception("Failed to initialize Vosk model. Please ensure the model is downloaded and path is correct.")

# Pydantic model for text input
class TextInput(BaseModel):
    text: str
    voice: str = 'default'  # Default voice if not specified

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Updated exception handler to avoid decoding binary data.
    """
    logger.error(f"Validation error for request to {request.url}: {exc}")
    body = await request.body()
    if body and not body.isascii():
        # If it's likely binary, don't decode
        logger.error(f"Request body is possibly binary, length={len(body)} bytes")
    else:
        # Otherwise, attempt decode safely
        try:
            text_body = body.decode('utf-8')
            logger.error(f"Request body causing validation error: {text_body}")
        except UnicodeDecodeError:
            logger.error(f"Request body not valid UTF-8, length={len(body)} bytes")
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "body": "Invalid or missing fields."},
    )


@app.post("/synthesize")
async def synthesize(request: Request, input_text: TextInput):
    # Log the raw request body (assuming it's JSON text)
    body_bytes = await request.body()
    try:
        logger.info(f"Received request body: {body_bytes.decode('utf-8')}")
    except UnicodeDecodeError:
        logger.info(f"Received non-text request body, length={len(body_bytes)} bytes")

    text = input_text.text.strip()
    voice = input_text.voice

    if not text:
        logger.error("Received empty text input.")
        raise HTTPException(status_code=400, detail="Text cannot be empty.")

    voice_mapping = {
        'default': 'pl-PL-MarekNeural',
        'male': 'pl-PL-MarekNeural',
        'female': 'pl-PL-ZofiaNeural'
    }
    
    voice_name = voice_mapping.get(voice, 'pl-PL-MarekNeural')
    logger.info(f"Using voice: {voice_name} for synthesis.")

    try:
        communicate = edge_tts.Communicate(text=text, voice=voice_name)
        stream = communicate.stream()

        async def iterfile():
            async for chunk in stream:
                if chunk["type"] == "audio":
                    yield chunk["data"]

        headers = {
            'Content-Disposition': 'attachment; filename="output.mp3"',
            'Content-Type': 'audio/mpeg'
        }

        logger.info(f"Synthesizing speech for text: {text[:50]}...")
        return StreamingResponse(iterfile(), media_type="audio/mpeg", headers=headers)
    except Exception as e:
        logger.error(f"An error occurred during speech synthesis: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred during speech synthesis: {e}")


@app.post("/transcribe")
async def transcribe(filename: str):
    """
    This endpoint still expects a WAV file in the local directory,
    so it hasn't changed.
    """
    logger.info(f"Received transcription request for file: {filename}")
    try:
        file_path = os.path.join(CLIENT_VOICE_DIRECTORY, filename)
        if not os.path.exists(file_path):
            logger.warning(f"File not found: {file_path}")
            raise HTTPException(status_code=404, detail="File not found.")

        # Must be valid mono WAV 16k
        wf = wave.open(file_path, "rb")
        if wf.getnchannels() != 1 or wf.getsampwidth() != 2 or wf.getframerate() != 16000:
            logger.error("Invalid audio file format. Expected mono PCM with 16kHz sampling rate")
            raise HTTPException(status_code=400, detail="Audio file must be WAV format mono PCM with 16kHz sampling rate")

        # Transcribe using Vosk
        logger.info("Starting transcription process...")
        rec = KaldiRecognizer(model, wf.getframerate())
        rec.SetWords(True)

        transcription_results = []
        while True:
            data = wf.readframes(4000)
            if len(data) == 0:
                break
            if rec.AcceptWaveform(data):
                result = json.loads(rec.Result())
                logger.debug(f"Interim transcription result: {result.get('text', '')}")
                if 'text' in result and result['text'].strip():
                    transcription_results.append(result['text'])

        final_result = json.loads(rec.FinalResult())
        if 'text' in final_result and final_result['text'].strip():
            transcription_results.append(final_result['text'])

        transcribed_text = " ".join(transcription_results)
        
        # Save transcription to file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        transcription_filename = f"{timestamp}_transcription.txt"
        transcription_path = os.path.join(TRANSCRIPTION_DIRECTORY, transcription_filename)
        
        with open(transcription_path, "w", encoding="utf-8") as f:
            f.write(transcribed_text)
            
        logger.info(f"Transcription saved to: {transcription_path}")
        logger.info(f"Transcription completed for file {filename}: {transcribed_text[:50]}...")

        return {
            "message": "Transcription successful",
            "transcription": transcribed_text,
            "transcription_file": transcription_path
        }

    except Exception as e:
        logger.error(f"Error during transcription for file {filename}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to process the audio: {str(e)}")


@app.post("/streamTranscribe")
async def stream_transcribe(file: UploadFile = File(...)):
    logger.info(f"Received streaming transcription request for file: {file.filename}")

    # 1) Save .webm to a temporary path
    temp_id = str(uuid.uuid4())
    webm_path = f"/tmp/{temp_id}_{file.filename}"
    with open(webm_path, "wb") as f:
        f.write(await file.read())

    # 2) Convert webm -> wav using ffmpeg
    wav_path = f"/tmp/{temp_id}.wav"
    try:
        ffmpeg_command = [
            "ffmpeg",
            "-y",
            "-i", webm_path,
            "-ar", "16000",
            "-ac", "1",
            "-c:a", "pcm_s16le",
            wav_path
        ]
        subprocess.run(ffmpeg_command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        logger.info("Conversion from .webm to .wav successful.")
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg conversion failed: {e.stderr.decode('utf-8', errors='replace')}")
        raise HTTPException(status_code=500, detail="Failed to convert webm to wav.")

    # 3) Transcribe using Vosk
    try:
        wf = wave.open(wav_path, "rb")
        if wf.getnchannels() != 1 or wf.getsampwidth() != 2 or wf.getframerate() != 16000:
            logger.error("Invalid audio format after conversion. Must be 16kHz mono PCM.")
            raise HTTPException(
                status_code=400,
                detail="Audio file must be WAV format mono PCM with 16kHz sampling rate"
            )

        rec = KaldiRecognizer(model, wf.getframerate())
        rec.SetWords(True)

        transcription_results = []
        while True:
            data = wf.readframes(4000)
            if len(data) == 0:
                break
            if rec.AcceptWaveform(data):
                result = json.loads(rec.Result())
                if 'text' in result and result['text'].strip():
                    transcription_results.append(result['text'])

        final_result = json.loads(rec.FinalResult())
        if 'text' in final_result and final_result['text'].strip():
            transcription_results.append(final_result['text'])

        transcribed_text = " ".join(transcription_results)

        # 4) Optionally save the raw transcription file somewhere else
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        transcription_filename = f"{timestamp}_transcription.txt"
        transcription_path = os.path.join(TRANSCRIPTION_DIRECTORY, transcription_filename)
        with open(transcription_path, "w", encoding="utf-8") as f:
            f.write(transcribed_text)

        logger.info(f"Streaming transcription completed. Saved transcription to {transcription_path}")

        # 5) Parse tasks from the transcribed text
        tasks = parse_project_tasks_from_transcription(transcribed_text)
        logger.info(f"Parsed tasks: {tasks}")

        # 6) Save tasks to tasks_from_transcription.md in the **main folder**
        tasks_md_path = "tasks_from_transcription.md"  # No directory prefix
        logger.info(f"Appending tasks to {tasks_md_path}")

        with open(tasks_md_path, "a", encoding="utf-8") as md_file:
            if tasks:
                for t in tasks:
                    project_upper = t["project"].upper()
                    task_text = t["task_text"]
                    # e.g. - [ ] TEDXLUBLIN - posty zaplanować
                    md_file.write(f"- [ ] {project_upper} - {task_text}\n")
            else:
                # Fallback: if no hashtags, store a note
                md_file.write(f"- [ ] NOTATKA - {transcribed_text}\n")

        return {
            "message": "Transcription successful",
            "transcription": transcribed_text,
            "transcription_file": transcription_path,
            "tasks": tasks
        }

    except Exception as e:
        logger.error(f"Error during transcription: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process the audio stream: {str(e)}"
        )
    finally:
        # Clean up temp files
        if os.path.exists(webm_path):
            os.remove(webm_path)
        if os.path.exists(wav_path):
            os.remove(wav_path)




@app.get("/get-transcriptions")
async def get_transcriptions():
    try:
        transcription_files = os.listdir(TRANSCRIPTION_DIRECTORY)
        transcriptions = []
        
        for filename in transcription_files:
            file_path = os.path.join(TRANSCRIPTION_DIRECTORY, filename)
            with open(file_path, 'r', encoding='utf-8') as file:
                transcriptions.append({
                    "filename": filename,
                    "text": file.read(),
                    "date": filename.split("_")[0]  # Extract date from filename
                })

        return JSONResponse(content={"transcriptions": transcriptions})
    except Exception as e:
        logger.error(f"Error fetching transcriptions: {e}")
        return JSONResponse(status_code=500, content={"error": "Error fetching transcriptions"})


@app.get("/test")
async def test():
    logger.info("Test endpoint accessed")
    return {"message": "FastAPI server is working"}


if __name__ == "__main__":
    # Typically run with: uvicorn main:app --reload
    pass
