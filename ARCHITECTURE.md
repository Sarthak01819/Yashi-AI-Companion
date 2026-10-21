# Yashi — Architecture

Two processes, one UI:

```
 Browser / desktop window
 ┌──────────────────────────────────────────────────────────────────┐
 │  frontend/  (Vite + React)            http://localhost:5173      │
 │   App.jsx ─ chat, settings, voice     avatar/ ─ 3D VRM + motion  │
 │   voice/whisperListener.js            ui/motion.js ─ GSAP        │
 └───────────────┬──────────────────────────────────────────────────┘
                 │  Vite dev proxy: /api  /audio  /health  /ws
 ┌───────────────▼──────────────────────────────────────────────────┐
 │  backend (FastAPI, API only)          http://127.0.0.1:8000      │
 │   /ws/chat ─▶ ConversationEngine ─▶ emotion · safety · memory    │
 │                                   ─▶ prompt ─▶ LLM (streamed)    │
 │                                   ─▶ sentence TTS (ElevenLabs)   │
 │   /api/stt (Whisper) · /api/settings · /api/memory · /audio/tts  │
 └───────────────┬───────────────────────────┬──────────────────────┘
                 │                           │
        data/yashi.db (SQLite)     Ollama Cloud / Claude /
        data/tts_cache/*.mp3       OpenAI · ElevenLabs
```

`python run.py` starts both processes. The backend never serves UI files; `GET /` on it redirects
to the frontend.

## Repository layout

```
app/                    FastAPI app
  main.py               startup (backend checks, model warm-up), CORS, /health, / -> frontend
  websocket_manager.py  connected chat sockets
  routes/
    chat.py             /ws/chat/{client_id} — plugins first, then the conversation engine
    stt_api.py          POST /api/stt — raw 16 kHz PCM -> Whisper text
    settings_api.py     GET/POST /api/settings — switch brain / voice at runtime
    memory_api.py       GET /api/memory/* — facts, reflections, search, history
    tts_serve.py        GET /audio/tts/{file} — cached ElevenLabs MP3s
config/settings.py      all defaults (models, limits, persona); reads .env
core/
  conversation/engine.py  the per-message pipeline (below)
  llm/                    ollama_client (Ollama Cloud), anthropic_client, openai_client,
                          prompt_builder (system prompt + chat turns)
  emotion/                text_sentiment (DistilBERT), voice_energy, fusion_engine
  cognitive/              complexity_analyzer + mode_selector -> light/standard/deep/support
  memory/                 database (SQLite), conversation_store, semantic_memory (MiniLM
                          embeddings), fact_extractor, reflection_engine
  safety/safety_monitor   session limits, dependency redirects, reply cleanup
  voice/                  elevenlabs_tts (TTS), stt (faster-whisper)
plugins/                  app_launcher, web_launcher, file_ops, file_search + intent_detector
frontend/
  src/App.jsx             UI: stage HUD, dialogue, composer, settings sheet, mic & wake word
  src/avatar/VrmAvatar.jsx    three.js scene, VRM loading, camera framing (lazy-loaded)
  src/avatar/avatarMotion.js  procedural animation: springs, breathing, gaze, blinks,
                              lip-sync, expressions, reactions
  src/voice/whisperListener.js  mic capture + voice-activity detection -> /api/stt
  src/ui/motion.js        GSAP helpers (entrances, hearts, meter, sheet, mic level ring)
  public/models/AvatarSample_A.vrm, public/yashi-avatar.mp4 (WebGL fallback)
tests/test_all.py         unit tests (emotion, cognition, safety, intents, prompt, security)
run.py · desktop.py       launchers
```

## A message, end to end

1. **Input.** Typed text, or speech: Chrome/Edge use the Web Speech API; Brave and the desktop
   app record the mic, cut sentences with a small energy VAD and POST them to `/api/stt`
   (faster-whisper `base`, hotword "Yashi").
2. **Wake word.** In wake mode only finished sentences are inspected. "Yashi …" sends the rest;
   a bare "Yashi" chimes and arms the next sentence (12 s). Common mishearings ("yes she",
   "Yasi") are matched only at the start of a sentence.
3. **Socket.** The UI sends `{type: "text"}` on `/ws/chat`. `chat.py` first runs the intent
   detector; only anchored, unambiguous commands for things that exist ("open notepad") are
   handled by plugins. Everything else goes to the engine.
4. **Engine** (`core/conversation/engine.py`):
   - emotion = fuse(text sentiment, optional voice energy) -> label + valence -> `emotion` event
   - safety check (session length, over-reliance phrases) -> optional `safety` note
   - store message, extract personal facts
   - cognitive mode (light / standard / deep / support) -> `thinking` event
   - context: recent turns, semantic memories, facts, latest reflection
   - prompt: persona + mood/mode instructions + memory as the system prompt; real chat turns
   - stream tokens from the active brain -> `token` events (emojis/markdown stripped per token)
   - as each sentence completes, start TTS; `tts_sentence` events carry the MP3 path in order
   - `done` event; store reply + memory vector; maybe run a reflection in the background
5. **UI.** Tokens stream into the bubble; MP3s play in order through an analyser that drives
   the avatar's mouth; mood updates the HUD, heart meter and her face.

### Brains

| Backend | Client | Notes |
|---|---|---|
| `ollama_cloud` (default) | `OllamaCloudClient` -> `https://ollama.com/api/chat` + key | `kimi-k3`, `think: false`. |
| `anthropic` | official `anthropic` SDK | `claude-opus-5`, low effort, thinking off for latency. |
| `openai` | `httpx` | `gpt-4o-mini`. Out-of-credit errors are not retried. |

The active backend is read at call time, so switching in Settings applies to the next message.
If the active brain fails before its first token, the engine tries the other brains that have
a key, in the order Ollama Cloud -> Claude -> OpenAI. At startup the backend verifies the
configured brain and switches to the first working one if needed. There is no local LLM.

### Voice out

Sentences are synthesised in parallel but **at most 2 at a time** (ElevenLabs free-plan
concurrency); 429s are retried with short backoff. A sentence that still fails falls back to the
browser voice. Files are cached by text + emotion + voice in `data/tts_cache/`.

## Avatar

- VRM loaded with `@pixiv/three-vrm`. VRM 0.x rigs are rotated on load, which inverts their X/Z
  rotation axes — `AvatarMotion` takes a `flip` factor and authors all poses in VRM 1.0 space.
- Motion is layered and frame-rate independent: base pose -> breathing (fast inhale, slow
  exhale) -> weight shift and sway -> mood posture -> head (critically-damped springs, so moves
  have follow-through) -> gaze (slow attention + saccades) -> blinks (incl. double blinks) ->
  lip-sync (envelope follower, new viseme per syllable) -> expressions (eased).
- Reactions (`headpat`, `tease`, `cheer`) temporarily override the face and kick the head springs.
- The camera frames by visible height and re-checks the container size every frame, so the
  stage, focus mode and phones all frame correctly.

## Security model

- Backend binds `127.0.0.1`; CORS allows only the Vite origins (`:5173`, `:4173`).
- No UI/static file serving on the backend; `/audio/tts` resolves names inside the cache folder
  only (tested against `../` traversal).
- Plugins only act on anchored commands and only claim "open X" when X resolves to a real app.
- Secrets live in `.env` (git-ignored); `.env.example` documents them.
