"""
Yashi Test Suite — run with: python -m pytest tests/ -v
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest, asyncio, numpy as np

def run(coro): return asyncio.get_event_loop().run_until_complete(coro)

# ── Config ─────────────────────────────────────────────────────────────────────
def test_config_loads():
    from config.settings import YASHI_NAME, EMBEDDING_MODEL
    assert YASHI_NAME == "Yashi"
    assert EMBEDDING_MODEL == "all-MiniLM-L6-v2"

# ── Fact extractor ─────────────────────────────────────────────────────────────
def test_fact_extraction_name():
    from core.memory.fact_extractor import extract_facts
    facts = extract_facts("My name is Alex and I'm 25 years old.")
    cats = [f[0] for f in facts]
    assert "name" in cats and "age" in cats

def test_fact_extraction_job():
    from core.memory.fact_extractor import extract_facts
    facts = extract_facts("I work as a software developer.")
    assert any(f[0] == "job" for f in facts)

# ── Sentiment ──────────────────────────────────────────────────────────────────
def test_sentiment_positive():
    from core.emotion.text_sentiment import analyse_sentiment
    r = analyse_sentiment("I feel wonderful and happy today!")
    assert r["label"] == "POSITIVE"

def test_sentiment_negative():
    from core.emotion.text_sentiment import analyse_sentiment
    r = analyse_sentiment("I'm really sad and feeling terrible.")
    assert r["label"] == "NEGATIVE"

def test_sentiment_has_emotion_key():
    from core.emotion.text_sentiment import analyse_sentiment
    r = analyse_sentiment("It is a regular day.")
    assert "emotion" in r

# ── Voice energy ───────────────────────────────────────────────────────────────
def test_voice_energy_silence():
    from core.emotion.voice_energy import compute_energy
    assert compute_energy(np.zeros(1600, dtype=np.int16)) < 0.01

def test_voice_energy_loud():
    from core.emotion.voice_energy import compute_energy
    assert compute_energy((np.random.rand(1600)*20000).astype(np.int16)) > 0.1

# ── Emotion fusion ─────────────────────────────────────────────────────────────
def test_emotion_fusion_keys():
    from core.emotion.fusion_engine import fuse
    r = fuse("I'm so happy today!")
    for k in ("current_emotion","emotional_state","emotional_trend","valence"):
        assert k in r

# ── Cognitive ──────────────────────────────────────────────────────────────────
def test_complexity_light():
    from core.cognitive.complexity_analyzer import analyse_complexity
    assert analyse_complexity("Open Chrome")["suggested_mode"] == "light"

def test_complexity_support():
    from core.cognitive.complexity_analyzer import analyse_complexity
    r = analyse_complexity("I'm feeling so depressed and alone.")
    assert r["suggested_mode"] == "support"

def test_mode_selector_light():
    from core.cognitive.mode_selector import select_cognitive_mode
    mode = select_cognitive_mode("Launch Spotify", {"emotional_state":"stable","current_emotion":"neutral"})
    assert mode == "light"

def test_mode_selector_support():
    from core.cognitive.mode_selector import select_cognitive_mode
    mode = select_cognitive_mode("I feel hopeless", {"emotional_state":"distress","current_emotion":"distressed"})
    assert mode == "support"

# ── Safety ─────────────────────────────────────────────────────────────────────
def test_safety_clean(tmp_path):
    from config import settings as s; s.DATABASE_PATH = tmp_path/"s.db"
    from core.memory.database import initialize_database; initialize_database()
    from core.safety.safety_monitor import check_message
    r = check_message("How's the weather?", {"emotional_state":"stable","current_emotion":"neutral"}, "sess1")
    assert r["should_respond"] and r["severity"] == "none"

def test_safety_dependency(tmp_path):
    from config import settings as s; s.DATABASE_PATH = tmp_path/"d.db"
    from core.memory.database import initialize_database; initialize_database()
    from core.safety.safety_monitor import check_message
    r = check_message("you're the only one who understands me",{"emotional_state":"stable","current_emotion":"neutral"},"sess2")
    assert r["severity"] == "gentle"

def test_filter_response():
    from core.safety.safety_monitor import filter_response
    assert "you need me" not in filter_response("Here to support you.").lower()

# ── Intent / Plugin ────────────────────────────────────────────────────────────
def test_intent_open_app():
    from plugins.intent_detector import detect_intent
    r = detect_intent("open Chrome")
    assert r and r["intent"] == "open_app"

def test_intent_web_search():
    from plugins.intent_detector import detect_intent
    r = detect_intent("search the web for Python tutorials")
    assert r and r["intent"] == "open_url"

def test_intent_youtube_search_open_and_search():
    from plugins.intent_detector import detect_intent
    r = detect_intent("open youtube and search lofi coding music")
    assert r and r["intent"] == "youtube_search"
    assert "lofi coding music" in r["target"].lower()

def test_intent_youtube_search_on_site():
    from plugins.intent_detector import detect_intent
    r = detect_intent("search lofi hip hop on youtube")
    assert r and r["intent"] == "youtube_search"
    assert "lofi hip hop" in r["target"].lower()

def test_intent_open_website_on_browser():
    from plugins.intent_detector import detect_intent
    r = detect_intent("open github on browser")
    assert r and r["intent"] == "open_website"
    assert r["target"].lower() == "github"

def test_intent_open_website_phrase_variant():
    from plugins.intent_detector import detect_intent
    r = detect_intent("open website reddit")
    assert r and r["intent"] == "open_website"
    assert r["target"].lower() == "reddit"

def test_spotify_generic_target_detection():
    from plugins.app_launcher.plugin import _is_generic_spotify_target
    assert _is_generic_spotify_target("any music")
    assert _is_generic_spotify_target("playlist")
    assert not _is_generic_spotify_target("shape of you")

def test_intent_find_file():
    from plugins.intent_detector import detect_intent
    r = detect_intent("find file report.pdf")
    assert r and r["intent"] == "find_file"

def test_intent_file_write():
    from plugins.intent_detector import detect_intent
    r = detect_intent("write Hello world to file notes.txt")
    assert r and r["intent"] == "file_write"
    assert r["extra"].lower() == "notes.txt"

def test_intent_file_append():
    from plugins.intent_detector import detect_intent
    r = detect_intent("append another line to file notes.txt")
    assert r and r["intent"] == "file_append"

def test_intent_no_match():
    from plugins.intent_detector import detect_intent
    assert detect_intent("How are you feeling today?") is None

def test_plugin_loader():
    from plugins.plugin_loader import load_all_plugins
    names = [p.name for p in load_all_plugins()]
    assert "app_launcher" in names
    assert "web_launcher" in names
    assert "file_search" in names

# ── Prompt builder ─────────────────────────────────────────────────────────────
def test_prompt_builder():
    from core.llm.prompt_builder import build_system_prompt, build_chat_messages
    sys_p = build_system_prompt(
        semantic_memories=[("I like hiking", 0.85)],
        personal_facts=[{"category":"name","fact":"Alex","confidence":1.0}],
        recent_reflections=[],
        emotion_state={"current_emotion":"neutral","emotional_state":"stable"},
        cognitive_mode="standard",
        user_message="Tell me about yourself.",
    )
    assert "Yashi" in sys_p and "Alex" in sys_p and "hiking" in sys_p
    msgs = build_chat_messages("Tell me about yourself.",
                               [{"role":"user","content":"Hi"},{"role":"assistant","content":"Hello!"}])
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert msgs[-1]["content"] == "Tell me about yourself."

# ── Reply cleanup ─────────────────────────────────────────────────────────────
def test_strip_emojis_and_emphasis():
    from core.safety.safety_monitor import filter_response
    assert filter_response("**YESSS!** that’s amazing 🎉") == "YESSS! that’s amazing"
    assert filter_response("café résumé — fine") == "café résumé — fine"
    assert filter_response("snake_case_name stays") == "snake_case_name stays"

def test_strip_emojis_streamed_tokens():
    from core.safety.safety_monitor import strip_emojis
    assert "".join(strip_emojis(t) for t in ["**", "YES", "S!*", "*", " 👍🏽"]) == "YESS! "

# ── TTS file serving must not escape the cache folder ────────────────────────
def test_tts_serve_blocks_traversal():
    from app.routes.tts_serve import serve_tts
    for name in ["../../.env", r"..\..\.env", "../yashi.db", "missing.mp3"]:
        assert serve_tts(name).status_code == 404

# ── Brains: cloud APIs only, fallback order follows configured keys ──────────
def test_configured_backends_fallback_order(monkeypatch):
    import config.settings as settings
    from core.conversation.engine import configured_backends
    monkeypatch.setattr(settings, "OLLAMA_API_KEY", "k")
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "k")
    assert configured_backends() == ["ollama_cloud", "openai"]

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
