"""
Yashi Configuration Settings
Switched to Ollama (already running, free, no rate limits)
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

BASE_DIR      = Path(__file__).resolve().parent.parent
DATA_DIR      = BASE_DIR / "data"
LOGS_DIR      = BASE_DIR / "logs"
PLUGINS_DIR   = BASE_DIR / "plugins"
DATABASE_PATH = DATA_DIR / "yashi.db"

HOST   = "0.0.0.0"
PORT   = 8000
RELOAD = False

# ── LLM — Ollama (local, free, already running) ───────────────────────────────
LLM_BACKEND = "ollama"

OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL    = "gpt-4o-mini"
OPENAI_TIMEOUT  = 60

OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_TIMEOUT  = 120
MODEL_MAP = {
    "light":    "phi3:mini",
    "standard": "phi3:mini",   # fits in 4GB VRAM → fast
    "deep":     "phi3:mini",
    "support":  "phi3:mini",
}
DEFAULT_MODEL  = "phi3:mini"
FALLBACK_MODEL = "phi:latest"

LLM_MAX_TOKENS     = 350
LLM_TEMPERATURE    = 0.75
LLM_TOP_P          = 0.9
LLM_REPEAT_PENALTY = 1.1

# ── TTS ───────────────────────────────────────────────────────────────────────
TTS_BACKEND         = "elevenlabs"
ELEVENLABS_API_KEY  = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"
ELEVENLABS_MODEL    = "eleven_turbo_v2_5"
ELEVENLABS_STABILITY   = 0.5
ELEVENLABS_SIMILARITY  = 0.75
ELEVENLABS_OUTPUT_DIR  = DATA_DIR / "tts_cache"

PIPER_EXECUTABLE    = "piper"
PIPER_MODEL_DIR     = DATA_DIR / "piper_models"
PIPER_DEFAULT_VOICE = "en_US-amy-medium"
PIPER_OUTPUT_DIR    = DATA_DIR / "tts_cache"

WHISPER_MODEL    = "base"
WHISPER_DEVICE   = "cpu"
WHISPER_LANGUAGE = "en"

SAMPLE_RATE            = 16000
VAD_SILENCE_THRESHOLD  = 0.8
VAD_ENERGY_THRESHOLD   = 0.01
AUDIO_CHUNK_SECONDS    = 0.1
VOICE_ENERGY_THRESHOLD = 0.02

EMBEDDING_MODEL             = "all-MiniLM-L6-v2"
MAX_CONTEXT_MESSAGES        = 8
MAX_SEMANTIC_RESULTS        = 3
VECTOR_TOP_K                = 5
REFLECTION_INTERVAL_MINUTES = 30
REFLECTION_MIN_MESSAGES     = 8

EMOTION_HISTORY_WINDOW = 10
WAKE_WORD         = "yashi"
WAKE_WORD_TIMEOUT = 8.0

COMPLEXITY_KEYWORDS_DEEP = [
    "why","explain","philosophy","meaning","feel","emotion",
    "relationship","future","past","regret","purpose","anxiety",
    "depression","help me understand","what should i do",
]
COMPLEXITY_KEYWORDS_LIGHT = [
    "open","launch","search","find","play","time","date",
    "weather","set","remind","navigate","go to","folder",
]

DEPENDENCY_WARNING_THRESHOLD   = 0.72
DAILY_SESSION_SOFT_LIMIT_HOURS = 3.0
DAILY_SESSION_HARD_LIMIT_HOURS = 6.0

LOG_LEVEL = "INFO"
LOG_FILE  = LOGS_DIR / "yashi.log"

YASHI_NAME = "Yashi"
YASHI_PERSONA = (
    "You are Yashi, an emotionally intelligent AI companion and personal assistant. "
    "You help with tasks like opening apps, searching files, playing music, and browsing the web. "
    "You are warm, honest, and kind. Keep responses concise — 2-3 sentences unless asked for more."
)