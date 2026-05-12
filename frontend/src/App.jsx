import { startTransition, useEffect, useReducer, useRef } from "react";

// Avatar is now a video — no canvas animation needed

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
  mode: "standard",
  avatarFocus: false,
  mobileMenuOpen: false,
  micBar: { on: false, text: "Listening..." },
  volumeVisible: false,
  micActive: false,
  wakeWordActive: false,
  settingsOpen: false,
  llmBackend: "ollama",
  ttsBackend: "browser",
  typing: false,
  input: "",
  messages: [],
};

const SIDEBAR_BUTTON_CLASS =
  "w-full rounded-lg border border-yashi-border bg-yashi-panel px-3.5 py-[9px] text-left text-[0.8rem] font-semibold text-yashi-muted transition hover:border-yashi-brand-strong hover:bg-yashi-user hover:text-[#e8e4f0]";

const ROUND_BUTTON_BASE_CLASS =
  "flex h-[42px] min-w-[42px] shrink-0 items-center justify-center rounded-full border px-3 text-[0.82rem] font-bold transition";

const RECOGNITION_LANGUAGE =
  typeof navigator !== "undefined" && /^en/i.test(navigator.language || "")
    ? navigator.language
    : "en-US";

const WAKE_WORD_PATTERN =
  /\b(?:yashi|yashii|yashy|ya[\s-]?shi|ya[\s-]?she)\b/i;

const WAKE_WORD_FOLLOWUP_MS = 12000;
const WAKE_WORD_RESTART_MS = 850;
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

function extractWakeCommand(transcript) {
  const normalized = normalizeSpeechText(transcript);
  const words = normalized.split(" ").filter(Boolean);

  for (let index = 0; index < words.length; index += 1) {
    const single = words[index];
    const pair =
      index < words.length - 1 ? `${words[index]} ${words[index + 1]}` : "";

    if (isWakeLikePhrase(pair)) {
      return { heard: true, command: words.slice(index + 2).join(" ").trim() };
    }
    if (isWakeLikePhrase(single)) {
      return { heard: true, command: words.slice(index + 1).join(" ").trim() };
    }
  }

  const match = normalized.match(WAKE_WORD_PATTERN);
  if (!match || typeof match.index !== "number") {
    return { heard: false, command: "" };
  }

  return {
    heard: true,
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
      return `${base} bg-yashi-teal shadow-[0_0_8px_#4ecdc4]`;
    case "think":
      return `${base} bg-yashi-brand animate-[yashi-pulse_0.8s_infinite]`;
    case "listen":
      return `${base} bg-yashi-pink animate-[yashi-pulse_0.6s_infinite]`;
    case "busy":
      return `${base} bg-yashi-warn animate-[yashi-pulse_1s_infinite]`;
    case "err":
      return `${base} bg-yashi-danger`;
    default:
      return `${base} bg-[#5a5478]`;
  }
}

function getEmotionBadgeClass(emotion) {
  const base =
    "rounded-full border border-yashi-border bg-yashi-panel px-2.5 py-1 text-[0.7rem] font-semibold capitalize text-yashi-muted transition";

  switch (emotion) {
    case "happy":
    case "joyful":
      return `${base} border-[rgba(255,217,61,0.38)] bg-[#2a2010] text-[#ffd93d]`;
    case "sad":
      return `${base} border-[rgba(108,155,209,0.38)] bg-[#101a2a] text-[#6c9bd1]`;
    case "distressed":
      return `${base} border-[rgba(255,107,107,0.38)] bg-[#2a1010] text-[#ff6b6b]`;
    case "content":
      return `${base} border-[rgba(195,245,132,0.38)] bg-[#182010] text-[#c3f584]`;
    case "excited":
      return `${base} border-[rgba(255,159,243,0.38)] bg-[#2a1020] text-[#ff9ff3]`;
    default:
      return base;
  }
}

function getModeBadgeClass(mode) {
  const base =
    "rounded-full border border-yashi-border bg-yashi-panel px-2.5 py-1 text-[0.7rem] font-semibold capitalize text-yashi-muted transition";

  switch (mode) {
    case "support":
      return `${base} border-[rgba(78,205,196,0.38)] bg-[#101828] text-yashi-teal`;
    case "deep":
      return `${base} border-[rgba(155,142,247,0.38)] bg-[#1a1030] text-yashi-brand`;
    case "light":
      return `${base} border-[rgba(240,168,104,0.38)] bg-[#201a10] text-yashi-warn`;
    default:
      return base;
  }
}

function getBubbleClass(message) {
  const base =
    "rounded-2xl px-[15px] py-[11px] text-[0.9rem] leading-[1.65] whitespace-pre-wrap break-words";

  if (message.role === "user") {
    return `${base} rounded-br-[5px] border border-yashi-user-border bg-yashi-user text-[#f0ece4]`;
  }

  if (message.stream) {
    return `${base} rounded-bl-[5px] border border-yashi-brand-strong bg-yashi-bot text-[#e8e4f0] shadow-[0_0_10px_rgba(124,110,245,0.19)]`;
  }

  switch (message.emotion) {
    case "sad":
      return `${base} rounded-bl-[5px] border border-[rgba(108,155,209,0.25)] bg-yashi-bot text-[#e8e4f0]`;
    case "distressed":
      return `${base} rounded-bl-[5px] border border-[rgba(255,107,107,0.25)] bg-yashi-bot text-[#e8e4f0]`;
    case "happy":
    case "joyful":
      return `${base} rounded-bl-[5px] border border-[rgba(255,217,61,0.25)] bg-yashi-bot text-[#e8e4f0]`;
    default:
      return `${base} rounded-bl-[5px] border border-yashi-bot-border bg-yashi-bot text-[#e8e4f0]`;
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
    case "set_mobile_menu":
      return { ...state, mobileMenuOpen: !!action.value };
    case "toggle_mobile_menu":
      return { ...state, mobileMenuOpen: !state.mobileMenuOpen };
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

function App() {
  const [state, dispatch] = useReducer(reducer, initialState);

  const canvasRef = useRef(null);
  const glowRef = useRef(null);
  const logRef = useRef(null);
  const textareaRef = useRef(null);
  const volumeBarRef = useRef(null);

  const avatarRef = useRef(null);
  const wsRef = useRef(null);
  const reconnectTimerRef = useRef(0);
  const streamIdRef = useRef(null);
  const stopRequestedRef = useRef(false);
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

  function setMobileMenuOpen(value) {
    dispatch({ type: "set_mobile_menu", value });
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
                "Speech recognition is not available. In the desktop app, please type your message or use the Mic button after granting microphone permission."
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
      state.typing ||
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
        addNote(
          "Voice input is not available in the desktop app. Please type your message instead, or open http://localhost:8000 in Google Chrome for voice input."
        );
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
        addMessage("bot", data.message, "neutral");
        setStatus("ok", "Ready");
        avatarRef.current?.setThinking(false);
        break;
      case "emotion":
        setEmotion(data.current_emotion);
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

  function isDesktopApp() {
    // pywebview injects window.pywebview, or we can check user agent
    return typeof window.pywebview !== "undefined" ||
           navigator.userAgent.includes("pywebview");
  }

  function scheduleWakeWordRestart(delay = WAKE_WORD_RESTART_MS) {
    clearTimeout(wakeRestartTimerRef.current);

    if (!wakeEnabledRef.current || isDesktopApp()) return;

    wakeRestartTimerRef.current = window.setTimeout(() => {
      if (!wakeEnabledRef.current || wakeWordOnRef.current || micOnRef.current) {
        return;
      }
      startWakeWord({ silent: true });
    }, delay);
  }

  function startWakeWord(options = {}) {
    const { silent = false } = options;
    // Wake word requires Google Speech API — not available in pywebview desktop
    if (isDesktopApp()) {
      wakeEnabledRef.current = false;
      dispatch({ type: "set_wake_word", active: false });
      if (!silent) {
        addNote("Wake word is not available in desktop mode. Type your message or use the Mic button.");
      }
      return false;
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

    r.onresult = function (ev) {
      for (let i = ev.resultIndex; i < ev.results.length; i++) {
        let wakeMatch = { heard: false, command: "" };
        let bestScore = -100;

        for (let alt = 0; alt < ev.results[i].length; alt += 1) {
          const transcript = applySpeechCorrections(ev.results[i][alt].transcript || "");
          if (!transcript) continue;

          const candidate = extractWakeCommand(transcript);
          if (!candidate.heard) continue;

          const confidence =
            typeof ev.results[i][alt].confidence === "number"
              ? ev.results[i][alt].confidence
              : 0;
          const cmdWords = candidate.command.split(" ").filter(Boolean).length;
          const score = confidence + Math.min(1.5, cmdWords * 0.3);

          if (score > bestScore) {
            bestScore = score;
            wakeMatch = candidate;
          }
        }

        if (wakeMatch.heard) {
          // Wake word heard — activate mic and strip wake word from text
          const cmd = wakeMatch.command;
          // Wake word fired — activate mic silently (no note spam)
          // IMPORTANT: stop wake word recognizer before starting main mic
          // Two SpeechRecognition instances cannot run simultaneously in Chrome
          clearTimeout(wakeTimeoutRef.current);
          try { wakeRecogRef.current?.abort(); } catch (error) {}
          wakeWordOnRef.current = false;
          wakeRecogRef.current = null;

          if (cmd.length > 2) {
            const sent = sendText(cmd);
            scheduleWakeWordRestart(sent ? 1800 : 700);
          } else {
            wakeResumeAfterMicRef.current = true;
            wakeTriggeredMicRef.current = true;
            if (!micOnRef.current) toggleMic({ fromWakeWord: true });
            wakeTimeoutRef.current = window.setTimeout(() => {
              if (micOnRef.current) stopMic();
              else scheduleWakeWordRestart(500);
            }, WAKE_WORD_FOLLOWUP_MS);
          }
          break;
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
        addNote("Wake word lost connection to speech recognition. Retrying...");
        scheduleWakeWordRestart(WAKE_WORD_RETRY_MS);
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
    dispatch({ type: "set_wake_word", active: false });
  }

  // ── Settings API calls ──────────────────────────────────────────────────
  async function fetchSettings() {
    try {
      const r = await fetch("/api/settings/current");
      if (r.ok) {
        const d = await r.json();
        dispatch({ type: "set_backends", llm: d.llm_backend || "ollama", tts: d.tts_backend || "browser" });
      }
    } catch (_) {}
  }

  async function switchLLM(backend) {
    try {
      setMobileMenuOpen(false);
      setStatus("busy", "Switching LLM...");
      const r = await fetch(`/api/settings/llm/${backend}`, { method: "POST" });
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
      setMobileMenuOpen(false);
      const r = await fetch(`/api/settings/tts/${backend}`, { method: "POST" });
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

  // Avatar is a looping video — no canvas init needed.
  // avatarRef methods (setEmotion, startLip, etc.) are safe no-ops.
  // Glow colour is still driven by emotion via the glowRef.

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
    setMobileMenuOpen(false);
    window.open(path, "_blank", "noopener,noreferrer");
  }

  return (
    <div className="h-full">
      {state.mobileMenuOpen && !state.avatarFocus ? (
        <button
          aria-label="Close menu"
          className="fixed inset-0 z-40 hidden bg-[rgba(0,0,0,0.58)] max-[640px]:block"
          onClick={() => setMobileMenuOpen(false)}
          type="button"
        />
      ) : null}
      <div className="relative grid h-screen grid-cols-[270px_minmax(0,1fr)] bg-yashi-shell max-[640px]:grid-cols-1">
        <aside
          className={cx(
            "flex flex-col items-center gap-4 overflow-y-auto border-r border-yashi-border bg-yashi-sidebar px-4 py-6",
            "max-[640px]:fixed max-[640px]:inset-y-0 max-[640px]:left-0 max-[640px]:z-50 max-[640px]:w-[min(88vw,320px)] max-[640px]:max-w-full max-[640px]:shadow-[0_20px_60px_rgba(0,0,0,0.45)] max-[640px]:transition-transform max-[640px]:duration-300",
            state.mobileMenuOpen
              ? "max-[640px]:translate-x-0"
              : "max-[640px]:-translate-x-full max-[640px]:pointer-events-none"
          )}
        >
          <button
            className="hidden self-end rounded-full border border-[rgba(124,110,245,0.28)] bg-yashi-panel px-3 py-1.5 text-[0.72rem] font-semibold text-[#e8e4f0] max-[640px]:block"
            onClick={() => setMobileMenuOpen(false)}
            type="button"
          >
            Close
          </button>
          <div className="text-2xl font-bold tracking-[0.06em] text-yashi-brand">
            Yashi
          </div>
          <div className="-mt-2 text-[0.68rem] uppercase tracking-[0.12em] text-[#5a5478]">
            Local AI Companion
          </div>

          <div
            className={cx(
              state.avatarFocus
                ? "fixed inset-0 z-40 flex items-center justify-center bg-[radial-gradient(circle_at_top,rgba(40,34,70,0.94),rgba(14,14,26,0.97)_56%,#05050c)] p-6"
                : "relative my-2 h-[308px] w-[232px] overflow-visible"
            )}
          >
            {state.avatarFocus ? (
              <>
                <div className="absolute left-6 top-6 z-50 flex items-center gap-3 rounded-full border border-[rgba(124,110,245,0.32)] bg-[rgba(22,22,38,0.78)] px-4 py-2 text-sm font-semibold text-[#efeaff] shadow-[0_12px_30px_rgba(0,0,0,0.22)] backdrop-blur-xl">
                  <span>Avatar Focus</span>
                  <span className={getStatusDotClass(state.status.code)} />
                  <span className="text-yashi-muted">{state.status.text}</span>
                </div>
                <button
                  className="absolute right-6 top-6 z-50 rounded-full border border-[rgba(124,110,245,0.35)] bg-[rgba(22,22,38,0.78)] px-4 py-2 text-sm font-semibold text-[#efeaff] shadow-[0_12px_30px_rgba(0,0,0,0.22)] backdrop-blur-xl transition hover:border-yashi-brand-strong hover:bg-yashi-user"
                  onClick={() => setAvatarFocus(false)}
                  type="button"
                >
                  Exit Avatar
                </button>
              </>
            ) : null}
            <div
              className={cx(
                "pointer-events-none absolute transition-[background,box-shadow] duration-700",
                state.avatarFocus ? "inset-10 rounded-[56px]" : "-inset-6 rounded-[34px]"
              )}
              ref={glowRef}
              style={{
                background:
                  "radial-gradient(ellipse, rgba(245, 221, 171, 0.33) 0%, rgba(245, 221, 171, 0.08) 42%, transparent 76%)",
              }}
            />
            <div
              className={cx(
                "relative overflow-hidden bg-black transition-[width,height,box-shadow] duration-700",
                state.avatarFocus
                  ? "h-[min(80vh,977px)] w-[min(62vw,736px)] min-w-screen min-h-screen shadow-[0_36px_120px_rgba(0,0,0,0.45),inset_0_0_0_1px_rgba(255,246,227,0.3)]"
                  : "h-full w-full rounded-[30px] shadow-[inset_0_0_0_1px_rgba(255,246,227,0.3)]"
              )}
            >
              <video
                aria-label="Yashi avatar"
                className="block h-[99%] pt-[2%] w-full object-fit drop-shadow-[0_18px_30px_rgba(0,0,0,0.28)]"
                ref={canvasRef}
                autoPlay
                loop
                muted
                playsInline
                src="/static/yashi-avatar.mp4"
              />
            </div>
            {state.avatarFocus ? (
              <div className="pointer-events-none absolute bottom-4 left-1/2 z-50 -translate-x-1/2 rounded-full border border-[rgba(255,255,255,0.08)] bg-[rgba(12,12,20,0.55)] px-3 py-1 text-xs font-medium tracking-[0.08em] text-[#d6d0f2] uppercase backdrop-blur-xl">
                Press Esc to close
              </div>
            ) : null}
            {state.avatarFocus ? (
              <div className="absolute inset-x-6 bottom-6 z-50 ml-auto flex w-[min(430px,calc(100vw-48px))] flex-col gap-3">
                <div
                  className="yashi-scrollbar max-h-[42vh] overflow-y-auto rounded-[28px] border border-[rgba(124,110,245,0.24)] bg-[rgba(15,15,24,0.72)] p-4 shadow-[0_18px_50px_rgba(0,0,0,0.32)] backdrop-blur-xl"
                  ref={logRef}
                >
                  {state.messages.length === 0 ? (
                    <div className="rounded-2xl border border-[rgba(255,255,255,0.08)] bg-[rgba(255,255,255,0.03)] px-4 py-3 text-sm leading-6 text-[#ddd8f7]">
                      Chat with Yashi while watching the avatar in full-screen.
                    </div>
                  ) : (
                    state.messages.slice(-6).map((message) => {
                      if (message.kind === "note") {
                        return (
                          <div
                            className="mb-3 whitespace-pre-wrap rounded-[16px] border border-yashi-safety-border bg-yashi-safety-bg px-4 py-2.5 text-[0.8rem] leading-[1.6] text-yashi-safety-text animate-[yashi-fade-up_0.3s_ease-out]"
                            key={message.id}
                          >
                            {message.text}
                          </div>
                        );
                      }

                      return (
                        <div
                          className={cx(
                            "mb-3 flex animate-[yashi-fade-up_0.2s_ease-out]",
                            message.role === "user" ? "justify-end" : "justify-start"
                          )}
                          key={message.id}
                        >
                          <div className={cx(getBubbleClass(message), "max-w-full")}>
                            {message.text}
                          </div>
                        </div>
                      );
                    })
                  )}

                  {state.typing ? (
                    <div className="flex self-start rounded-2xl rounded-bl-[5px] border border-yashi-bot-border bg-yashi-bot px-[15px] py-[11px]">
                      {[0, 0.2, 0.4].map((delay, index) => (
                        <div
                          className="mx-[2px] h-1.5 w-1.5 rounded-full bg-[#5a5478] animate-[yashi-bounce_1.2s_infinite]"
                          key={index}
                          style={{ animationDelay: `${delay}s` }}
                        />
                      ))}
                    </div>
                  ) : null}
                </div>

                <div className="flex items-end gap-2 rounded-[30px] border border-[rgba(124,110,245,0.24)] bg-[rgba(22,22,38,0.84)] p-3 shadow-[0_18px_50px_rgba(0,0,0,0.32)] backdrop-blur-xl">
                  <button
                    className={cx(
                      ROUND_BUTTON_BASE_CLASS,
                      state.micActive
                        ? "border-yashi-rose bg-[#3a1020] text-yashi-rose animate-[yashi-pulse_0.8s_infinite]"
                        : "border-yashi-border bg-yashi-panel text-yashi-muted hover:border-yashi-brand-strong hover:bg-yashi-user hover:text-yashi-brand"
                    )}
                    onClick={toggleMic}
                    title="Click to toggle voice"
                    type="button"
                  >
                    Mic
                  </button>
                  <textarea
                    className="min-h-[44px] max-h-[140px] flex-1 resize-none rounded-[24px] border border-yashi-border bg-yashi-input px-4 py-[11px] text-[0.9rem] text-[#e8e4f0] outline-none transition placeholder:text-[#5a5478] focus:border-yashi-brand-strong focus:shadow-[0_0_0_3px_rgba(124,110,245,0.12)]"
                    onChange={(event) => setInput(event.target.value)}
                    onKeyDown={handleInputKeyDown}
                    placeholder="Type a message or click Mic to speak..."
                    ref={textareaRef}
                    rows="1"
                    value={state.input}
                  />
                  <button
                    className={cx(
                      ROUND_BUTTON_BASE_CLASS,
                      state.typing
                        ? "border-[rgba(255,107,107,0.45)] bg-[#3a1118] text-[#ff9ca9] hover:border-[#ff6b6b] hover:bg-[#4c1620]"
                        : "border-yashi-brand-strong bg-yashi-brand-strong text-white hover:scale-105 hover:bg-yashi-brand hover:text-white"
                    )}
                    onClick={state.typing ? requestStop : sendCurrentInput}
                    title={state.typing ? "Stop response" : "Send"}
                    type="button"
                  >
                    {state.typing ? "Stop" : "Send"}
                  </button>
                </div>
              </div>
            ) : null}
          </div>

          <div className="flex items-center gap-2 text-[0.8rem] text-yashi-muted">
            <div className={getStatusDotClass(state.status.code)} />
            <span>{state.status.text}</span>
          </div>

          <div className="flex flex-wrap justify-center gap-1.5">
            <span className={getEmotionBadgeClass(state.emotion)}>
              {state.emotion}
            </span>
            <span className={getModeBadgeClass(state.mode)}>{state.mode}</span>
          </div>

          <div className="mt-auto flex w-full flex-col gap-2">
            <button
              className={SIDEBAR_BUTTON_CLASS}
              onClick={() => {
                setMobileMenuOpen(false);
                if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
                  wsRef.current.send(JSON.stringify({ type: "new_session" }));
                }
              }}
              type="button"
            >
              New Session
            </button>

            {/* ── Backend toggle panel ────────────────────────────────── */}
            <div className="w-full rounded-lg border border-yashi-border bg-yashi-panel overflow-hidden">
              <button
                className="w-full px-3.5 py-[9px] text-left text-[0.8rem] font-semibold text-yashi-muted transition hover:text-[#e8e4f0] flex items-center justify-between"
                onClick={() => dispatch({ type: "toggle_settings" })}
                type="button"
              >
                <span>AI Settings</span>
                <span className="text-[0.65rem] opacity-60">{state.settingsOpen ? "▲" : "▼"}</span>
              </button>

              {state.settingsOpen && (
                <div className="px-3 pb-3 flex flex-col gap-3 border-t border-yashi-border pt-2.5">

                  {/* LLM Toggle */}
                  <div>
                    <div className="text-[0.68rem] uppercase tracking-[0.1em] text-[#5a5478] mb-1.5">
                      Brain (LLM)
                    </div>
                    <div className="flex gap-1.5">
                      <button
                        className={cx(
                          "flex-1 rounded-md py-1.5 text-[0.72rem] font-bold transition border",
                          state.llmBackend === "ollama"
                            ? "border-yashi-teal bg-[#0d2020] text-yashi-teal"
                            : "border-yashi-border bg-transparent text-yashi-muted hover:border-yashi-teal hover:text-yashi-teal"
                        )}
                        onClick={() => switchLLM("ollama")}
                        type="button"
                        title="Ollama — local AI, free, no internet needed"
                      >
                        Ollama
                      </button>
                      <button
                        className={cx(
                          "flex-1 rounded-md py-1.5 text-[0.72rem] font-bold transition border",
                          state.llmBackend === "openai"
                            ? "border-yashi-brand bg-[#130d30] text-yashi-brand"
                            : "border-yashi-border bg-transparent text-yashi-muted hover:border-yashi-brand hover:text-yashi-brand"
                        )}
                        onClick={() => switchLLM("openai")}
                        type="button"
                        title="OpenAI GPT-4o-mini — needs API key + internet"
                      >
                        OpenAI
                      </button>
                    </div>
                    <div className="mt-1 text-[0.62rem] text-[#5a5478]">
                      {state.llmBackend === "ollama"
                        ? "Local · Free · phi3:mini"
                        : "Cloud · GPT-4o-mini · API key required"}
                    </div>
                  </div>

                  {/* TTS Toggle */}
                  <div>
                    <div className="text-[0.68rem] uppercase tracking-[0.1em] text-[#5a5478] mb-1.5">
                      Voice (TTS)
                    </div>
                    <div className="flex gap-1.5 flex-col">
                      <div className="flex gap-1.5">
                        <button
                          className={cx(
                            "flex-1 rounded-md py-1.5 text-[0.72rem] font-bold transition border",
                            state.ttsBackend === "elevenlabs"
                              ? "border-yashi-pink bg-[#2a0820] text-yashi-pink"
                              : "border-yashi-border bg-transparent text-yashi-muted hover:border-yashi-pink hover:text-yashi-pink"
                          )}
                          onClick={() => switchTTS("elevenlabs")}
                          type="button"
                          title="ElevenLabs — human-quality AI voice, free 10k chars/month"
                        >
                          ElevenLabs
                        </button>
                        <button
                          className={cx(
                            "flex-1 rounded-md py-1.5 text-[0.72rem] font-bold transition border",
                            state.ttsBackend === "browser"
                              ? "border-yashi-warn bg-[#201a08] text-yashi-warn"
                              : "border-yashi-border bg-transparent text-yashi-muted hover:border-yashi-warn hover:text-yashi-warn"
                          )}
                          onClick={() => switchTTS("browser")}
                          type="button"
                          title="Browser built-in voice — free, works everywhere"
                        >
                          Browser
                        </button>
                      </div>
                    </div>
                    <div className="mt-1 text-[0.62rem] text-[#5a5478]">
                      {state.ttsBackend === "elevenlabs"
                        ? "Rachel AI · Human quality · API key needed"
                        : state.ttsBackend === "browser"
                        ? "Built-in · Free · Less natural"
                        : "Piper · Local · No internet"}
                    </div>
                  </div>

                  {/* Status indicators */}
                  <div className="flex gap-2 flex-wrap">
                    <span className={cx(
                      "rounded-full px-2 py-0.5 text-[0.6rem] font-semibold border",
                      state.llmBackend === "ollama"
                        ? "border-yashi-teal/40 bg-[#0d2020] text-yashi-teal"
                        : "border-yashi-brand/40 bg-[#130d30] text-yashi-brand"
                    )}>
                      {state.llmBackend === "ollama" ? "Ollama ON" : "OpenAI ON"}
                    </span>
                    <span className={cx(
                      "rounded-full px-2 py-0.5 text-[0.6rem] font-semibold border",
                      state.ttsBackend === "elevenlabs"
                        ? "border-yashi-pink/40 bg-[#2a0820] text-yashi-pink"
                        : "border-yashi-warn/40 bg-[#201a08] text-yashi-warn"
                    )}>
                      {state.ttsBackend === "elevenlabs" ? "ElevenLabs ON" : state.ttsBackend === "browser" ? "Browser Voice" : "Piper ON"}
                    </span>
                  </div>
                </div>
              )}
            </div>

            {/* ── Other buttons ───────────────────────────────────────── */}
            <button
              className={SIDEBAR_BUTTON_CLASS}
              onClick={() => openWindow("/api/memory/reflections")}
              type="button"
            >
              Reflections
            </button>
            <button
              className={SIDEBAR_BUTTON_CLASS}
              onClick={() => openWindow("/api/memory/facts")}
              type="button"
            >
              Personal Facts
            </button>
            <button
              className={SIDEBAR_BUTTON_CLASS}
              onClick={() => openWindow("/health")}
              type="button"
            >
              Health Check
            </button>
            <button
              className={SIDEBAR_BUTTON_CLASS}
              onClick={() => {
                setMobileMenuOpen(false);
                if (wakeEnabledRef.current) {
                  stopWakeWord();
                  addNote("Wake word deactivated.");
                } else {
                  const started = startWakeWord();
                  if (started) {
                    addNote("Wake word ON. Say \"Yashi\" and then your command, or say \"Yashi [command]\" in one go.");
                  }
                }
              }}
              type="button"
            >
              {state.wakeWordActive ? "Wake Word: ON" : "Enable Wake Word (Chrome only)"}
            </button>
            <button
              className={SIDEBAR_BUTTON_CLASS}
              onClick={() => {
                setMobileMenuOpen(false);
                setAvatarFocus(!state.avatarFocus);
              }}
              type="button"
            >
              {state.avatarFocus ? "Close Avatar" : "Avatar Focus"}
            </button>
          </div>
        </aside>

        <main className="flex h-screen min-w-0 flex-col bg-yashi-shell">
          <div className="flex items-center gap-2.5 border-b border-yashi-border bg-yashi-sidebar px-5 py-3.5 text-[0.95rem] font-semibold text-[#e8e4f0] max-[640px]:gap-2 max-[640px]:px-3.5 max-[640px]:py-3">
            <button
              className="hidden rounded-full border border-[rgba(124,110,245,0.28)] bg-yashi-panel px-3 py-1.5 text-xs font-semibold text-[#e8e4f0] max-[640px]:inline-flex"
              onClick={() => setMobileMenuOpen(true)}
              type="button"
            >
              Menu
            </button>
            <span>Conversation with Yashi</span>
            <div
              className={cx(
                "min-w-0 flex-1 items-center gap-1.5 text-[0.74rem] text-yashi-pink",
                state.micBar.on ? "flex" : "hidden"
              )}
            >
              <div className="h-[7px] w-[7px] shrink-0 rounded-full bg-yashi-pink animate-[yashi-pulse_0.6s_infinite]" />
              <span className="truncate">{state.micBar.text}</span>
            </div>
            <button
              className="rounded-full border border-[rgba(124,110,245,0.28)] bg-yashi-panel px-3 py-1.5 text-xs font-semibold text-[#e8e4f0] transition hover:border-yashi-brand-strong hover:bg-yashi-user max-[640px]:hidden"
              onClick={() => setAvatarFocus(!state.avatarFocus)}
              type="button"
            >
              {state.avatarFocus ? "Close Avatar" : "Avatar Focus"}
            </button>
          </div>

          <div
            className={cx(
              "mt-1 h-1 w-full overflow-hidden rounded-sm bg-yashi-panel",
              state.volumeVisible ? "block" : "hidden"
            )}
          >
            <div
              className="h-full w-0 rounded-sm bg-[linear-gradient(90deg,#4ecdc4,#9b8ef7)] transition-[width] duration-75"
              ref={volumeBarRef}
            />
          </div>

          {!state.avatarFocus ? (
            <>
              <div
                className="yashi-scrollbar flex flex-1 flex-col gap-2.5 overflow-y-auto px-4 py-5 scroll-smooth max-[640px]:gap-2 max-[640px]:px-3 max-[640px]:py-3"
                ref={logRef}
              >
                {state.messages.map((message) => {
                  if (message.kind === "note") {
                    return (
                      <div
                        className="max-w-[80%] self-center whitespace-pre-wrap rounded-[14px] border border-yashi-safety-border bg-yashi-safety-bg px-4 py-2.5 text-[0.82rem] leading-[1.6] text-yashi-safety-text animate-[yashi-fade-up_0.3s_ease-out]"
                        key={message.id}
                      >
                        {message.text}
                      </div>
                    );
                  }

                  return (
                    <div
                      className={cx(
                        "flex max-w-[78%] animate-[yashi-fade-up_0.2s_ease-out] max-[640px]:max-w-[90%]",
                        message.role === "user" ? "self-end" : "self-start"
                      )}
                      key={message.id}
                    >
                      <div className={getBubbleClass(message)}>{message.text}</div>
                    </div>
                  );
                })}

                {state.typing ? (
                  <div className="flex self-start rounded-2xl rounded-bl-[5px] border border-yashi-bot-border bg-yashi-bot px-[15px] py-[11px]">
                    {[0, 0.2, 0.4].map((delay, index) => (
                      <div
                        className="mx-[2px] h-1.5 w-1.5 rounded-full bg-[#5a5478] animate-[yashi-bounce_1.2s_infinite]"
                        key={index}
                        style={{ animationDelay: `${delay}s` }}
                      />
                    ))}
                  </div>
                ) : null}
              </div>

              <div className="flex items-end gap-2 border-t border-yashi-border bg-yashi-sidebar px-4 py-3.5 max-[640px]:gap-1.5 max-[640px]:px-3 max-[640px]:py-3">
                <button
                  className={cx(
                    ROUND_BUTTON_BASE_CLASS,
                    state.micActive
                      ? "border-yashi-rose bg-[#3a1020] text-yashi-rose animate-[yashi-pulse_0.8s_infinite]"
                      : "border-yashi-border bg-yashi-panel text-yashi-muted hover:border-yashi-brand-strong hover:bg-yashi-user hover:text-yashi-brand"
                  )}
                  onClick={toggleMic}
                  title="Click to toggle voice"
                  type="button"
                >
                  Mic
                </button>
                <textarea
                  className="min-h-[44px] max-h-[140px] flex-1 resize-none rounded-[24px] border border-yashi-border bg-yashi-input px-4 py-[11px] text-[0.9rem] text-[#e8e4f0] outline-none transition placeholder:text-[#5a5478] focus:border-yashi-brand-strong focus:shadow-[0_0_0_3px_rgba(124,110,245,0.12)] max-[640px]:min-h-[42px] max-[640px]:px-3 max-[640px]:py-[10px] max-[640px]:text-[0.86rem]"
                  onChange={(event) => setInput(event.target.value)}
                  onKeyDown={handleInputKeyDown}
                  placeholder="Type a message or click Mic to speak..."
                  ref={textareaRef}
                  rows="1"
                  value={state.input}
                />
                <button
                  className={cx(
                    ROUND_BUTTON_BASE_CLASS,
                    state.typing
                      ? "border-[rgba(255,107,107,0.45)] bg-[#3a1118] text-[#ff9ca9] hover:border-[#ff6b6b] hover:bg-[#4c1620]"
                      : "border-yashi-brand-strong bg-yashi-brand-strong text-white hover:scale-105 hover:bg-yashi-brand hover:text-white"
                  )}
                  onClick={state.typing ? requestStop : sendCurrentInput}
                  title={state.typing ? "Stop response" : "Send"}
                  type="button"
                >
                  {state.typing ? "Stop" : "Send"}
                </button>
              </div>
            </>
          ) : (
            <div className="flex flex-1 items-center justify-center px-6 text-center text-sm leading-7 text-yashi-muted">
              Avatar focus mode is active. Keep chatting with the floating composer over the full-screen avatar.
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

export default App;
