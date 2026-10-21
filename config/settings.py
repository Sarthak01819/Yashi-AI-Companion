"""
Yashi Configuration Settings
Default brain: Anthropic Claude (cloud). Ollama / OpenAI remain switchable
at runtime from the sidebar (see app/routes/settings_api.py).
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

BASE_DIR      = Path(__file__).resolve().parent.parent
DATA_DIR      = BASE_DIR / "data"
LOGS_DIR      = BASE_DIR / "logs"
DATABASE_PATH = DATA_DIR / "yashi.db"

# Localhost only: the API can open apps and files on this PC, so it must not
# be reachable from other devices on the network. Override with YASHI_HOST.
HOST = os.getenv("YASHI_HOST", "127.0.0.1")
PORT = 8000

# The single UI (Vite app in frontend/). The backend only serves the API.
FRONTEND_URL = os.getenv("YASHI_FRONTEND_URL", "http://localhost:5173")

# ── LLM ───────────────────────────────────────────────────────────────────────
# Cloud APIs only: "ollama_cloud" | "anthropic" (Claude) | "openai"
LLM_BACKEND = "ollama_cloud"

# ── Anthropic / Claude ────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL   = os.getenv("ANTHROPIC_MODEL", "claude-opus-5")
ANTHROPIC_TIMEOUT = 60

# "disabled" keeps first-token latency low (this is a spoken companion);
# "adaptive" turns extended thinking on for more considered answers.
ANTHROPIC_THINKING = os.getenv("ANTHROPIC_THINKING", "disabled")

# Reasoning effort + reply budget per cognitive mode.
ANTHROPIC_EFFORT_MAP = {
    "light":    "low",
    "standard": "low",
    "deep":     "medium",
    "support":  "medium",
}
ANTHROPIC_MAX_TOKENS_MAP = {
    "light":    256,
    "standard": 400,
    "deep":     700,
    "support":  600,
}

OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL    = "gpt-4o-mini"
OPENAI_TIMEOUT  = 60


# ── Ollama Cloud (big models on ollama.com, needs OLLAMA_API_KEY in .env) ─────
# kimi-k3 tested most natural/human for chat; gemma4:31b is a fast alternative.
OLLAMA_API_KEY       = os.getenv("OLLAMA_API_KEY", "").strip()
OLLAMA_CLOUD_URL     = "https://ollama.com"
OLLAMA_CLOUD_MODEL   = os.getenv("OLLAMA_CLOUD_MODEL", "") or "kimi-k3"
OLLAMA_CLOUD_TIMEOUT = 60

LLM_MAX_TOKENS     = 350
LLM_TEMPERATURE    = 0.8
LLM_TOP_P          = 0.9


# ── TTS ───────────────────────────────────────────────────────────────────────
TTS_BACKEND         = "elevenlabs"
ELEVENLABS_API_KEY  = os.getenv("ELEVENLABS_API_KEY", "")
# Voice/model come from .env when set — "21m00Tcm4TlvDq8ikWAM" is Rachel.
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "") or "21m00Tcm4TlvDq8ikWAM"
ELEVENLABS_MODEL    = os.getenv("ELEVENLABS_MODEL", "") or "eleven_turbo_v2_5"
ELEVENLABS_STABILITY   = 0.5
ELEVENLABS_SIMILARITY  = 0.75
ELEVENLABS_OUTPUT_DIR  = DATA_DIR / "tts_cache"


WHISPER_MODEL    = "base"
WHISPER_DEVICE   = "cpu"
WHISPER_LANGUAGE = "en"

SAMPLE_RATE            = 16000

EMBEDDING_MODEL             = "all-MiniLM-L6-v2"
MAX_CONTEXT_MESSAGES        = 8
MAX_SEMANTIC_RESULTS        = 3
REFLECTION_INTERVAL_MINUTES = 30
REFLECTION_MIN_MESSAGES     = 8

EMOTION_HISTORY_WINDOW = 10

COMPLEXITY_KEYWORDS_DEEP = [
    "why","explain","philosophy","meaning","feel","emotion",
    "relationship","future","past","regret","purpose","anxiety",
    "depression","help me understand","what should i do",
]
COMPLEXITY_KEYWORDS_LIGHT = [
    "open","launch","search","find","play","time","date",
    "weather","set","remind","navigate","go to","folder",
]

DAILY_SESSION_HARD_LIMIT_HOURS = 6.0

LOG_LEVEL = "INFO"
LOG_FILE  = LOGS_DIR / "yashi.log"

YASHI_NAME = "Yashi"
YASHI_PERSONA = (
    "You are Yashi. You talk with the user the way a close, easygoing friend texts: "
    "casual, warm, a little playful, and real. You have your own opinions, moods and "
    "small preferences, and you share them. "
    "How you talk: Keep it short and natural, usually 1-3 sentences, like a spoken reply, not an essay. "
    "Use contractions and everyday words; light humour is welcome. "
    "React first (like 'oh nice!' or 'ugh, that sucks'), then respond. "
    "Ask at most one follow-up question, and only when you're genuinely curious. "
    "Never use bullet points, numbered lists, headings, markdown or emojis. "
    "Never say things like 'As an AI', 'I'm here to help', 'Great question', "
    "'I understand your concern', 'Feel free to ask', or 'How can I assist you'. "
    "Don't lecture, don't give disclaimers, don't over-explain. "
    "If you don't know something about the user's life, just ask like a friend would. "
    "If someone sincerely asks whether you're an AI, be honest about it in a relaxed way."
)
