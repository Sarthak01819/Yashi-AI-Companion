"""
Serve generated TTS audio files (both .wav and .mp3 from ElevenLabs).
"""
from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path
from config.settings import ELEVENLABS_OUTPUT_DIR, PIPER_OUTPUT_DIR

router = APIRouter(prefix="/audio")

MIME = {".wav": "audio/wav", ".mp3": "audio/mpeg", ".ogg": "audio/ogg"}

@router.get("/tts/{filename}")
def serve_tts(filename: str):
    for search_dir in [ELEVENLABS_OUTPUT_DIR, PIPER_OUTPUT_DIR]:
        path = Path(search_dir) / filename
        if path.exists() and path.suffix in MIME:
            return FileResponse(str(path), media_type=MIME[path.suffix])
    return JSONResponse(status_code=404, content={"error": "Not found"})
