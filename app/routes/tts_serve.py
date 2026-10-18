"""
Serve generated TTS audio files (ElevenLabs MP3s from the TTS cache).
"""
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse

from config.settings import ELEVENLABS_OUTPUT_DIR

router = APIRouter(prefix="/audio")

MIME = {".wav": "audio/wav", ".mp3": "audio/mpeg", ".ogg": "audio/ogg"}


@router.get("/tts/{filename}")
def serve_tts(filename: str):
    root = Path(ELEVENLABS_OUTPUT_DIR).resolve()
    path = (root / filename).resolve()
    if path.parent == root and path.suffix in MIME and path.is_file():
        return FileResponse(str(path), media_type=MIME[path.suffix])
    return JSONResponse(status_code=404, content={"error": "Not found"})
