import { lazy, startTransition, Suspense, useEffect, useReducer, useRef, useState } from "react";

import { createWhisperListener } from "./voice/whisperListener";
import {
  createEnterAnimator,
  createLevelRing,
  floatHearts,
  introStagger,
  messageEntrance,
  popBadge,
  pressFeedback,
  setMeter,
  slideSheet,
} from "./ui/motion";

const SPEECH_RATE = {
  distressed: 0.82,
  sad: 0.88,
  concerned: 0.9,
  neutral: 1.0,
  content: 1.0,
  happy: 1.06,
  joyful: 1.12,
  excited: 1.15,
};

const initialState = {
  status: { code: "busy", text: "Connecting..." },
  emotion: "neutral",
  valence: 0,
  mode: "standard",
  avatarFocus: false,
  micBar: { on: false, text: "Listening..." },
  volumeVisible: false,
  micActive: false,
  wakeWordActive: false,
  settingsOpen: false,
  llmBackend: "ollama_cloud",
  ttsBackend: "browser",
  typing: false,
  input: "",
  messages: [],
};

const RECOGNITION_LANGUAGE =
  typeof navigator !== "undefined" && /^en/i.test(navigator.language || "")
    ? navigator.language
    : "en-US";

const WAKE_WORD_PATTERN =
  /\b(?:yashi|yashii|yashy|ya[\s-]?shi|ya[\s-]?she)\b/i;

const WAKE_WORD_FOLLOWUP_MS = 12000;
// Chrome ends a listening session every so often; restart fast so we don't miss her name.
const WAKE_WORD_RESTART_MS = 250;
const WAKE_WORD_RETRY_MS = 1400;
const WAKE_WORD_CANONICAL = "yashi";
const WAKE_WORD_ALIASES = new Set([
  "yashi",
  "yashii",
  "yashy",
  "yasi",
  "yaashi",
  "yeshi",
  "yoshi",
  "yashee",
  "yashie",
]);

// Spellings that mean the recogniser really wrote her name, not a lookalike.
const WAKE_WORD_EXACT = new Set(["yashi", "yashii", "yashy", "yaashi", "yashee", "yashie"]);

// Brave exposes webkitSpeechRecognition but blocks Google's speech service,
// so every attempt fails with a "network" error.
function isBraveBrowser() {
  return typeof navigator !== "undefined" && !!navigator.brave;
}

const SPEECH_SERVICE_NOTE =
  "Couldn't reach the browser's speech-recognition service (it needs internet). " +
  "Wake word is off — check your connection, then turn it back on.";

function isPywebview() {
  return (
    typeof window !== "undefined" &&
    (typeof window.pywebview !== "undefined" || navigator.userAgent.includes("pywebview"))
  );
}

// Use on-device Whisper (via the Yashi backend) where browser speech
// recognition can't work: Brave, the desktop app, or no Web Speech API at all.
function useLocalWhisper() {
  const hasWebSpeech =
    typeof window !== "undefined" &&
    !!(window.SpeechRecognition || window.webkitSpeechRecognition);
  return isBraveBrowser() || isPywebview() || !hasWebSpeech;
}

function micErrorNote(error) {
  if (error && (error.name === "NotAllowedError" || error.name === "SecurityError")) {
    return "Microphone access is blocked. Click the mic icon in the address bar, allow it for localhost, then try again.";
  }
  if (error && error.name === "NotFoundError") {
    return "No microphone found. Plug one in and try again.";
  }
  return `Couldn't start the microphone (${(error && error.name) || "unknown error"}).`;
}

// three.js + the VRM model are big: load them after the UI paints.
const VrmAvatar = lazy(() => import("./avatar/VrmAvatar"));

const LLM_OPTIONS = [
  { id: "ollama_cloud", label: "Cloud", hint: "Kimi K3 · Ollama Cloud" },
  { id: "anthropic", label: "Claude", hint: "Anthropic API" },
  { id: "openai", label: "OpenAI", hint: "GPT-4o mini" },
];

const TTS_OPTIONS = [
  { id: "elevenlabs", label: "ElevenLabs", hint: "Natural voice" },
  { id: "browser", label: "Browser", hint: "Built-in · offline" },
];

const REACTIONS = [
  { id: "headpat", label: "Headpat", hint: "pat pat" },
  { id: "tease", label: "Tease", hint: "poke" },
  { id: "cheer", label: "Cheer", hint: "go go!" },
];

const MOOD_NOTE = {
  joyful: "on cloud nine",
  happy: "feeling good",
  excited: "buzzing",
  content: "at ease",
  neutral: "steady",
  concerned: "a bit worried",
  sad: "feeling down",
  distressed: "having a hard time",
};

// Angled "game UI" cuts used on buttons, tags and the nameplate.
const SLANT = "[clip-path:polygon(7px_0,100%_0,calc(100%-7px)_100%,0_100%)]";

function ChipButton({ active = false, className = "", children, ...props }) {
  return (
    <button
      className={cx(
        "rounded-md border px-3 py-1.5 text-[0.72rem] font-extrabold tracking-wide transition",
        active
          ? "border-yashi-brand bg-yashi-brand text-white"
          : "border-yashi-border bg-white text-[#6b4a51] hover:border-yashi-brand hover:text-yashi-brand",
        className
      )}
      type="button"
      {...props}
    >
      {children}
    </button>
  );
}

function OptionCard({ active, label, hint, onClick }) {
  return (
    <button
      className={cx(
        "border px-3 py-2 text-left transition",
        SLANT,
        active
          ? "border-yashi-brand bg-yashi-brand text-white"
          : "border-yashi-border bg-white text-[#2b1a1d] hover:border-yashi-brand hover:bg-[#fbe1e6]"
      )}
      onClick={onClick}
      type="button"
    >
      <div className="pl-1 text-[0.8rem] font-extrabold">{label}</div>
      <div className={cx("pl-1 text-[0.64rem]", active ? "text-white/75" : "text-yashi-muted")}>{hint}</div>
    </button>
  );
}

function SectionLabel({ en }) {
  return (
    <div className="mb-2 text-[0.66rem] font-extrabold uppercase tracking-[0.22em] text-[#6b4a51]">{en}</div>
  );
}

function cx(...values) {
  return values.filter(Boolean).join(" ");
}

function normalizeSpeechText(text) {
  return text
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s-]/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function levenshteinDistance(left, right) {
  const rows = left.length + 1;
  const cols = right.length + 1;
  const table = Array.from({ length: rows }, () => Array(cols).fill(0));

  for (let row = 0; row < rows; row += 1) table[row][0] = row;
  for (let col = 0; col < cols; col += 1) table[0][col] = col;

  for (let row = 1; row < rows; row += 1) {
    for (let col = 1; col < cols; col += 1) {
      const cost = left[row - 1] === right[col - 1] ? 0 : 1;
      table[row][col] = Math.min(
        table[row - 1][col] + 1,
        table[row][col - 1] + 1,
        table[row - 1][col - 1] + cost
      );
    }
  }

  return table[left.length][right.length];
}

function isWakeLikePhrase(phrase) {
  const collapsed = phrase.replace(/[\s-]/g, "");
  if (!collapsed || collapsed.length < 4 || collapsed.length > 8) {
    return false;
  }
  if (WAKE_WORD_ALIASES.has(collapsed)) {
    return true;
  }
  return levenshteinDistance(collapsed, WAKE_WORD_CANONICAL) <= 1;
}

// How Chrome commonly hears "Yashi" when it splits it into two English words.
// Only trusted at the START of a sentence, so "yes she did" mid-sentence is fine.
const WAKE_WORD_LEADING_PHRASES = new Set([
  "yes she", "yeah she", "ya she", "yah she", "yea she", "yes shi", "ya shee",
  "yes he", "yah shi", "jah she", "i she", "ash he", "ah she",
]);

function extractWakeCommand(transcript) {
  const normalized = normalizeSpeechText(transcript);
  const words = normalized.split(" ").filter(Boolean);

  // "hey yashi ..." / "ok yashi ..." — skip a leading greeting.
  const lead = words[0] === "hey" || words[0] === "hi" || words[0] === "ok" || words[0] === "okay" ? 1 : 0;
  const leadingPair = words.slice(lead, lead + 2).join(" ");
  if (WAKE_WORD_LEADING_PHRASES.has(leadingPair)) {
    return { heard: true, exact: false, command: words.slice(lead + 2).join(" ").trim() };
  }

  for (let index = 0; index < words.length; index += 1) {
    const single = words[index];
    const pair =
      index < words.length - 1 ? `${words[index]} ${words[index + 1]}` : "";

    if (isWakeLikePhrase(pair)) {
      return { heard: true, exact: false, command: words.slice(index + 2).join(" ").trim() };
    }
    if (isWakeLikePhrase(single)) {
      return { heard: true, exact: WAKE_WORD_EXACT.has(single), command: words.slice(index + 1).join(" ").trim() };
    }
  }

  const match = normalized.match(WAKE_WORD_PATTERN);
  if (!match || typeof match.index !== "number") {
    return { heard: false, command: "" };
  }

  return {
    heard: true,
    exact: WAKE_WORD_EXACT.has(match[0].toLowerCase()),
    command: normalized.slice(match.index + match[0].length).trim(),
  };
}

function normalizeSpeechForTTS(text) {
  return text
    .replace(/[`*_#~]/g, "")
    .replace(/\.{3,}/g, ".")
    .replace(/[,:;]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

const COMMON_SPEECH_CORRECTIONS = [
  [/\byou tube\b/gi, "youtube"],
  [/\bbest boy shub\b/gi, "beast boy shub"],
  [/\bbeast boy shop\b/gi, "beast boy shub"],
  [/\bbeast boy sub\b/gi, "beast boy shub"],
  [/\bbeastboy\s*shub\b/gi, "beast boy shub"],
];

function applySpeechCorrections(text) {
  let fixed = text || "";

  for (const [pattern, replacement] of COMMON_SPEECH_CORRECTIONS) {
    fixed = fixed.replace(pattern, replacement);
  }

  const normalized = normalizeSpeechText(fixed);

  // Common YouTube command false-positive correction.
  if (/\bon youtube\b/.test(normalized) && /\bwashroom\b/.test(normalized)) {
    fixed = fixed.replace(/\bwashroom\b/gi, "beast boy shub");
  }

  return fixed.replace(/\s+/g, " ").trim();
}

function scoreTranscriptCandidate(text) {
  const fixed = applySpeechCorrections(text);
  const normalized = normalizeSpeechText(fixed);

  if (!normalized) {
    return { text: "", score: -100 };
  }

  let score = 0;

  if (/\b(find|search|open|play|pause|next|previous|skip|stop|resume)\b/.test(normalized)) {
    score += 1.6;
  }

  if (/\bon youtube\b/.test(normalized)) {
    score += 1.4;
    const queryMatch = normalized.match(/\b(?:find|search|open|play)\s+(.+?)\s+on youtube\b/);
    if (queryMatch) {
      const words = queryMatch[1].split(" ").filter(Boolean).length;
      score += Math.min(2.0, words * 0.45);
      if (words <= 1) score -= 0.5;
    }
  }

  if (/\bwashroom\b/.test(normalized) && /\byoutube\b/.test(normalized)) {
    score -= 1.0;
  }

  score += Math.min(1.0, normalized.split(" ").filter(Boolean).length * 0.12);
  return { text: fixed, score };
}

function pickBestTranscript(result) {
  if (!result || result.length === 0) return "";

  let best = { text: "", score: -100 };

  for (let index = 0; index < result.length; index += 1) {
    const transcript = result[index]?.transcript || "";
    if (!transcript.trim()) continue;

    const candidate = scoreTranscriptCandidate(transcript);
    const confidence =
      typeof result[index]?.confidence === "number" ? result[index].confidence : 0;
    candidate.score += confidence;

    if (candidate.score > best.score) {
      best = candidate;
    }
  }

  return best.text || applySpeechCorrections(result[0]?.transcript || "");
}

function getStatusDotClass(code) {
  const base = "h-2 w-2 shrink-0 rounded-full transition";

  switch (code) {
    case "ok":
      return `${base} bg-yashi-teal shadow-[0_0_8px_#2e9e6b]`;
    case "think":
      return `${base} bg-yashi-brand animate-[yashi-pulse_0.8s_infinite]`;
    case "listen":
      return `${base} bg-yashi-pink animate-[yashi-pulse_0.6s_infinite]`;
    case "busy":
      return `${base} bg-yashi-warn animate-[yashi-pulse_1s_infinite]`;
    case "err":
      return `${base} bg-yashi-danger`;
    default:
      return `${base} bg-[#a68890]`;
  }
}



function getBubbleClass(message) {
  const base =
    "rounded-2xl px-[15px] py-[11px] text-[0.9rem] leading-[1.65] whitespace-pre-wrap break-words";

  if (message.role === "user") {
    return `${base} rounded-br-[5px] border border-yashi-user-border bg-yashi-user text-[#ffffff]`;
  }

  if (message.stream) {
    return `${base} rounded-bl-[5px] border border-yashi-brand-strong bg-yashi-bot text-[#2b1a1d] shadow-[0_0_10px_rgba(200,16,46,0.19)]`;
  }

  switch (message.emotion) {
    case "sad":
      return `${base} rounded-bl-[5px] border border-[rgba(108,155,209,0.25)] bg-yashi-bot text-[#2b1a1d]`;
    case "distressed":
      return `${base} rounded-bl-[5px] border border-[rgba(255,107,107,0.25)] bg-yashi-bot text-[#2b1a1d]`;
    case "happy":
    case "joyful":
      return `${base} rounded-bl-[5px] border border-[rgba(255,217,61,0.25)] bg-yashi-bot text-[#2b1a1d]`;
    default:
      return `${base} rounded-bl-[5px] border border-yashi-bot-border bg-yashi-bot text-[#2b1a1d]`;
  }
}

function reducer(state, action) {
  switch (action.type) {
    case "set_status":
      return { ...state, status: { code: action.code, text: action.text } };
    case "set_emotion":
      return { ...state, emotion: action.emotion || "neutral" };
    case "set_mode":
      return { ...state, mode: action.mode || "standard" };
    case "set_avatar_focus":
      return { ...state, avatarFocus: !!action.value };
    case "set_valence":
      return { ...state, valence: typeof action.value === "number" ? action.value : 0 };
    case "set_mic_bar":
      return {
        ...state,
        micBar: {
          on: action.on,
          text: action.text || "Listening...",
        },
      };
    case "set_volume_visible":
      return { ...state, volumeVisible: action.visible };
    case "set_mic_active":
      return { ...state, micActive: action.active };
    case "set_typing":
      return { ...state, typing: action.value };
    case "set_input":
      return { ...state, input: action.value };
    case "add_message":
      return {
        ...state,
        messages: [
          ...state.messages,
          {
            id: action.id,
            kind: "message",
            role: action.role,
            text: action.text,
            emotion: action.emotion || "neutral",
            stream: false,
          },
        ],
      };
    case "add_note":
      return {
        ...state,
        messages: [
          ...state.messages,
          {
            id: action.id,
            kind: "note",
            text: action.text,
          },
        ],
      };
    case "start_stream":
      return {
        ...state,
        messages: [
          ...state.messages,
          {
            id: action.id,
            kind: "message",
            role: "bot",
            text: "",
            emotion: "neutral",
            stream: true,
          },
        ],
      };
    case "append_stream":
      return {
        ...state,
        messages: state.messages.map((message) =>
          message.id === action.id
            ? { ...message, text: message.text + action.text }
            : message
        ),
      };
    case "finish_stream":
      return {
        ...state,
        messages: state.messages.map((message) => {
          if (message.id !== action.id) return message;

          const nextText =
            (!message.text || !message.text.trim()) && action.fullText
              ? action.fullText
              : message.text;

          return {
            ...message,
            text: nextText,
            emotion: action.emotion || message.emotion,
            stream: false,
          };
        }),
      };
    case "reset_session":
      return {
        ...state,
        emotion: "neutral",
        mode: "standard",
        avatarFocus: false,
        typing: false,
        input: "",
        messages: [],
      };
    case "set_wake_word":
      return { ...state, wakeWordActive: action.active };
    case "toggle_settings":
      return { ...state, settingsOpen: !state.settingsOpen };
    case "set_backends":
      return { ...state, llmBackend: action.llm, ttsBackend: action.tts };
    default:
      return state;
  }
}

function App({ active = true }) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const [persona, setPersona] = useState({ name: "Yashi" });
  // Focus mode: slide the chat away to see only Yashi.
  const [chatHidden, setChatHidden] = useState(false);

  const stageRef = useRef(null);
  const hudRef = useRef(null);
  const meterRef = useRef(null);
  const enter = useRef(createEnterAnimator()).current;
  const levelRingsRef = useRef(new Map());   // element -> level setter
  const logRef = useRef(null);
  const textareaRef = useRef(null);
  const volumeBarRef = useRef(null);

  const avatarRef = useRef(null);
  const wsRef = useRef(null);
  const reconnectTimerRef = useRef(0);
  const streamIdRef = useRef(null);
  const stopRequestedRef = useRef(false);
  const greetedRef = useRef(false);
  const typingRef = useRef(false);
  const nextMessageIdRef = useRef(1);
  const isConnectedRef = useRef(false);
  const statusCodeRef = useRef(initialState.status.code);

  const micOnRef = useRef(false);
  const restartingRef = useRef(false);
  const recognitionRef = useRef(null);
  const speechReceivedRef = useRef(false);
  const volDetectedRef = useRef(false);
  const noResultTimerRef = useRef(0);
  const volumeRafRef = useRef(0);
  const micStreamRef = useRef(null);
  const audioCtxRef = useRef(null);
  const analyserRef = useRef(null);

  const ttsQueueRef = useRef([]);
  const ttsPlayingRef = useRef(false);
  const speechQueueRef = useRef([]);
  const speechBusyRef = useRef(false);
  const voiceRef = useRef(null);
  const synthRef = useRef(
    typeof window !== "undefined" ? window.speechSynthesis : null
  );
  const wakeEnabledRef = useRef(false);
  const wakeResumeAfterMicRef = useRef(false);
  const wakeTriggeredMicRef = useRef(false);
  const wakeRestartTimerRef = useRef(0);

  function nextMessageId() {
    const id = nextMessageIdRef.current;
    nextMessageIdRef.current += 1;
    return id;
  }

  function setStatus(code, text) {
    statusCodeRef.current = code;
    dispatch({ type: "set_status", code, text });
  }

  function setEmotion(emotion) {
    const nextEmotion = emotion || "neutral";
    dispatch({ type: "set_emotion", emotion: nextEmotion });
    avatarRef.current?.setEmotion(nextEmotion);
  }

  function setMode(mode) {
    dispatch({ type: "set_mode", mode });
  }

  function setAvatarFocus(value) {
    dispatch({ type: "set_avatar_focus", value });
  }


  function setMicBar(on, text) {
    dispatch({ type: "set_mic_bar", on, text });
    avatarRef.current?.setListening(on);
  }

  function setVolumeVisible(visible) {
    dispatch({ type: "set_volume_visible", visible });
  }

  function setVolumePercent(percent) {
    if (volumeBarRef.current) {
      volumeBarRef.current.style.width = `${percent}%`;
    }
    levelRingsRef.current.forEach((setLevel) => setLevel(percent));
  }

  // Ref callback for the ring behind each Mic button (registered once per element).
  function levelRing(element) {
    const rings = levelRingsRef.current;
    for (const node of rings.keys()) if (!node.isConnected) rings.delete(node);
    if (element && !rings.has(element)) rings.set(element, createLevelRing(element));
  }

  function setMicActive(active) {
    dispatch({ type: "set_mic_active", active });
  }

  function setInput(value) {
    dispatch({ type: "set_input", value });
  }

  function addMessage(role, text, emotion = "neutral") {
    dispatch({
      type: "add_message",
      id: nextMessageId(),
      role,
      text,
      emotion,
    });
  }

  function addNote(text) {
    dispatch({ type: "add_note", id: nextMessageId(), text });
  }

  function setTyping(value) {
    // Mirrored in a ref: speech-recognition callbacks are created once and
    // would otherwise see a stale `state.typing`.
    typingRef.current = !!value;
    dispatch({ type: "set_typing", value });
  }

  function startStream() {
    const id = nextMessageId();
    streamIdRef.current = id;
    dispatch({ type: "start_stream", id });
  }

  function finishStream(emotion, fullText) {
    if (streamIdRef.current == null) return;

    dispatch({
      type: "finish_stream",
      id: streamIdRef.current,
      emotion,
      fullText,
    });
    streamIdRef.current = null;
  }

  function pickVoice() {
    if (voiceRef.current) return voiceRef.current;

    const synth = synthRef.current;
    const voices = synth ? synth.getVoices() : [];

    const preferred = voices.find(
      (voice) =>
        /female|woman|samantha|victoria|karen|moira|tessa|zira|aria|jenny|emma|hazel|luna|nova|bella|rachel/i.test(
          voice.name
        ) &&
        /en/i.test(voice.lang)
    );

    voiceRef.current =
      preferred ||
      voices.find((voice) => /en/i.test(voice.lang)) ||
      voices[0] ||
      null;

    return voiceRef.current;
  }

  function drainSpeech() {
    const synth = synthRef.current;

    if (!synth || speechBusyRef.current || speechQueueRef.current.length === 0) {
      return;
    }

    speechBusyRef.current = true;
    synth.speak(speechQueueRef.current.shift());
  }

  function speakBrowser(text, emotion) {
    const synth = synthRef.current;

    const prepared = normalizeSpeechForTTS(text);
    if (!synth || !prepared) return;

    const utterance = new SpeechSynthesisUtterance(prepared);
    utterance.voice = pickVoice();
    utterance.rate = Math.min(1.12, (SPEECH_RATE[emotion] || 1.0) + 0.03);
    utterance.pitch =
      emotion === "happy" || emotion === "joyful" ? 1.14 : 1.08;
    utterance.volume = 1.0;
    utterance.onstart = function () {
      avatarRef.current?.startLip();
    };
    utterance.onend = function () {
      avatarRef.current?.stopLip();
      speechBusyRef.current = false;
      drainSpeech();
    };
    utterance.onerror = function () {
      avatarRef.current?.stopLip();
      speechBusyRef.current = false;
      drainSpeech();
    };

    speechQueueRef.current.push(utterance);
    drainSpeech();
  }

  function drainTTS() {
    if (ttsPlayingRef.current || ttsQueueRef.current.length === 0) return;

    ttsPlayingRef.current = true;

    const audio = ttsQueueRef.current.shift();
    avatarRef.current?.startLip(audio);
    audio.onended = function () {
      avatarRef.current?.stopLip();
      ttsPlayingRef.current = false;
      drainTTS();
    };
    audio.onerror = function () {
      avatarRef.current?.stopLip();
      ttsPlayingRef.current = false;
      drainTTS();
    };
    audio.play().catch(function () {
      avatarRef.current?.stopLip();
      ttsPlayingRef.current = false;
      drainTTS();
    });
  }

  function stopAllTTS() {
    const synth = synthRef.current;

    if (synth) synth.cancel();

    speechQueueRef.current = [];
    speechBusyRef.current = false;
    ttsQueueRef.current = [];
    ttsPlayingRef.current = false;
    avatarRef.current?.stopLip();
  }

  function stopVolumeMeter() {
    if (volumeRafRef.current) {
      cancelAnimationFrame(volumeRafRef.current);
      volumeRafRef.current = 0;
    }

    if (noResultTimerRef.current) {
      clearTimeout(noResultTimerRef.current);
      noResultTimerRef.current = 0;
    }

    volDetectedRef.current = false;

    if (analyserRef.current) {
      analyserRef.current.disconnect();
      analyserRef.current = null;
    }

    if (micStreamRef.current) {
      micStreamRef.current.getTracks().forEach((track) => track.stop());
      micStreamRef.current = null;
    }

    if (audioCtxRef.current) {
      audioCtxRef.current.close().catch(function () {});
      audioCtxRef.current = null;
    }

    setVolumeVisible(false);
    setVolumePercent(0);
  }

  async function startVolumeMeter() {
    try {
      micStreamRef.current = await navigator.mediaDevices.getUserMedia({
        audio: true,
        video: false,
      });

      const AudioContextCtor =
        window.AudioContext || window.webkitAudioContext;

      if (!AudioContextCtor) return;

      audioCtxRef.current = new AudioContextCtor();
      const source = audioCtxRef.current.createMediaStreamSource(
        micStreamRef.current
      );

      analyserRef.current = audioCtxRef.current.createAnalyser();
      analyserRef.current.fftSize = 256;
      source.connect(analyserRef.current);

      const buffer = new Uint8Array(analyserRef.current.frequencyBinCount);
      setVolumeVisible(true);

      const tick = () => {
        if (!analyserRef.current) return;

        analyserRef.current.getByteFrequencyData(buffer);
        const average =
          buffer.reduce((total, value) => total + value, 0) / buffer.length;
        const percent = Math.min(100, average * 2.5);

        setVolumePercent(percent);

        if (percent > 8 && !volDetectedRef.current) {
          volDetectedRef.current = true;
          noResultTimerRef.current = window.setTimeout(() => {
            if (micOnRef.current && !speechReceivedRef.current) {
              addNote(
                "I can hear sound but no words are coming through. Check that the right microphone is selected, or type your message instead."
              );
            }
          }, 6000);
        }

        volumeRafRef.current = requestAnimationFrame(tick);
      };

      tick();
    } catch (error) {
      console.warn("[Yashi volume]", error);
    }
  }

  function sendText(text) {
    const value = text.trim();
    const socket = wsRef.current;

    if (
      typingRef.current ||
      !value ||
      !isConnectedRef.current ||
      !socket ||
      socket.readyState !== WebSocket.OPEN
    ) {
      return false;
    }

    // Always clear stale stop state before a fresh prompt.
    stopRequestedRef.current = false;
    addMessage("user", value, "neutral");
    // Show typing indicator immediately — don't wait for server
    setTyping(true);
    setStatus("think", "Thinking...");
    socket.send(JSON.stringify({ type: "text", text: value }));
    return true;
  }

  function requestStop() {
    const socket = wsRef.current;

    if (
      !state.typing ||
      !isConnectedRef.current ||
      !socket ||
      socket.readyState !== WebSocket.OPEN
    ) {
      return;
    }

    socket.send(JSON.stringify({ type: "stop" }));
    stopRequestedRef.current = true;
    stopAllTTS();
    setTyping(false);
    avatarRef.current?.setThinking(false);
    setStatus("busy", "Stopping...");
  }

  function sendCurrentInput() {
    if (!sendText(state.input)) return;
    setInput("");
  }

  function stopMic() {
    micOnRef.current = false;
    restartingRef.current = false;
    speechReceivedRef.current = false;
    clearTimeout(wakeTimeoutRef.current);
    wakeTimeoutRef.current = 0;

    if (noResultTimerRef.current) {
      clearTimeout(noResultTimerRef.current);
      noResultTimerRef.current = 0;
    }

    try {
      recognitionRef.current?.abort();
    } catch (error) {}

    recognitionRef.current = null;
    if (whisperModeRef.current === "mic") stopWhisper();

    stopVolumeMeter();
    setMicActive(false);
    setMicBar(false);

    if (statusCodeRef.current !== "think") {
      setStatus("ok", "Ready");
    }
    if (wakeResumeAfterMicRef.current) {
      wakeResumeAfterMicRef.current = false;
      wakeTriggeredMicRef.current = false;
      scheduleWakeWordRestart(700);
    }

    // Note: wake word restart is handled manually — don't auto-start in desktop mode
  }

  function startRecognition() {
    if (!micOnRef.current) return;

    restartingRef.current = true;

    const SpeechRecognitionCtor =
      window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognitionCtor) return;

    const recognition = new SpeechRecognitionCtor();
    recognition.lang = RECOGNITION_LANGUAGE;
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.maxAlternatives = 5;

    recognition.onstart = function () {
      restartingRef.current = false;
      setMicActive(true);
      setStatus("listen", "Listening...");
      setMicBar(true, "Listening - speak now...");
    };

    recognition.onresult = function (event) {
      if (!speechReceivedRef.current) {
        speechReceivedRef.current = true;
        clearTimeout(noResultTimerRef.current);
        noResultTimerRef.current = 0;
      }

      let interim = "";
      let finalText = "";

      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const transcript = pickBestTranscript(event.results[index]);
        if (!transcript) continue;

        if (event.results[index].isFinal) finalText += `${transcript} `;
        else interim += `${transcript} `;
      }

      const interimText = interim.trim();
      if (interimText) {
        setInput(interimText);
        setMicBar(true, interimText.slice(-50));
      }

      const correctedFinal = applySpeechCorrections(finalText.trim());
      if (correctedFinal) {
        setInput(correctedFinal);
        const sent = sendText(correctedFinal);

        if (sent) setInput("");
        if (sent && wakeTriggeredMicRef.current) {
          window.setTimeout(() => {
            if (micOnRef.current) stopMic();
          }, 250);
        }

        window.setTimeout(() => {
          if (micOnRef.current) {
            setMicBar(true, "Listening - speak now...");
          }
        }, 500);
      }
    };

    recognition.onerror = function (event) {
      if (event.error === "no-speech" || event.error === "aborted") return;

      if (event.error === "network") {
        addNote(SPEECH_SERVICE_NOTE.replace(
          "Wake word is off — check your connection, then turn it back on.",
          "Check your connection and try the Mic again."
        ));
        stopMic();
        return;
      }

      if (event.error === "not-allowed") {
        addNote(
          "Microphone access is blocked. Allow microphone access in the browser and refresh."
        );
        micOnRef.current = false;
        restartingRef.current = false;
        setMicActive(false);
        setMicBar(false);
        return;
      }

      console.warn("[Yashi mic] error:", event.error);
    };

    recognition.onend = function () {
      if (micOnRef.current && !restartingRef.current) {
        restartingRef.current = true;
        window.setTimeout(() => {
          startRecognition();
        }, 120);
      } else {
        setMicActive(false);
        setMicBar(false);

        if (statusCodeRef.current !== "think") {
          setStatus("ok", "Ready");
        }
      }
    };

    recognitionRef.current = recognition;

    try {
      recognition.start();
    } catch (error) {
      restartingRef.current = false;
      window.setTimeout(() => {
        if (micOnRef.current) startRecognition();
      }, 300);
    }
  }

  async function toggleMic(options = {}) {
    const { fromWakeWord = false } = options;

    if (useLocalWhisper()) {
      if (micOnRef.current) {
        stopMic();
        return;
      }
      if (whisperModeRef.current === "wake") {
        stopWhisper();
        wakeWordOnRef.current = false;
      }
      micOnRef.current = true;
      wakeResumeAfterMicRef.current = wakeEnabledRef.current;
      wakeTriggeredMicRef.current = fromWakeWord;
      try {
        await startWhisper("mic");
      } catch (error) {
        micOnRef.current = false;
        addNote(micErrorNote(error));
        if (wakeResumeAfterMicRef.current) {
          wakeResumeAfterMicRef.current = false;
          scheduleWakeWordRestart(700);
        }
        return;
      }
      setMicActive(true);
      setVolumeVisible(true);
      setStatus("listen", "Listening...");
      setMicBar(true, "Listening - speak now...");
      return;
    }

    const SpeechRecognitionCtor =
      window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognitionCtor) {
      addNote(
        "Voice input requires microphone permission. Click Allow when prompted, or type your message."
      );
      return;
    }

    if (micOnRef.current) {
      stopMic();
      return;
    }

    if (wakeWordOnRef.current) {
      try {
        wakeRecogRef.current?.abort();
      } catch (error) {}
      wakeWordOnRef.current = false;
      wakeRecogRef.current = null;
    }

    micOnRef.current = true;
    speechReceivedRef.current = false;
    volDetectedRef.current = false;
    wakeResumeAfterMicRef.current = wakeEnabledRef.current;
    wakeTriggeredMicRef.current = fromWakeWord;

    await startVolumeMeter();
    startRecognition();
  }

  function handleSocketMessage(data) {
    switch (data.type) {
      case "connected":
        if (!greetedRef.current) {
          greetedRef.current = true;
          addMessage("bot", data.message, "neutral");
        }
        setStatus("ok", "Ready");
        avatarRef.current?.setThinking(false);
        break;
      case "emotion":
        setEmotion(data.current_emotion);
        dispatch({ type: "set_valence", value: data.valence });
        break;
      case "thinking":
        stopRequestedRef.current = false;
        setStatus("think", `Thinking (${data.mode})...`);
        setMode(data.mode);
        avatarRef.current?.setThinking(true);
        setTyping(true);
        startStream();
        break;
      case "token":
        if (stopRequestedRef.current) {
          break;
        }
        if (streamIdRef.current != null) {
          startTransition(() => {
            dispatch({
              type: "append_stream",
              id: streamIdRef.current,
              text: data.text,
            });
          });
        }
        break;
      case "tts_sentence":
        if (stopRequestedRef.current) {
          break;
        }
        if (data.emotion) setEmotion(data.emotion);
        if (data.audio_path) {
          const fileName = data.audio_path.replace(/.*[\\/]/, "");
          const ttsAud = new Audio(`/audio/tts/${fileName}`);
          ttsAud.onerror = function() {
            if (data.text) speakBrowser(data.text, data.emotion || "neutral");
          };
          ttsQueueRef.current.push(ttsAud);
          drainTTS();
        } else if (data.text) {
          speakBrowser(data.text, data.emotion || "neutral");
        }
        break;
      case "done":
        stopRequestedRef.current = false;
        const stopped = !!data.stopped;
        setTyping(false);
        avatarRef.current?.setThinking(false);
        finishStream(data.emotion || "neutral", data.full_text || "");
        setEmotion(data.emotion || "neutral");

        if (!stopped && data.audio_path) {
          const fileName = data.audio_path.replace(/.*[\\/]/, "");
          const audio = new Audio(`/audio/tts/${fileName}`);
          avatarRef.current?.startLip(audio);
          audio.onended = function () {
            avatarRef.current?.stopLip();
          };
          audio.onerror = function () {
            avatarRef.current?.stopLip();
          };
          audio.play().catch(function () {
            avatarRef.current?.stopLip();
          });
        }

        if (!stopped) {
          avatarRef.current?.triggerBounce();
        }
        if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
        // Safety net: if TTS backend is browser and no sentences were queued, speak the full text
        if (!stopped && data.tts_backend === "browser" && data.full_text &&
            speechQueueRef.current.length === 0 && !speechBusyRef.current) {
          speakBrowser(data.full_text.slice(0, 300), data.emotion || "neutral");
        }
        if (micOnRef.current) {
          setStatus("listen", "Listening...");
          setMicBar(true, "Listening - speak now...");
        } else {
          setStatus("ok", stopped ? "Stopped" : "Ready");
          if (wakeEnabledRef.current) {
            scheduleWakeWordRestart(700);
          }
        }
        break;
      case "safety":
        addNote(data.note);
        break;
      case "plugin_response":
        stopRequestedRef.current = false;
        setTyping(false);
        avatarRef.current?.setThinking(false);
        setStatus("ok", "Ready");
        addMessage("bot", data.message, "neutral");
        avatarRef.current?.triggerBounce();
        // Speak the plugin response via browser TTS
        if (data.message && data.message.trim()) {
          speakBrowser(data.message, "neutral");
        }
        if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
        if (micOnRef.current) {
          setStatus("listen", "Listening...");
          setMicBar(true, "Listening - speak now...");
        } else if (wakeEnabledRef.current) {
          scheduleWakeWordRestart(700);
        }
        break;
      case "session_reset":
        stopRequestedRef.current = false;
        avatarRef.current?.setThinking(false);
        streamIdRef.current = null;
        setTyping(false);
        stopAllTTS();
        dispatch({ type: "reset_session" });
        addMessage("bot", "Fresh start! What's on your mind?", "neutral");
        break;
      default:
        break;
    }
  }


  // ── Wake word detection ─────────────────────────────────────────────────
  const wakeWordOnRef = useRef(false);
  const wakeRecogRef = useRef(null);
  const wakeTimeoutRef = useRef(0);
  const wakeArmedUntilRef = useRef(0);
  const wakeNetErrorsRef = useRef(0);
  const whisperRef = useRef(null);
  const whisperModeRef = useRef(null);      // "mic" | "wake" | null
  const whisperErrorsRef = useRef(0);

  function isAssistantSpeaking() {
    return speechBusyRef.current || ttsPlayingRef.current;
  }

  function stopWhisper() {
    whisperRef.current?.stop();
    whisperRef.current = null;
    whisperModeRef.current = null;
  }

  function isWhisperListeningForCommand() {
    return whisperModeRef.current === "mic" || Date.now() < wakeArmedUntilRef.current;
  }

  // Wake-word logic for one finished sentence.
  function handleWakeTranscript(text, acousticWake = false, acousticChecked = false) {
    let match = extractWakeCommand(text);
    const armed = Date.now() < wakeArmedUntilRef.current;
    if (acousticChecked && match.heard && !match.exact && !acousticWake) {
      match = { heard: false, command: "" };     // "yes she did", "Yoshi": not her
    }
    // The backend heard "Yashi" in the sound itself even though the transcript
    // lost it ("What time is it?"): the whole sentence is the command.
    if (!match.heard && acousticWake && !armed) {
      match = { heard: true, command: normalizeSpeechText(text).replace(/^(?:hey|hi|ok|okay)\s+/, "") };
    }

    if (match.heard && match.command.length > 1) {
      wakeArmedUntilRef.current = 0;
      clearTimeout(wakeTimeoutRef.current);
      setMicBar(false);
      sendText(match.command);
    } else if (match.heard) {
      wakeArmedUntilRef.current = Date.now() + WAKE_WORD_FOLLOWUP_MS;
      setMicBar(true, "I'm listening...");
      playWakeChime();
      clearTimeout(wakeTimeoutRef.current);
      wakeTimeoutRef.current = window.setTimeout(() => {
        if (Date.now() >= wakeArmedUntilRef.current) setMicBar(false);
      }, WAKE_WORD_FOLLOWUP_MS + 50);
    } else if (armed && text.trim().length > 1) {
      wakeArmedUntilRef.current = 0;
      clearTimeout(wakeTimeoutRef.current);
      setMicBar(false);
      sendText(text.trim());
    } else if (!armed) {
      setMicBar(false);
    }
  }

  function handleWhisperUtterance(raw, acousticWake = false, acousticChecked = false) {
    whisperErrorsRef.current = 0;
    const text = applySpeechCorrections(raw);
    if (!text && !acousticWake) return;
    if (whisperModeRef.current === "mic") {
      setMicBar(true, "Listening - speak now...");
      sendText(text);
      return;
    }
    handleWakeTranscript(text, acousticWake, acousticChecked);
  }

  async function startWhisper(mode) {
    stopWhisper();
    whisperErrorsRef.current = 0;
    const listener = createWhisperListener({
      onUtterance: handleWhisperUtterance,
      onSpeech(speaking) {
        if (speaking && isWhisperListeningForCommand()) setMicBar(true, "Hearing you...");
      },
      onTranscribing(busy) {
        if (busy && isWhisperListeningForCommand()) setMicBar(true, "Understanding...");
      },
      onLevel(percent) {
        if (whisperModeRef.current === "mic") setVolumePercent(percent);
      },
      isMuted: isAssistantSpeaking,
      // Only while waiting for her name; once armed, everything is the command.
      wantsWakeCheck: () => whisperModeRef.current === "wake" && Date.now() >= wakeArmedUntilRef.current,
      onError(error) {
        console.warn("[Yashi whisper]", error);
        whisperErrorsRef.current += 1;
        if (whisperErrorsRef.current === 3) {
          addNote("Local speech recognition isn't responding. Make sure the Yashi backend is running.");
        }
      },
    });
    whisperRef.current = listener;
    whisperModeRef.current = mode;
    try {
      await listener.start();
    } catch (error) {
      if (whisperRef.current === listener) stopWhisper();
      throw error;
    }
  }
  const chimeCtxRef = useRef(null);

  // Soft two-note chime so you know Yashi heard her name.
  function playWakeChime() {
    try {
      const Ctor = window.AudioContext || window.webkitAudioContext;
      if (!Ctor) return;
      const ctx = chimeCtxRef.current || (chimeCtxRef.current = new Ctor());
      const now = ctx.currentTime;
      [660, 880].forEach((freq, index) => {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = "sine";
        osc.frequency.value = freq;
        const start = now + index * 0.09;
        gain.gain.setValueAtTime(0.0001, start);
        gain.gain.exponentialRampToValueAtTime(0.12, start + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.0001, start + 0.18);
        osc.connect(gain).connect(ctx.destination);
        osc.start(start);
        osc.stop(start + 0.2);
      });
    } catch (error) {}
  }

  function scheduleWakeWordRestart(delay = WAKE_WORD_RESTART_MS) {
    clearTimeout(wakeRestartTimerRef.current);

    if (!wakeEnabledRef.current) return;

    wakeRestartTimerRef.current = window.setTimeout(() => {
      if (!wakeEnabledRef.current || wakeWordOnRef.current || micOnRef.current) {
        return;
      }
      startWakeWord({ silent: true });
    }, delay);
  }

  function startWakeWord(options = {}) {
    const { silent = false } = options;

    if (useLocalWhisper()) {
      if (wakeWordOnRef.current || micOnRef.current) return true;
      wakeEnabledRef.current = true;
      wakeWordOnRef.current = true;
      dispatch({ type: "set_wake_word", active: true });
      startWhisper("wake").catch((error) => {
        wakeEnabledRef.current = false;
        wakeWordOnRef.current = false;
        dispatch({ type: "set_wake_word", active: false });
        addNote(micErrorNote(error));
      });
      return true;
    }
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
      wakeEnabledRef.current = false;
      dispatch({ type: "set_wake_word", active: false });
      if (!silent) {
        addNote("Wake word needs Chrome speech recognition. Open Yashi in Chrome and allow microphone access.");
      }
      return false;
    }
    if (wakeWordOnRef.current || micOnRef.current) return true;

    const r = new SR();
    r.lang = RECOGNITION_LANGUAGE;
    r.continuous = true;
    r.interimResults = true;
    r.maxAlternatives = 5;

    r.onstart = function () {
      wakeWordOnRef.current = true;
      wakeRecogRef.current = r;
      dispatch({ type: "set_wake_word", active: true });
    };

    // One recognizer does everything. Switching to a second recognizer after
    // the wake word leaves a ~1s gap in which the command itself gets lost,
    // and interim results are often cut off mid-word ("Yashi op..."), so we
    // only act on FINAL results and use interim ones just for feedback.
    r.onresult = function (ev) {
      wakeNetErrorsRef.current = 0;
      for (let i = ev.resultIndex; i < ev.results.length; i++) {
        const result = ev.results[i];
        let wakeMatch = { heard: false, command: "" };
        let bestScore = -100;

        for (let alt = 0; alt < result.length; alt += 1) {
          const transcript = applySpeechCorrections(result[alt].transcript || "");
          if (!transcript) continue;

          const candidate = extractWakeCommand(transcript);
          if (!candidate.heard) continue;

          const confidence =
            typeof result[alt].confidence === "number" ? result[alt].confidence : 0;
          const cmdWords = candidate.command.split(" ").filter(Boolean).length;
          const score = confidence + Math.min(1.5, cmdWords * 0.3);

          if (score > bestScore) {
            bestScore = score;
            wakeMatch = candidate;
          }
        }

        const armed = Date.now() < wakeArmedUntilRef.current;

        if (!result.isFinal) {
          // Instant visual feedback while the sentence is still being spoken.
          if (wakeMatch.heard) {
            setMicBar(true, wakeMatch.command || "I'm listening...");
          } else if (armed) {
            setMicBar(true, pickBestTranscript(result) || "I'm listening...");
          }
          continue;
        }

        if (wakeMatch.heard && wakeMatch.command.length > 1) {
          // "Yashi, open YouTube" in one breath.
          wakeArmedUntilRef.current = 0;
          setMicBar(false);
          sendText(wakeMatch.command);
        } else if (wakeMatch.heard) {
          // Just "Yashi" — the next sentence is the command.
          wakeArmedUntilRef.current = Date.now() + WAKE_WORD_FOLLOWUP_MS;
          setMicBar(true, "I'm listening...");
          playWakeChime();
          clearTimeout(wakeTimeoutRef.current);
          wakeTimeoutRef.current = window.setTimeout(() => {
            if (Date.now() >= wakeArmedUntilRef.current) setMicBar(false);
          }, WAKE_WORD_FOLLOWUP_MS + 50);
        } else if (armed) {
          const command = pickBestTranscript(result).trim();
          if (command.length > 1) {
            wakeArmedUntilRef.current = 0;
            clearTimeout(wakeTimeoutRef.current);
            setMicBar(false);
            sendText(command);
          }
        }
      }
    };

    r.onerror = function (ev) {
      // Wake word error handling — stop immediately, don't spam
      wakeWordOnRef.current = false;
      wakeRecogRef.current = null;
      if (ev.error === "no-speech" || ev.error === "aborted") {
        scheduleWakeWordRestart(WAKE_WORD_RESTART_MS);
        return;
      }
      if (ev.error === "not-allowed" || ev.error === "service-not-allowed") {
        wakeEnabledRef.current = false;
        dispatch({ type: "set_wake_word", active: false });
        addNote("Wake word was blocked. Allow microphone access in Chrome and try again.");
        return;
      }
      if (ev.error === "network") {
        // Retry quietly a few times; a real outage turns the wake word off
        // with ONE explanation instead of a new note every 1.4s forever.
        wakeNetErrorsRef.current += 1;
        if (wakeNetErrorsRef.current >= 3) {
          stopWakeWord();
          addNote(SPEECH_SERVICE_NOTE);
          return;
        }
        scheduleWakeWordRestart(WAKE_WORD_RETRY_MS * wakeNetErrorsRef.current);
        return;
      }
      console.warn("[Yashi wake word]", ev.error);
      scheduleWakeWordRestart(WAKE_WORD_RESTART_MS);
      // Don't retry — would cause infinite loop
    };

    r.onend = function () {
      wakeWordOnRef.current = false;
      wakeRecogRef.current = null;
      if (wakeEnabledRef.current && !micOnRef.current) {
        scheduleWakeWordRestart(WAKE_WORD_RESTART_MS);
      }
    };

    wakeEnabledRef.current = true;
    if (!silent) wakeNetErrorsRef.current = 0;

    try {
      r.start();
      return true;
    } catch (error) {
      wakeWordOnRef.current = false;
      wakeRecogRef.current = null;
      dispatch({ type: "set_wake_word", active: true });
      scheduleWakeWordRestart(WAKE_WORD_RETRY_MS);
      if (!silent) {
        addNote("Wake word is starting up. If it misses the first try, it will retry automatically.");
      }
      return true;
    }
  }

  function stopWakeWord() {
    wakeEnabledRef.current = false;
    wakeWordOnRef.current = false;
    wakeResumeAfterMicRef.current = false;
    wakeTriggeredMicRef.current = false;
    clearTimeout(wakeRestartTimerRef.current);
    clearTimeout(wakeTimeoutRef.current);
    try { wakeRecogRef.current?.abort(); } catch (error) {}
    wakeRecogRef.current = null;
    wakeArmedUntilRef.current = 0;
    if (whisperModeRef.current === "wake") stopWhisper();
    dispatch({ type: "set_wake_word", active: false });
  }

  // ── Settings API calls ──────────────────────────────────────────────────
  async function fetchSettings() {
    try {
      const r = await fetch("/api/settings/current");
      if (r.ok) {
        const d = await r.json();
        dispatch({ type: "set_backends", llm: d.llm_backend || "ollama_cloud", tts: d.tts_backend || "browser" });
      }
    } catch (_) {}
  }

  async function switchLLM(backend) {
    try {
      setStatus("busy", "Switching LLM...");
      const r = await fetch(`/api/settings/llm/${backend}`, { method: "POST", headers: { "X-Yashi": "1" } });
      const d = await r.json();
      dispatch({ type: "set_backends", llm: backend, tts: state.ttsBackend });
      addNote(d.message || `LLM switched to ${backend}`);
      setStatus("ok", "Ready");
    } catch (e) {
      addNote("Failed to switch LLM backend.");
      setStatus("ok", "Ready");
    }
  }

  async function switchTTS(backend) {
    try {
      const r = await fetch(`/api/settings/tts/${backend}`, { method: "POST", headers: { "X-Yashi": "1" } });
      const d = await r.json();
      dispatch({ type: "set_backends", llm: state.llmBackend, tts: backend });
      addNote(d.message || `TTS switched to ${backend}`);
    } catch (e) {
      addNote("Failed to switch TTS backend.");
    }
  }

  useEffect(() => {
    document.title = "Yashi - AI Companion";
    fetchSettings();
  }, []);

  useEffect(() => {
    const synth = synthRef.current;

    if (!synth) return undefined;

    const handleVoicesChanged = () => {
      voiceRef.current = null;
      pickVoice();
    };

    synth.onvoiceschanged = handleVoicesChanged;
    handleVoicesChanged();

    return () => {
      if (synth.onvoiceschanged === handleVoicesChanged) {
        synth.onvoiceschanged = null;
      }
    };
  }, []);

  useEffect(() => {
    let disposed = false;

    function connect() {
      const protocol = window.location.protocol === "https:" ? "wss" : "ws";
      const clientId = `c_${Math.random().toString(36).slice(2, 9)}`;

      setStatus("busy", "Connecting...");

      const socket = new WebSocket(
        `${protocol}://${window.location.host}/ws/chat/${clientId}`
      );

      wsRef.current = socket;

      socket.onopen = function () {
        if (disposed) return;
        isConnectedRef.current = true;
        setStatus("ok", "Ready");
      };

      socket.onclose = function () {
        isConnectedRef.current = false;

        if (disposed) return;

        setStatus("err", "Reconnecting...");
        reconnectTimerRef.current = window.setTimeout(connect, 3000);
      };

      socket.onerror = function () {
        if (disposed) return;
        setStatus("err", "Connection error");
      };

      socket.onmessage = function (event) {
        try {
          handleSocketMessage(JSON.parse(event.data));
        } catch (error) {
          console.warn("[Yashi ws]", error);
        }
      };
    }

    connect();
    // Wake word starts only when user clicks the button (avoids Chrome mic conflicts on load)

    return () => {
      stopWakeWord();
      disposed = true;
      isConnectedRef.current = false;
      clearTimeout(reconnectTimerRef.current);
      stopMic();
      stopAllTTS();

      if (wsRef.current && wsRef.current.readyState < WebSocket.CLOSING) {
        wsRef.current.close();
      }
    };
  }, []);

  useEffect(() => {
    introStagger(hudRef.current);
  }, []);

  useEffect(() => {
    if (!active) return;
    fetch("/api/persona")
      .then((r) => (r.ok ? r.json() : null))
      .then((p) => p && setPersona({ name: p.name || "Yashi" }))
      .catch(() => {});
    fetchSettings();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);

  // Mood meter: valence -1..1 -> 0..100 %.
  useEffect(() => {
    setMeter(meterRef.current, ((state.valence + 1) / 2) * 100);
  }, [state.valence]);

  useEffect(() => {
    const textarea = textareaRef.current;

    if (!textarea) return;

    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 140)}px`;
  }, [state.input, state.avatarFocus]);

  useEffect(() => {
    const log = logRef.current;

    if (!log) return;

    log.scrollTop = log.scrollHeight;
  }, [state.messages, state.typing, state.avatarFocus]);

  useEffect(() => {
    if (!state.avatarFocus) return undefined;

    function handleKeyDown(event) {
      if (event.key === "Escape") {
        setAvatarFocus(false);
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [state.avatarFocus]);

  function handleInputKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendCurrentInput();
    }
  }

  function openWindow(path) {
    window.open(path, "_blank", "noopener,noreferrer");
  }

  function newSession() {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "new_session" }));
    }
  }

  function toggleWakeWord() {
    if (wakeEnabledRef.current) {
      stopWakeWord();
      addNote("Wake word off.");
    } else if (startWakeWord()) {
      addNote('Wake word on. Say "Yashi", wait for the chime, then talk - or say it all in one go.');
    }
  }

  // Interactive reactions. A click on Yashi herself is a headpat.
  function react(kind, event) {
    avatarRef.current?.react(kind);
    const stage = stageRef.current;
    if (kind !== "headpat" || !stage) return;
    const box = stage.getBoundingClientRect();
    const x = event && event.clientX ? event.clientX - box.left : box.width / 2;
    const y = event && event.clientY ? event.clientY - box.top : box.height * 0.28;
    floatHearts(stage, x, y);
  }

  const meterPercent = Math.round(((state.valence + 1) / 2) * 100);

  return (
    <div className="relative flex h-screen flex-col overflow-hidden bg-yashi-shell text-[#2b1a1d] min-[900px]:flex-row">
      {/* ── Stage: Yashi on black, VN-style nameplate and HUD ─────────────── */}
      <section
        className={cx(
          "relative shrink-0 overflow-hidden bg-black",
          state.avatarFocus
            ? "h-screen w-full"
            : "h-[44vh] w-full min-[900px]:h-screen min-[900px]:w-[42%] min-[900px]:max-w-[640px]"
        )}
        ref={stageRef}
      >
        <button
          aria-label="Give Yashi a headpat"
          className="absolute inset-0 block cursor-pointer"
          onClick={(event) => react("headpat", event)}
          title="Click for a headpat · drag to spin her · double-click to face you"
          type="button"
        >
          <Suspense fallback={null}>
          <VrmAvatar
            ref={avatarRef}
            fallback={
              <video
                aria-label="Yashi avatar"
                className="block h-full w-full object-contain"
                autoPlay
                loop
                muted
                playsInline
                src="/yashi-avatar.mp4"
              />
            }
          />
          </Suspense>
        </button>

        <div className="pointer-events-none absolute inset-0 flex flex-col justify-between" ref={hudRef}>
          {/* Nameplate */}
          <div className="pt-5">
            <div className="flex items-stretch">
              <div className="bg-yashi-brand py-2 pl-5 pr-7 text-white [clip-path:polygon(0_0,100%_0,calc(100%-14px)_100%,0_100%)]">
                <div className="text-[1.45rem] font-black uppercase leading-none tracking-[0.2em]">{persona.name}</div>
              </div>
              <div className="-ml-3 flex items-center bg-white pl-6 pr-5 text-[0.78rem] font-black tracking-[0.25em] text-yashi-brand [clip-path:polygon(14px_0,100%_0,calc(100%-10px)_100%,0_100%)]">
                ♡
              </div>
            </div>
            <div className="mt-2.5 flex items-center gap-2 pl-5 text-[0.72rem] font-semibold tracking-wide text-white/75">
              <span className={getStatusDotClass(state.status.code)} />
              <span>{state.status.text}</span>
              {state.wakeWordActive ? (
                <span className="ml-1 rounded-sm border border-white/25 px-1.5 py-px text-[0.6rem] font-bold tracking-[0.18em] text-white/70">
                  WAKE WORD
                </span>
              ) : null}
            </div>
          </div>

          {/* Mood + reactions */}
          {!state.avatarFocus ? (
            <div className="bg-[linear-gradient(to_top,#000_0%,rgba(0,0,0,0.88)_55%,transparent_100%)] p-4 pt-16">
              <div className="mb-2 flex items-end justify-between gap-3">
                <div key={state.emotion} ref={popBadge}>
                  <div className="text-[0.6rem] font-bold uppercase tracking-[0.28em] text-white/45">Current mood</div>
                  <div className="flex items-baseline gap-2">
                    <span className="text-[1.15rem] font-black capitalize text-white">{state.emotion}</span>
                    <span className="text-[0.72rem] font-bold text-[#ff8da1]">{MOOD_NOTE[state.emotion] || ""}</span>
                  </div>
                </div>
                <span
                  className="rounded-sm border border-white/20 px-2 py-0.5 text-[0.6rem] font-bold uppercase tracking-[0.2em] text-white/65"
                  key={state.mode}
                  ref={popBadge}
                >
                  {state.mode}
                </span>
              </div>

              <div className="flex items-center gap-2" title={`Mood ${meterPercent}%`}>
                <span className="text-[0.9rem] font-black text-[#ff5c7a]">♡</span>
                <div className="h-[7px] flex-1 overflow-hidden bg-white/10 [clip-path:polygon(4px_0,100%_0,calc(100%-4px)_100%,0_100%)]">
                  <div className="h-full w-1/2 bg-[linear-gradient(90deg,#a30d25,#ff5c7a)]" ref={meterRef} />
                </div>
              </div>

              <div className="pointer-events-auto mt-3 grid grid-cols-3 gap-2">
                {REACTIONS.map((reaction) => (
                  <button
                    className={cx(
                      "border border-white/15 bg-white/[0.06] px-3 py-2 text-left text-white transition hover:border-[#ff5c7a] hover:bg-yashi-brand/40",
                      SLANT
                    )}
                    key={reaction.id}
                    onClick={(event) => {
                      pressFeedback(event.currentTarget);
                      react(reaction.id);
                    }}
                    type="button"
                  >
                    <div className="pl-1 text-[0.76rem] font-extrabold">{reaction.label}</div>
                    <div className="pl-1 text-[0.6rem] font-bold text-white/45">{reaction.hint}</div>
                  </button>
                ))}
              </div>
            </div>
          ) : null}
        </div>

        <button
          className="absolute right-4 top-5 rounded-md border border-white/25 bg-black/50 px-3 py-1.5 text-[0.72rem] font-extrabold tracking-wide text-white transition hover:border-white"
          onClick={() => setAvatarFocus(!state.avatarFocus)}
          type="button"
        >
          {state.avatarFocus ? "Exit focus" : "Focus"}
        </button>
      </section>

      {/* ── Focus mode: minimize / restore the chat ──────────────────────────── */}
      {state.avatarFocus ? (
        <button
          aria-label={chatHidden ? "Show chat" : "Hide chat"}
          className={cx(
            "absolute z-30 flex items-center justify-center bg-yashi-brand text-white shadow-[0_8px_24px_rgba(200,16,46,0.45)] transition-all duration-500 hover:bg-yashi-brand-strong",
            // phones: a tab on the top edge of the chat, slides to the bottom
            "left-1/2 h-7 w-16 -translate-x-1/2 rounded-t-lg",
            chatHidden ? "bottom-0" : "bottom-[calc(48vh+12px)]",
            // desktop: a tab on the left edge of the chat, slides to the right edge
            "min-[900px]:bottom-auto min-[900px]:left-auto min-[900px]:top-1/2 min-[900px]:h-16 min-[900px]:w-7 min-[900px]:translate-x-0 min-[900px]:-translate-y-1/2 min-[900px]:rounded-l-lg min-[900px]:rounded-tr-none",
            chatHidden ? "min-[900px]:right-0" : "min-[900px]:right-[446px]"
          )}
          onClick={() => setChatHidden((hidden) => !hidden)}
          title={chatHidden ? "Show chat" : "Hide chat"}
          type="button"
        >
          <svg aria-hidden="true" className="h-4 w-4" fill="none" stroke="currentColor" strokeLinecap="round"
            strokeLinejoin="round" strokeWidth="2.6" viewBox="0 0 24 24">
            {/* desktop arrows point left/right, phone arrows up/down */}
            <path className="min-[900px]:hidden" d={chatHidden ? "M6 15l6-6 6 6" : "M6 9l6 6 6-6"} />
            <path className="hidden min-[900px]:block" d={chatHidden ? "M15 6l-6 6 6 6" : "M9 6l6 6-6 6"} />
          </svg>
        </button>
      ) : null}

      {/* ── Dialogue ───────────────────────────────────────────────────────── */}
      <main
        aria-hidden={state.avatarFocus && chatHidden ? true : undefined}
        className={cx(
          "flex min-h-0 min-w-0 flex-col",
          state.avatarFocus
            ? "absolute inset-x-3 bottom-3 z-20 h-[48vh] overflow-hidden rounded-2xl border border-white/15 bg-[rgba(251,246,246,0.94)] shadow-[0_30px_80px_rgba(0,0,0,0.5)] backdrop-blur-xl transition-transform duration-500 ease-out min-[900px]:inset-x-auto min-[900px]:right-4 min-[900px]:top-16 min-[900px]:h-auto min-[900px]:w-[430px]"
            : "relative flex-1 bg-yashi-shell",
          state.avatarFocus && chatHidden && "pointer-events-none translate-y-[calc(100%+24px)] min-[900px]:translate-x-[calc(100%+24px)] min-[900px]:translate-y-0"
        )}
      >
        <header className="flex flex-wrap items-center gap-2 border-b border-yashi-border bg-white px-4 py-3">
          <div className="mr-auto leading-tight">
            <div className="text-[0.95rem] font-black tracking-wide">Conversation</div>
          </div>
          {state.micBar.on ? (
            <div className="flex min-w-0 max-w-[40%] items-center gap-1.5 text-[0.72rem] font-semibold text-yashi-brand">
              <span className="h-[7px] w-[7px] shrink-0 rounded-full bg-yashi-brand animate-[yashi-pulse_0.6s_infinite]" />
              <span className="truncate">{state.micBar.text}</span>
            </div>
          ) : null}
          <ChipButton onClick={newSession}>New chat</ChipButton>
          <ChipButton active={state.wakeWordActive} onClick={toggleWakeWord}>
            Wake word
          </ChipButton>
          <ChipButton onClick={() => dispatch({ type: "toggle_settings" })}>Settings</ChipButton>
          <a
            className="rounded-md border border-yashi-brand bg-yashi-brand px-3 py-1.5 text-[0.72rem] font-extrabold tracking-wide text-white transition hover:bg-yashi-brand-strong"
            href="#/dashboard/profile"
          >
            Dashboard
          </a>
        </header>

        <div className={cx("h-[3px] w-full bg-yashi-panel", state.volumeVisible ? "block" : "hidden")}>
          <div className="h-full w-0 bg-[linear-gradient(90deg,#a30d25,#ff5c7a)] transition-[width] duration-75" ref={volumeBarRef} />
        </div>

        <div
          className="yashi-scrollbar flex flex-1 flex-col gap-3 overflow-y-auto px-4 py-5 scroll-smooth"
          ref={logRef}
        >
          {state.messages.map((message, index) => {
            if (message.kind === "note") {
              return (
                <div
                  className="max-w-[88%] self-center whitespace-pre-wrap border-l-2 border-yashi-brand bg-yashi-safety-bg px-3.5 py-2 text-[0.78rem] leading-[1.6] text-yashi-safety-text"
                  key={message.id}
                  ref={enter(`n${message.id}`, messageEntrance("note"))}
                >
                  {message.text}
                </div>
              );
            }

            const isUser = message.role === "user";
            const previous = state.messages[index - 1];
            const showName =
              !isUser && !(previous && previous.kind === "message" && previous.role !== "user");

            return (
              <div
                className={cx("flex max-w-[82%] flex-col", isUser ? "items-end self-end" : "items-start self-start")}
                key={message.id}
                ref={enter(`m${message.id}`, messageEntrance(message.role))}
              >
                {showName ? (
                  <span className="mb-1 bg-yashi-brand py-0.5 pl-2.5 pr-3.5 text-[0.6rem] font-black uppercase tracking-[0.24em] text-white [clip-path:polygon(0_0,100%_0,calc(100%-6px)_100%,0_100%)]">
                    {persona.name}
                  </span>
                ) : null}
                <div className={getBubbleClass(message)}>{message.text}</div>
              </div>
            );
          })}

          {state.typing ? (
            <div className="flex self-start rounded-2xl rounded-bl-[5px] border border-yashi-bot-border bg-yashi-bot px-[15px] py-[11px]">
              {[0, 0.2, 0.4].map((delay, index) => (
                <div
                  className="mx-[2px] h-1.5 w-1.5 rounded-full bg-yashi-brand animate-[yashi-bounce_1.2s_infinite]"
                  key={index}
                  style={{ animationDelay: `${delay}s` }}
                />
              ))}
            </div>
          ) : null}
        </div>

        <div className="flex items-end gap-2 border-t border-yashi-border bg-white px-3 py-3">
          <span className="relative inline-flex shrink-0">
            <span
              aria-hidden="true"
              className="pointer-events-none absolute inset-0 rounded-full bg-yashi-brand opacity-0"
              ref={levelRing}
            />
            <button
              className={cx(
                "relative flex h-[42px] w-[42px] items-center justify-center rounded-full border text-[0.75rem] font-extrabold transition",
                state.micActive
                  ? "border-yashi-brand bg-yashi-brand text-white"
                  : "border-yashi-border bg-white text-yashi-muted hover:border-yashi-brand hover:text-yashi-brand"
              )}
              onClick={toggleMic}
              title={state.micActive ? "Stop listening" : "Talk to Yashi"}
              type="button"
            >
              Mic
            </button>
          </span>
          <textarea
            className="min-h-[44px] max-h-[140px] flex-1 resize-none rounded-xl border border-yashi-border bg-yashi-input px-4 py-[11px] text-[0.9rem] text-[#2b1a1d] outline-none transition placeholder:text-[#a68890] focus:border-yashi-brand focus:shadow-[0_0_0_3px_rgba(200,16,46,0.12)]"
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={handleInputKeyDown}
            placeholder="Say something to Yashi..."
            ref={textareaRef}
            rows="1"
            value={state.input}
          />
          <button
            className={cx(
              "h-[44px] shrink-0 px-6 text-[0.8rem] font-black tracking-[0.12em] transition",
              SLANT,
              state.typing
                ? "bg-[#fde8eb] text-[#a30d25] hover:bg-[#fbd5db]"
                : "bg-yashi-brand text-white hover:bg-yashi-brand-strong"
            )}
            onClick={(event) => {
              pressFeedback(event.currentTarget);
              (state.typing ? requestStop : sendCurrentInput)();
            }}
            title={state.typing ? "Stop response" : "Send"}
            type="button"
          >
            {state.typing ? "STOP" : "SEND"}
          </button>
        </div>
      </main>

      {/* ── Settings sheet ────────────────────────────────────────────────── */}
      {state.settingsOpen ? (
        <>
          <button
            aria-label="Close settings"
            className="fixed inset-0 z-40 bg-[rgba(26,4,8,0.35)]"
            onClick={() => dispatch({ type: "toggle_settings" })}
            type="button"
          />
          <aside
            className="fixed inset-y-0 right-0 z-50 flex w-[min(360px,92vw)] flex-col gap-6 overflow-y-auto bg-white p-5 shadow-[-20px_0_60px_rgba(0,0,0,0.25)]"
            ref={slideSheet}
          >
            <div className="flex items-start justify-between">
              <div className="leading-tight">
                <div className="text-[1.1rem] font-black tracking-wide">Settings</div>
              </div>
              <ChipButton onClick={() => dispatch({ type: "toggle_settings" })}>Close</ChipButton>
            </div>

            <div>
              <SectionLabel en="Brain" />
              <div className="grid grid-cols-2 gap-2">
                {LLM_OPTIONS.map((option) => (
                  <OptionCard
                    active={state.llmBackend === option.id}
                    hint={option.hint}
                    key={option.id}
                    label={option.label}
                    onClick={() => switchLLM(option.id)}
                  />
                ))}
              </div>
            </div>

            <div>
              <SectionLabel en="Voice" />
              <div className="grid grid-cols-2 gap-2">
                {TTS_OPTIONS.map((option) => (
                  <OptionCard
                    active={state.ttsBackend === option.id}
                    hint={option.hint}
                    key={option.id}
                    label={option.label}
                    onClick={() => switchTTS(option.id)}
                  />
                ))}
              </div>
            </div>

            <div>
              <SectionLabel en="Memory" />
              <div className="flex flex-wrap gap-2">
                <ChipButton onClick={() => openWindow("/api/memory/facts")}>Personal facts</ChipButton>
                <ChipButton onClick={() => openWindow("/api/memory/reflections")}>Reflections</ChipButton>
                <ChipButton onClick={() => openWindow("/health")}>Health check</ChipButton>
              </div>
            </div>
          </aside>
        </>
      ) : null}
    </div>
  );
}

export default App;
