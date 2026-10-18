# Yashi — AI Companion

Yashi is an emotionally aware AI companion with a live 3D anime avatar. She chats like a friend
(short, warm, no "As an AI" talk), notices your mood, remembers what you tell her, talks back with
a natural voice, and reacts on screen — smiling, frowning, nodding, and lip-syncing as she speaks.

- **3D avatar** (VRM) with mood-driven expressions, lip-sync, blinking, breathing and gaze.
- **Interactive**: click her for a headpat, or use *Tease* / *Cheer*; a heart meter follows her mood.
- **Brains you can switch at runtime**: Ollama Cloud (default), Claude, a local Ollama model, or OpenAI.
- **Voice**: ElevenLabs (natural) with a browser-voice fallback; speech input via the browser or
  on-device Whisper (works in Brave and offline).
- **Memory**: conversation history, personal facts, semantic search and periodic reflections (SQLite).
- **Wake word**: say "Yashi" hands-free.

See [ARCHITECTURE.md](ARCHITECTURE.md) for how it fits together and [CONTEXT.md](CONTEXT.md) for
project decisions and history.

---

## Requirements

| | |
|---|---|
| Python | 3.11+ (developed on 3.13) |
| Node.js | 20+ (developed on 22) |
| Ollama | [ollama.com/download](https://ollama.com/download) — for the offline fallback brain |
| Browser | Chrome, Edge or Brave (desktop) |

Hardware that runs it comfortably: 8 GB RAM, a 4 GB GPU (e.g. GTX 1650) for the local model.

## Setup

```bash
# 1. Python packages (inside a virtual environment)
python -m venv .venv
.venv\Scripts\activate          # Windows   (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt

# 2. Frontend packages
cd frontend && npm install && cd ..

# 3. Local fallback model (used when the cloud brain is unreachable)
ollama pull llama3.2:3b

# 4. Keys
copy .env.example .env          # Linux/macOS: cp .env.example .env
```

Fill in `.env` (all optional except one brain):

| Variable | What it does |
|---|---|
| `OLLAMA_API_KEY` | Ollama Cloud — default brain (`kimi-k3`) |
| `OLLAMA_CLOUD_MODEL` | Optional; e.g. `gemma4:31b` for faster replies |
| `ANTHROPIC_API_KEY` | Claude brain |
| `OPENAI_API_KEY` | OpenAI brain |
| `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`, `ELEVENLABS_MODEL` | Natural voice |

Without any cloud key, Yashi still runs fully offline on `llama3.2:3b` with the browser voice.

## Run

```bash
python run.py
```

This starts the backend API on `http://localhost:8000` **and** the app on
**http://localhost:5173** — open that one. `Ctrl+C` stops both.

- `python run.py --api-only` — backend only (then `cd frontend && npm run dev` yourself).
- `python desktop.py` — the same app in a native window (needs `pip install pywebview`).

There is exactly one UI: the Vite app in `frontend/`. The backend never serves its own copy;
visiting `:8000` redirects to the app.

## Using Yashi

- **Chat** — type, or click **Mic**. In Chrome/Edge the browser recognises speech; in Brave (or
  the desktop app) it's transcribed on your PC by Whisper.
- **Wake word** — click *Wake word*, then say "Yashi", wait for the chime and talk — or say it in
  one breath ("Yashi, how was your day?").
- **Reactions** — click Yashi for a headpat; *Tease* makes her pout, *Cheer* makes her light up.
- **Focus** — full-screen stage with the chat floating on top.
- **Settings** — switch brain and voice, and open memory (facts, reflections) and health check.
- **Commands** — "open notepad", "play lofi on spotify", "search the web for …", "find file
  report.pdf". Ordinary sentences always go to the conversation, not to commands.

## Configuration

`config/settings.py` holds the defaults (model names, memory limits, safety limits, persona).
The brain/voice picked in *Settings* is applied immediately and saved back to this file.

## Tests

```bash
pip install pytest
python -m pytest tests -q
```

## Privacy & security

- The backend listens on `127.0.0.1` only and accepts API calls only from the Yashi app
  (CORS-restricted) — it can open apps and files, so it is never exposed to your network.
- Memory lives in `data/yashi.db` on your machine. Cloud brains (Ollama Cloud, Claude, OpenAI)
  and ElevenLabs receive the conversation text; the local model and Whisper do not send anything.
- `.env`, the database and the TTS cache are git-ignored.

## Credits & licence

- Code: GNU GPL v3 — see [COPYING](COPYING).
- Avatar: **AvatarSample_A** © pixiv Inc. / VRoid Project, used under its
  [conditions of use](https://vroid.pixiv.help/hc/en-us/articles/4402394424089) (free for any use,
  no credit required; not CC0).
- Built with FastAPI, React, Vite, Tailwind CSS, three.js, @pixiv/three-vrm, GSAP, faster-whisper
  and sentence-transformers.
