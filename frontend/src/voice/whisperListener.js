// Local voice input: mic -> voice-activity detection in the browser -> one
// POST per spoken sentence to /api/stt (Whisper on the Yashi backend).
//
// Used instead of the Web Speech API in browsers that block Google's speech
// service (Brave), so wake word and Mic work everywhere, fully on-device.

const TARGET_RATE = 16000;
const FRAME_SIZE = 2048;            // ~43 ms at 48 kHz
const MIN_RMS = 0.012;              // absolute floor for "this is speech"
const NOISE_MULTIPLIER = 3;         // speech must be this much louder than the room
const START_FRAMES = 3;             // ~130 ms of speech before we start recording
const PREROLL_FRAMES = 8;           // keep ~340 ms before the trigger (first syllable)
const END_SILENCE_MS = 750;         // pause that ends a sentence
const MIN_SPEECH_MS = 250;          // shorter bursts are clicks/coughs
const MAX_UTTERANCE_MS = 15000;

function rms(samples) {
  let sum = 0;
  for (let i = 0; i < samples.length; i += 1) sum += samples[i] * samples[i];
  return Math.sqrt(sum / samples.length);
}

function concat(chunks) {
  const length = chunks.reduce((total, chunk) => total + chunk.length, 0);
  const out = new Float32Array(length);
  let offset = 0;
  for (const chunk of chunks) {
    out.set(chunk, offset);
    offset += chunk.length;
  }
  return out;
}

function toPcm16At16k(samples, sourceRate) {
  const ratio = sourceRate / TARGET_RATE;
  const length = Math.floor(samples.length / ratio);
  const out = new Int16Array(length);
  for (let i = 0; i < length; i += 1) {
    const position = i * ratio;
    const index = Math.floor(position);
    const next = Math.min(index + 1, samples.length - 1);
    const value = samples[index] + (samples[next] - samples[index]) * (position - index);
    out[i] = Math.max(-1, Math.min(1, value)) * 0x7fff;
  }
  return out;
}

async function transcribe(pcm) {
  const response = await fetch("/api/stt", {
    method: "POST",
    headers: { "Content-Type": "application/octet-stream" },
    body: pcm.buffer,
  });
  if (!response.ok) throw new Error(`STT HTTP ${response.status}`);
  const data = await response.json();
  return (data.text || "").trim();
}

/**
 * @param {object} handlers
 * @param {(text: string) => void} handlers.onUtterance  final transcript of one sentence
 * @param {(speaking: boolean) => void} [handlers.onSpeech]
 * @param {(busy: boolean) => void} [handlers.onTranscribing]
 * @param {(percent: number) => void} [handlers.onLevel]
 * @param {() => boolean} [handlers.isMuted]  true while Yashi is talking (ignore her voice)
 * @param {(error: Error) => void} [handlers.onError]
 */
export function createWhisperListener(handlers) {
  const {
    onUtterance,
    onSpeech = () => {},
    onTranscribing = () => {},
    onLevel = () => {},
    isMuted = () => false,
    onError = () => {},
  } = handlers;

  let stream = null;
  let ctx = null;
  let source = null;
  let processor = null;
  let sink = null;
  let running = false;

  let noiseFloor = 0.006;
  let speaking = false;
  let speechRun = 0;
  let silenceMs = 0;
  let speechMs = 0;
  let utteranceMs = 0;
  let preroll = [];
  let chunks = [];
  let queue = Promise.resolve();

  function resetUtterance() {
    if (speaking) onSpeech(false);
    speaking = false;
    speechRun = 0;
    silenceMs = 0;
    speechMs = 0;
    utteranceMs = 0;
    chunks = [];
  }

  function finishUtterance() {
    const sampleRate = ctx.sampleRate;
    const captured = chunks;
    const longEnough = speechMs >= MIN_SPEECH_MS;
    resetUtterance();
    if (!longEnough || captured.length === 0) return;

    const pcm = toPcm16At16k(concat(captured), sampleRate);
    queue = queue.then(async () => {
      if (!running) return;
      onTranscribing(true);
      try {
        const text = await transcribe(pcm);
        if (running && text) onUtterance(text);
      } catch (error) {
        onError(error);
      } finally {
        onTranscribing(false);
      }
    });
  }

  function handleFrame(event) {
    if (!running) return;
    const input = event.inputBuffer.getChannelData(0);
    const frame = new Float32Array(input);   // the buffer is reused by the browser
    const frameMs = (frame.length / ctx.sampleRate) * 1000;
    const level = rms(frame);
    onLevel(Math.min(100, level * 900));

    // Don't record Yashi's own voice coming out of the speakers.
    if (isMuted()) {
      preroll = [];
      resetUtterance();
      return;
    }

    const threshold = Math.max(MIN_RMS, noiseFloor * NOISE_MULTIPLIER);
    const isSpeech = level > threshold;

    if (!speaking) {
      // Track the room's background level while nobody is talking.
      if (!isSpeech) noiseFloor = Math.max(0.002, noiseFloor * 0.95 + level * 0.05);
      preroll.push(frame);
      if (preroll.length > PREROLL_FRAMES) preroll.shift();
      speechRun = isSpeech ? speechRun + 1 : 0;
      if (speechRun >= START_FRAMES) {
        speaking = true;
        chunks = preroll.slice();
        preroll = [];
        speechMs = speechRun * frameMs;
        utteranceMs = chunks.length * frameMs;
        onSpeech(true);
      }
      return;
    }

    chunks.push(frame);
    utteranceMs += frameMs;
    if (isSpeech) {
      speechMs += frameMs;
      silenceMs = 0;
    } else {
      silenceMs += frameMs;
    }

    if (silenceMs >= END_SILENCE_MS || utteranceMs >= MAX_UTTERANCE_MS) {
      finishUtterance();
    }
  }

  async function start() {
    if (running) return;
    stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
      video: false,
    });
    const AudioContextCtor = window.AudioContext || window.webkitAudioContext;
    ctx = new AudioContextCtor();
    if (ctx.state === "suspended") await ctx.resume();
    source = ctx.createMediaStreamSource(stream);
    processor = ctx.createScriptProcessor(FRAME_SIZE, 1, 1);
    sink = ctx.createGain();
    sink.gain.value = 0;                     // keeps the processor running, silently
    processor.onaudioprocess = handleFrame;
    source.connect(processor);
    processor.connect(sink);
    sink.connect(ctx.destination);
    running = true;
  }

  function stop() {
    running = false;
    resetUtterance();
    preroll = [];
    onLevel(0);
    try { processor && (processor.onaudioprocess = null); } catch (error) {}
    try { source && source.disconnect(); } catch (error) {}
    try { processor && processor.disconnect(); } catch (error) {}
    try { sink && sink.disconnect(); } catch (error) {}
    if (stream) stream.getTracks().forEach((track) => track.stop());
    if (ctx) ctx.close().catch(() => {});
    stream = ctx = source = processor = sink = null;
  }

  return {
    start,
    stop,
    get running() {
      return running;
    },
  };
}
