/**
 * Voice input system.
 * Captures microphone audio via Web Audio API,
 * streams raw PCM int16 chunks to the voice WebSocket endpoint.
 */

const VoiceSystem = (() => {
  let audioCtx = null;
  let source = null;
  let processor = null;
  let stream = null;
  let ws = null;
  let isRecording = false;
  let onTranscript = null;
  let onVADUpdate = null;

  const SAMPLE_RATE = 16000;
  const CHUNK_SIZE  = 1600;   // 100ms at 16kHz

  async function start(websocketUrl, onTranscriptCb, onVADCb) {
    if (isRecording) return;
    onTranscript = onTranscriptCb;
    onVADUpdate  = onVADCb;

    // Open voice WebSocket
    ws = new WebSocket(websocketUrl);
    ws.binaryType = 'arraybuffer';

    await new Promise((res, rej) => {
      ws.onopen = res;
      ws.onerror = rej;
    });

    // Microphone
    stream = await navigator.mediaDevices.getUserMedia({ audio: {
      sampleRate: SAMPLE_RATE,
      channelCount: 1,
      echoCancellation: true,
      noiseSuppression: true,
    }});

    audioCtx = new AudioContext({ sampleRate: SAMPLE_RATE });
    source   = audioCtx.createMediaStreamSource(stream);
    processor = audioCtx.createScriptProcessor(CHUNK_SIZE, 1, 1);

    processor.onaudioprocess = (e) => {
      if (!isRecording || ws.readyState !== WebSocket.OPEN) return;
      const float32 = e.inputBuffer.getChannelData(0);
      const int16 = convertTo16BitPCM(float32);
      ws.send(int16.buffer);
      if (onVADUpdate) {
        const energy = computeEnergy(float32);
        onVADUpdate(energy);
      }
    };

    source.connect(processor);
    processor.connect(audioCtx.destination);
    isRecording = true;

    ws.onmessage = (evt) => {
      const data = JSON.parse(evt.data);
      if (data.type === 'transcript' && onTranscript) {
        onTranscript(data.text);
      }
    };

    ws.onclose = () => { isRecording = false; };
  }

  function stop() {
    isRecording = false;
    if (processor) { processor.disconnect(); processor = null; }
    if (source)    { source.disconnect(); source = null; }
    if (audioCtx)  { audioCtx.close(); audioCtx = null; }
    if (stream)    { stream.getTracks().forEach(t => t.stop()); stream = null; }
    if (ws && ws.readyState === WebSocket.OPEN) ws.close();
    ws = null;
  }

  function convertTo16BitPCM(float32) {
    const int16 = new Int16Array(float32.length);
    for (let i = 0; i < float32.length; i++) {
      const s = Math.max(-1, Math.min(1, float32[i]));
      int16[i] = s < 0 ? s * 32768 : s * 32767;
    }
    return int16;
  }

  function computeEnergy(float32) {
    let sum = 0;
    for (const s of float32) sum += s * s;
    return Math.sqrt(sum / float32.length);
  }

  return { start, stop, get isActive() { return isRecording; } };
})();
