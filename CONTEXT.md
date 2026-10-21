# Yashi — Project Context

Background for anyone (human or AI assistant) picking up this project: what Yashi is for, the
decisions behind the current design, and what is known to be rough. For how the code is laid out
see [ARCHITECTURE.md](ARCHITECTURE.md); for setup see [README.md](README.md).

## Goal

A companion that feels like talking to a close friend, not an assistant: short casual replies,
real reactions, a face that reacts with her mood, a natural voice, and memory of who you are —
running on modest hardware (8 GB RAM, GTX 1650 4 GB) and usable from Brave.

Design principles carried from the original project: encourage real-world connection (the
safety monitor redirects over-reliance and nudges breaks after long sessions), be honest about
being an AI when sincerely asked, and keep personal data on the user's machine.

## Key decisions (and why)

| Decision | Why |
|---|---|
| **Default brain: Ollama Cloud `kimi-k3`** | Compared 7 cloud models on the same emotional exchange; Kimi K3 read the most like a real friend (~2 s to first token). `glm-5.3-flash` leaked its reasoning; `mistral-large-4` was flat. |
| **Cloud APIs only (no local LLM)** | The local `llama3.2:3b` fallback was removed at the owner's request and Ollama uninstalled. Resilience now comes from falling back across configured cloud APIs (Ollama Cloud -> Claude -> OpenAI). Speech-to-text, sentiment and embeddings still run on-device. |
| **Persona rewritten as "a close friend texting"** | The old persona ("AI companion and personal assistant") produced assistant-speak. Banned phrases, 1–3 sentences, react first, at most one question. Replies are also stripped of emojis and markdown emphasis server-side (models ignore the instruction sometimes, and TTS reads them aloud). |
| **Chat turns, not a transcript** | Prompts used to be a `User:/Yashi:` text dump; real message turns made replies noticeably more natural. |
| **Claude via the official SDK** | `claude-opus-5`, low effort, thinking disabled for voice latency. |
| **On-device Whisper for voice in Brave** | Brave blocks Google's speech service behind `webkitSpeechRecognition` (every attempt fails with `network`). Whisper `base` + hotword "Yashi" transcribed every test clip correctly; without the hotword it heard "Yasi"/"Yossi". |
| **Wake word acts on final sentences only** | Acting on interim results caused a ~1 s mic hand-off gap that swallowed the command — the "say Yashi many times" bug. |
| **Acoustic wake check (Whisper forced alignment)** | Text matching alone missed a lone "Yashi" (heard as "Yes she" or dropped) and false-fired on lookalikes. Scoring the audio for the "Yashi" tokens gets the Alexa-like behaviour without training a custom keyword model: 40/40 correct on clean + noisy synthetic speech. A dedicated keyword-spotting model (openWakeWord / Porcupine) would be the next step for always-on, low-CPU listening. |
| **Persona lives in the DB, edited from the Dashboard** | It used to be a hard-coded string in `settings.py`. Now it's structured (traits, role, style, likes, story, custom instructions) and compiled into the prompt every message, so edits apply to the very next reply. |
| **Memory stores only the user's words** | Storing "User: … \| Yashi: …" made her repeat her own old replies and drift back to the old personality after an edit. |
| **`X-Yashi` header on mutating routes** | The Dashboard can write API keys to `.env`; without a CSRF guard any website could have done the same through the browser. |
| **English-only UI** | Japanese sub-labels were removed at the owner's request; the romaji talking style stays as an opt-in persona option. |
| **ElevenLabs capped at 2 concurrent requests** | Free plan concurrency is 2; parallel per-sentence synthesis got HTTP 429 and fell back to the robotic browser voice mid-reply. |
| **VRM avatar (AvatarSample_A)** | VRM has standard expressions + visemes, runs in the browser via three-vrm, and the official VRoid samples are free for any use. A custom VRoid Studio model can be dropped into `frontend/public/models/` and listed first in `MODEL_URLS`. |
| **One frontend** | The backend used to serve a stale built copy of the UI on :8000. Now the Vite app is the only UI and the backend is API-only. |
| **Localhost-only backend** | The API can launch apps and touch files. It previously listened on `0.0.0.0` with `allow_origins=["*"]` and leaked `.env` and the memory DB through `/static/..%2F.env`. Fixed and covered by a test. |
| **UI: visual-novel / game style** | Crimson + white palette, black stage behind the model, slanted nameplate and buttons, mood heart meter, headpat/tease/cheer reactions. GSAP only where motion explains a change; respects reduced-motion. |

## History

- **Initial import** — FastAPI + React app built around Ollama `phi3:mini` (not installed), with a
  video avatar and a sidebar UI.
- **Make it work** — added the Claude client; found Ollama had no models, the Anthropic key was
  rejected and the OpenAI account had no credit; pulled `llama3.2:3b`; fixed plugin hijacking,
  the Windows banner crash, the missing dev proxy, and silent OpenAI failures.
- **Voice** — wake-word rework; Brave detection; on-device Whisper STT endpoint and listener.
- **Ollama Cloud** — new default brain (initially with a local `llama3.2:3b` fallback).
- **3D avatar** — VRM avatar, expressions, lip-sync; crimson/white theme; AvatarSample_A.
- **Refactor & hardening** — removed ~20 dead files/functions (legacy vanilla-JS UI, 2D avatar,
  unused routes and modules, Piper TTS, VAD), fixed the file-leak vulnerability and CORS, bound to
  localhost, single frontend, ElevenLabs concurrency fix, natural spring-based avatar motion,
  emoji/markdown stripping, GSAP UI, VN-style redesign, lazy-loaded 3D bundle, docs.
- **API only** — uninstalled Ollama; removed the local backend, model router and warm-up;
  brains now fall back across configured cloud APIs; prompts are chat turns only.
- **Dashboard** — RPG-style user profile (levels, XP, streak, check-ins, radar), persona editor
  in a glass "home screen" style, Brain & Keys page; persona and profile injected into the
  prompt; CSRF header; fact-extractor fixes ("name: going" junk).
- **Voice & stage polish** — acoustic wake-word check, drag-to-rotate avatar, focus-mode chat
  hide/show, English-only UI.

## Known limitations

- The Anthropic key in the original `.env` is rejected by the API (401) and the OpenAI account
  has no credit; both backends work once valid keys are added.
- AvatarSample_A has no "surprised" expression, so *excited* shows as a happy face.
- Stripping `*` also removes a literal asterisk in maths ("5 * 3"); acceptable for chat.
- Voice emotion (`voice_energy`) is supported by the fusion engine but not yet fed from the
  Whisper path.
- Yashi needs internet and at least one working brain key; there is no offline brain.
- First reply after a cold start can be slow while on-device models (Whisper, sentiment,
  embeddings) load; startup warm-up mitigates it.
- ElevenLabs free tier: 10,000 characters/month.
- Not deployable as-is on Vercel or other static/serverless hosts: the backend needs WebSockets,
  on-device models, a writable SQLite file and local app control. Vercel can serve the frontend
  only, which then has no backend to talk to.
- The wake threshold was calibrated on Windows synthetic voices, not real recordings; tune
  `WAKE_THRESHOLD` per mic/room. Yashi can't be interrupted by her name while she is speaking.
- The acoustic check only runs on the Whisper path (Brave / desktop); Chrome's Web Speech path
  still uses text matching.

## Ideas / next steps

- Feed Whisper audio energy into emotion fusion.
- A custom Yashi model made in VRoid Studio (silver hair like the original video avatar).
- Arm gestures (wave on greeting) — needs authored poses beyond the procedural layer.
- Persist chat sessions in the browser and show history on load.
- Barge-in: listen for "Yashi" while she talks (louder threshold + echo cancellation) and stop
  her voice.
- Hosted mode: backend on a VPS/Render with auth, frontend on Vercel pointing at it.
