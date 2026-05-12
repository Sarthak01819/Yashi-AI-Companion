# ✦ Yashi — Local AI Companion

A fully local, emotionally intelligent AI companion running on your own hardware.
Private by design. No cloud. No subscriptions.

---

## 🖥️ Hardware Requirements

| Component | Minimum           | Recommended         |
|-----------|-------------------|---------------------|
| RAM       | 8 GB              | 16 GB               |
| GPU       | GTX 1650 (4 GB)   | RTX 3060 (8 GB)     |
| CPU       | Ryzen 5 5600H     | Any modern 6-core   |
| Storage   | 10 GB free        | 20 GB free          |
| OS        | Windows 10/11     | Windows 11 / Ubuntu |

---

## ⚡ Quick Start

### 1. Clone / place the project
```bash
cd Yashi/
```

### 2. Install dependencies

**Windows:**
```bat
setup.bat
```

**Linux/macOS:**
```bash
bash setup.sh
```

### 3. Install Ollama

Download from https://ollama.com/download

```bash
# Pull models (do this once)
ollama pull mistral:7b-instruct-v0.2-q4_K_M   # ~4.1 GB — primary model
ollama pull phi3:mini                           # ~2.3 GB — fast/light tasks
```

### 4. Install Piper TTS (optional — for voice output)

```bash
# Option A: pip package
pip install piper-tts

# Option B: binary from https://github.com/rhasspy/piper/releases
# Place piper.exe (Windows) or piper (Linux) on your PATH
```

Download a voice model:
```bash
# Place in data/piper_models/
# Example: https://huggingface.co/rhasspy/piper-voices
# Download en_US-amy-medium.onnx and en_US-amy-medium.onnx.json
```

### 5. Start Ollama

```bash
ollama serve   # keep this running in a separate terminal
```

### 6. Launch Yashi

```bash
# Activate venv first
source venv/bin/activate      # Linux/macOS
venv\Scripts\activate.bat     # Windows

python run.py
```

Open your browser: **http://localhost:8000**

---

## 🧱 Project Structure

```
Yashi/
├── app/
│   ├── main.py                  FastAPI app + lifespan startup
│   ├── websocket_manager.py     WS connection manager
│   └── routes/
│       ├── chat.py              Text chat WebSocket /ws/chat/{id}
│       ├── audio.py             Voice WebSocket /ws/audio/{id}
│       ├── memory_api.py        REST: facts, reflections, history
│       └── tts_serve.py         REST: serve TTS audio files
│
├── core/
│   ├── llm/
│   │   ├── ollama_client.py     Async Ollama API client + streaming
│   │   ├── model_router.py      Selects model based on cognitive mode
│   │   └── prompt_builder.py    Constructs system + user prompts
│   ├── memory/
│   │   ├── database.py          SQLite init + WAL mode
│   │   ├── conversation_store.py Store/retrieve dialogue history
│   │   ├── semantic_memory.py   Embedding-based memory search (SQLite blobs)
│   │   ├── fact_extractor.py    Regex-based personal fact extraction
│   │   └── reflection_engine.py Periodic conversation analysis
│   ├── emotion/
│   │   ├── text_sentiment.py    DistilBERT sentiment (+ heuristic fallback)
│   │   ├── voice_energy.py      RMS energy + ZCR from audio
│   │   └── fusion_engine.py     Combines signals → unified emotion state
│   ├── cognitive/
│   │   ├── complexity_analyzer.py  Detects topic complexity
│   │   └── mode_selector.py        Selects light/standard/deep/support
│   ├── safety/
│   │   └── safety_monitor.py    Dependency detection + response filtering
│   ├── voice/
│   │   ├── vad.py               Simple energy-based VAD
│   │   ├── stt.py               faster-whisper transcription
│   │   └── tts.py               Piper TTS (subprocess + caching)
│   └── conversation/
│       └── engine.py            Full pipeline orchestrator (streaming)
│
├── plugins/
│   ├── base_plugin.py           Abstract plugin interface
│   ├── intent_detector.py       Regex intent matcher
│   ├── plugin_loader.py         Dynamic discovery + dispatch
│   ├── app_launcher/plugin.py   Open local apps
│   ├── web_launcher/plugin.py   Open URLs / search the web
│   └── file_search/plugin.py    Find files on disk
│
├── frontend/
│   ├── index.html               Single-page app
│   ├── css/yashi.css            Dark organic theme
│   └── js/
│       ├── avatar.js            SVG avatar: blink, breathe, eye-track, lip-sync
│       ├── audio_capture.js     Mic → PCM → base64 → WebSocket
│       └── yashi_client.js      WS client, UI state, message rendering
│
├── tests/
│   └── test_all.py              35+ unit tests
│
├── config/settings.py           Central configuration
├── requirements.txt
├── run.py
├── setup.sh
└── setup.bat
```

---

## 🧪 Running Tests

```bash
python -m pytest tests/ -v
```

Tests cover: config, emotion, cognitive, safety, VAD, plugins, prompt builder, model router.

*Note: tests that require the embedding model or Ollama are integration-level and will be
skipped automatically if the dependencies are not installed.*

---

## 🎯 Cognitive Modes

| Mode     | Trigger                              | Behaviour                           |
|----------|--------------------------------------|-------------------------------------|
| light    | Task commands (open, find, search)   | Concise, fast, phi3:mini            |
| standard | Normal conversation                  | Natural, balanced                   |
| deep     | Philosophy, explanation, meaning     | Thoughtful, nuanced, asks follow-up |
| support  | Distress/anxiety/sadness detected    | Empathy-first, validating           |

---

## 🧠 Memory System

| Table             | Contents                                    |
|-------------------|---------------------------------------------|
| conversations     | Full dialogue history + emotion tags        |
| memory_vectors    | Embedded memories (cosine search)           |
| personal_facts    | Name, age, job, hobbies, goals…             |
| reflections       | Periodic insights from conversation         |
| behavior_state    | Key-value runtime state                     |
| session_stats     | Session duration tracking (safety)          |

Access via API:
- `GET /api/memory/facts`
- `GET /api/memory/reflections`
- `GET /api/memory/search?q=hiking`
- `GET /api/memory/history/{session_id}`

---

## 📡 WebSocket Protocol

### Text Chat: `ws://localhost:8000/ws/chat/{client_id}`

**Send:**
```json
{ "type": "text",        "text": "Hello Yashi" }
{ "type": "stop"                                }
{ "type": "new_session"                         }
{ "type": "ping"                                }
```

**Receive:**
```json
{ "type": "connected",     "session": "...", "message": "..." }
{ "type": "emotion",       "current_emotion": "happy", "emotional_state": "positive", ... }
{ "type": "thinking",      "mode": "standard" }
{ "type": "token",         "text": "word"   }
{ "type": "done",          "full_text": "...", "audio_path": "...", "emotion": "...", "elapsed": 1.2, "stopped": false }
{ "type": "safety",        "note": "..."    }
{ "type": "plugin_response","message": "..."  }
```

### Voice: `ws://localhost:8000/ws/audio/{client_id}`

Send base64-encoded PCM int16 chunks at 16 kHz mono:
```json
{ "type": "audio", "audio_chunk": "<base64>" }
```

---

## 🔌 Adding Plugins

Create `plugins/my_plugin/plugin.py`:

```python
from plugins.base_plugin import YashiPlugin

class Plugin(YashiPlugin):
    name = "my_plugin"
    description = "Does something cool"
    trigger_phrases = ["keyword1", "keyword2"]

    async def can_handle(self, text, intent=None):
        return intent == "my_intent" or "keyword1" in text.lower()

    async def execute(self, text, context):
        # Do work here
        return {
            "success": True,
            "message": "Done! Here's what I found.",
            "data": { "result": "..." },
        }
```

Yashi auto-discovers it on next startup.

---

## 🔮 Future Upgrades

| Feature                  | Notes                                                          |
|--------------------------|----------------------------------------------------------------|
| Live2D avatar            | Replace SVG with Cubism SDK; hook into `window.YASHI_LIVE2D`  |
| OpenCV face emotion      | Add `fer` library; feed into `fusion_engine.fuse()`           |
| Multiple voices (Piper)  | Map emotions to different voice models in `tts.py`            |
| Better embeddings        | Switch to `all-mpnet-base-v2` if RAM permits (~420 MB)        |
| Persistent sessions      | Store session IDs in browser localStorage                      |
| Wake-word activation     | Add `porcupine` or `openWakeWord` before `AudioCapture.start()`|
| GPU acceleration         | Set `WHISPER_DEVICE=cuda`, `COGNITIVE_DEVICE=cuda`             |
| Calendar / reminders     | New plugin using `schedule` or Windows Task Scheduler          |
| Home Assistant bridge    | Plugin to control smart home via HA REST API                   |
| Streaming TTS (real-time)| Sentence-chunk the LLM stream and synthesise each sentence     |

---

## 💙 Design Philosophy

Yashi is built on the principle that an AI companion should:

1. **Empower**, not entrench. Encourage real-world connections and personal growth.
2. **Be honest**. Never pretend to be human or create false intimacy.
3. **Respect limits**. Gentle nudges when session time or dependency patterns emerge.
4. **Stay private**. Everything runs locally. No data ever leaves your machine.

---

*Built with ❤️ for low-resource, high-empathy AI.*
