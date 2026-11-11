# Yashi — Architecture

Two processes, one UI:

```
 Browser / desktop window
 ┌──────────────────────────────────────────────────────────────────┐
 │  frontend/  (Vite + React)            http://localhost:5173      │
 │   App.jsx ─ chat, settings, voice     avatar/ ─ 3D VRM + motion  │
 │   dashboard/ ─ profile, persona, keys voice/whisperListener.js   │
 └───────────────┬──────────────────────────────────────────────────┘
                 │  Vite dev proxy: /api  /audio  /health  /ws
 ┌───────────────▼──────────────────────────────────────────────────┐
 │  backend (FastAPI, API only)          http://127.0.0.1:8000      │
 │   /ws/chat ─▶ ConversationEngine ─▶ emotion · safety · memory    │
 │                                   ─▶ prompt ─▶ LLM (streamed)    │
 │                                   ─▶ sentence TTS (ElevenLabs)   │
 │   /api/stt (Whisper + wake check) · /api/settings · /api/memory  │
 │   /api/profile · /api/persona · /audio/tts                       │
 └───────────────┬───────────────────────────┬──────────────────────┘
                 │                           │
        data/yashi.db (SQLite)     Ollama Cloud / Claude /
        data/tts_cache/*.mp3       OpenAI · ElevenLabs
```

`python run.py` starts both processes for development; there the backend serves no UI files and
`GET /` redirects to the frontend. The Windows app (`desktop.py`) runs the same backend in-process
with `YASHI_SERVE_UI=1`: it serves the production build of the same frontend (`frontend/dist`,
rebuilt on launch when the source is newer) on `http://127.0.0.1:8000`, inside a WebView2 window.

## Repository layout

```
app/                    FastAPI app
  main.py               startup (backend checks, model warm-up), CORS, /health, / -> frontend
                        (desktop app: serves frontend/dist instead)
  websocket_manager.py  connected chat sockets
  security.py           require_app — mutating routes need the X-Yashi: 1 header
  routes/
    chat.py             /ws/chat/{client_id} — Origin check, PC actions first, then the
                        conversation engine
    stt_api.py          POST /api/stt — raw 16 kHz PCM -> Whisper text (?wake=1 adds the
                        acoustic wake-word verdict)
    settings_api.py     /api/settings — switch brain / voice; masked keys, PUT keys (.env),
                        provider tests, Ollama model list
    profile_api.py      /api/profile (+ stats, check-in) and /api/persona (+ options,
                        presets, reset, compiled prompt preview, voice preview)
    memory_api.py       GET /api/memory/* — facts, reflections, search, history
    tts_serve.py        GET /audio/tts/{file} — cached ElevenLabs MP3s
config/settings.py      all defaults (models, limits, wake threshold); reads .env
core/
  conversation/engine.py  the per-message pipeline (below)
  llm/                    ollama_client (Ollama Cloud), anthropic_client, openai_client,
                          prompt_builder (system prompt + chat turns)
  emotion/                text_sentiment (DistilBERT), voice_energy, fusion_engine
  cognitive/              complexity_analyzer + mode_selector -> light/standard/deep/support
  memory/                 database (SQLite), conversation_store, semantic_memory (MiniLM
                          embeddings), fact_extractor, reflection_engine
  personalization/        persona (Yashi's editable character -> system-prompt section,
                          presets) and profile (the user's profile, XP/levels, streaks,
                          check-ins, stats) — both stored in SQLite behavior_state
  safety/safety_monitor   session limits, dependency redirects, reply cleanup
  voice/                  elevenlabs_tts (TTS), stt (faster-whisper + wake_score)
  actions/                PC control: planner (keyword gate -> LLM -> JSON tool calls), agent
                          (fast path, yes/no confirmations), registry, windows (apps, windows,
                          keyboard, volume), browser (Yashi's Chrome over CDP), tools_system,
                          tools_web, tools_music (YouTube Music), tools_whatsapp, tools_files
frontend/
  src/main.jsx            hash router: #/ chat, #/dashboard/<tab> (chat stays mounted, hidden)
  src/App.jsx             UI: stage HUD, dialogue, composer, settings sheet, mic & wake word,
                          focus mode with hide/show chat tab
  src/dashboard/          Dashboard shell + ProfilePage, PersonaPage, BrainPage,
                          RadarChart, ui.jsx (sliders, count-ups, fields, icons)
  src/lib/api.js          fetch helpers (always send X-Yashi), image -> resized data URL
  src/avatar/VrmAvatar.jsx    three.js scene, VRM loading, camera framing (lazy-loaded)
  src/avatar/avatarMotion.js  procedural animation: springs, breathing, gaze, blinks,
                              lip-sync, expressions, reactions
  src/voice/whisperListener.js  mic capture + voice-activity detection -> /api/stt
  src/ui/motion.js        GSAP helpers (entrances, hearts, meter, sheet, mic level ring)
  public/models/AvatarSample_A.vrm, public/yashi-avatar.mp4 (WebGL fallback)
tests/test_all.py         unit tests (emotion, cognition, safety, prompt, security, desktop UI path)
tests/test_actions.py     PC control: yes/no, fast path, command gate, plan validation, contacts,
                          confirm-before-send, WebSocket Origin check
tests/test_wake.py        wake-word decision rules
run.py                    development launcher (backend + Vite)
desktop.py                Windows app: native window, in-process backend, built UI, mic on start
tools/make_shortcut.py    Desktop + Start Menu shortcut with the Yashi icon (assets/yashi.ico)
```

## A message, end to end

1. **Input.** Typed text, or speech: Chrome/Edge use the Web Speech API; Brave and the desktop
   app record the mic, cut sentences with a small energy VAD and POST them to `/api/stt`
   (faster-whisper `base`, hotword "Yashi").
2. **Wake word.** In wake mode only finished sentences are inspected. "Yashi …" sends the rest;
   a bare "Yashi" chimes and arms the next sentence (12 s). See *Wake word* below.
3. **Socket.** The UI sends `{type: "text"}` on `/ws/chat` (connections from any other Origin
   are refused). `chat.py` first asks the action agent (see *PC control*); if it isn't a
   command, the message goes to the engine.
4. **Engine** (`core/conversation/engine.py`):
   - emotion = fuse(text sentiment, optional voice energy) -> label + valence -> `emotion` event
   - safety check (session length, over-reliance phrases) -> optional `safety` note
   - store message, extract personal facts
   - cognitive mode (light / standard / deep / support) -> `thinking` event
   - context: recent turns, semantic memories, facts, latest reflection
   - prompt: compiled persona (from the Dashboard) + "about the person" (user profile) +
     mood/mode instructions + memory as the system prompt; real chat turns. Semantic memory
     stores only the user's words, so she never parrots her own old replies.
   - stream tokens from the active brain -> `token` events (emojis/markdown stripped per token)
   - as each sentence completes, start TTS; `tts_sentence` events carry the MP3 path in order
   - `done` event; store reply + memory vector; maybe run a reflection in the background
5. **UI.** Tokens stream into the bubble; MP3s play in order through an analyser that drives
   the avatar's mouth; mood updates the HUD, heart meter and her face.

### Brains

| Backend | Client | Notes |
|---|---|---|
| `ollama_cloud` (default) | `OllamaCloudClient` -> `https://ollama.com/api/chat` + key | `kimi-k3` (needs a paid Ollama plan; `gemma4:31b` works on Free), `think: false`. |
| `anthropic` | official `anthropic` SDK | `claude-opus-5`, low effort, thinking off for latency. |
| `openai` | `httpx` | `gpt-4o-mini`. Out-of-credit errors are not retried. |

The active backend is read at call time, so switching in Settings applies to the next message.
If the active brain fails before its first token, the engine tries the other brains that have
a key, in the order Ollama Cloud -> Claude -> OpenAI. At startup the backend verifies the
configured brain and switches to the first working one if needed. There is no local LLM.

### Wake word

Whisper path (Brave, desktop app): while waiting for her name, each sentence is sent to
`/api/stt?wake=1`. Besides the transcript, the backend computes `wake_score` — a forced
alignment of the tokens for " Yashi" / " Hey Yashi" / " Okay Yashi" / " Hi Yashi" against the
audio (the same mechanism faster-whisper uses for word timestamps), i.e. the model's probability
that the sentence *starts* with her name. It is a geometric mean of token probabilities;
`WAKE_THRESHOLD` (0.007) separates the two groups on synthetic speech (wake ≥ 0.011, others ≤ 0.003).
If Whisper confidently wrote an English soundalike ("yes she…"), the bar is 0.1.

The UI wakes when the acoustic verdict says so, or when the transcript literally contains her
name. Fuzzy text matches ("Yasi", "yes she", "Yoshi") only count when the acoustic check agrees.
If the name was heard but lost from the text ("What time is it?"), the whole sentence is the
command. Short clips are padded with 0.25 s of silence and decoded with beam 5.

Web Speech path (Chrome/Edge): no audio is available, so the text rules apply alone.

### PC control

`core/actions/agent.py`, per chat connection:

1. A pending question ("Send 'x' to Rahul?") is answered by a clear yes/no; anything else drops it.
2. Instant rules for one-word commands (pause, next, volume up, what's playing): no LLM call.
3. Otherwise a keyword gate (`planner.looks_like_command`) decides if the brain is asked at all.
   The planner prompt lists the tools; the model replies with JSON (`format: json`, temperature
   0.1, model `ACTION_MODEL` or the chat model). `validate()` keeps only known tools/arguments.
4. Tools run in order; the first failure stops the chain. Tools registered with `confirm=True`
   (WhatsApp send, power) run their `prepare` step, Yashi asks, and the tool runs on "yes" only.

Yashi's browser is Chrome started normally with `--remote-debugging-port=9223` and its own
profile; Playwright attaches over CDP on a single worker thread. YouTube Music: the search
endpoint gives a video/playlist id, playback is a watch URL with a queue (song + radio, playlist,
album, artist mix); controls call the page's `movie_player` API. WhatsApp Web: search the chat
list, pick the best name (asks if ambiguous), and before sending check the open chat's header
matches the confirmed name.

### Personalization

`core/personalization/persona.py` normalises the saved persona (clamped traits 0–100, length
limits, known enum values) and `compile_persona()` turns it into the character section of the
system prompt, with sample lines for strong traits and fixed guard-rails (no lists/markdown/
emojis, honest about being an AI). `profile.py` derives XP and levels (level L needs
`50·L·(L−1)` XP) from messages, facts and check-ins, plus streaks and the radar stats.

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
- Drag to rotate: a turntable yaw on top of the model's base yaw, with inertia; a drag over
  6 px suppresses the click (so it isn't a headpat); double-click springs back to the front.
  Rendering pauses while the chat view is hidden behind the dashboard.
- The camera frames by visible height and re-checks the container size every frame, so the
  stage, focus mode and phones all frame correctly.

## Security model

- Backend binds `127.0.0.1`; CORS allows only the Vite origins (`:5173`, `:4173`). The desktop
  app's UI is served from the backend itself, so it is same-origin.
- The only files served are the desktop app's built UI (`frontend/dist`, desktop mode only) and
  `/audio/tts`, which resolves names inside the cache folder; both are tested against `../`
  traversal.
- The desktop window grants the microphone to Yashi's own page only.
- The chat socket checks `Origin` (browsers don't apply CORS to WebSockets), so other websites
  can't drive the PC through Yashi.
- PC actions: messages and power actions always need a spoken/typed yes; files are never
  overwritten; the planner can only call registered tools with known arguments.
- Yashi's browser debugging port listens on 127.0.0.1 only, but any program on this PC could use
  it while it's open (it holds the WhatsApp session).
- Mutating routes (`PUT`/`POST` on settings, keys, profile, persona) require `X-Yashi: 1`.
  A cross-site form or simple request can't set custom headers, and a preflighted one is
  refused by CORS, so other websites can't change Yashi through your browser.
- Keys written from the Dashboard go to `.env`; values with newlines or over 300 characters are
  rejected (no injecting extra variables), and keys are only returned masked.
- Secrets live in `.env` (git-ignored); `.env.example` documents them.
