/**
 * Yashi Audio Capture
 * Captures microphone input, sends PCM chunks over WebSocket for VAD+STT.
 */

const AudioCapture = (() => {
  let stream = null;
  let audioContext = null;
  let processor = null;
  let ws = null;
  let isCapturing = false;
  const SAMPLE_RATE = 16000;
  const CHUNK_SIZE = 1600; // 100ms @ 16kHz

  async function start(wsConnection) {
    if (isCapturing) return;
    ws = wsConnection;

    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: SAMPLE_RATE,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });

      audioContext = new AudioContext({ sampleRate: SAMPLE_RATE });
      const source = audioContext.createMediaStreamSource(stream);

      processor = audioContext.createScriptProcessor(CHUNK_SIZE, 1, 1);
      processor.onaudioprocess = (e) => {
        if (!isCapturing || !ws || ws.readyState !== WebSocket.OPEN) return;

        const float32 = e.inputBuffer.getChannelData(0);
        const int16 = float32ToInt16(float32);
        const b64 = arrayBufferToBase64(int16.buffer);

        ws.send(JSON.stringify({ type: 'audio', audio_chunk: b64 }));
      };

      source.connect(processor);
      processor.connect(audioContext.destination);
      isCapturing = true;

      console.log('[AudioCapture] Started @', SAMPLE_RATE, 'Hz');
      return true;
    } catch (err) {
      console.error('[AudioCapture] Error:', err);
      return false;
    }
  }

  function stop() {
    isCapturing = false;
    processor?.disconnect();
    stream?.getTracks().forEach(t => t.stop());
    audioContext?.close();
    processor = null;
    stream = null;
    audioContext = null;
    console.log('[AudioCapture] Stopped');
  }

  function float32ToInt16(f32) {
    const i16 = new Int16Array(f32.length);
    for (let i = 0; i < f32.length; i++) {
      const s = Math.max(-1, Math.min(1, f32[i]));
      i16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
    }
    return i16;
  }

  function arrayBufferToBase64(buf) {
    const bytes = new Uint8Array(buf);
    let binary = '';
    for (let i = 0; i < bytes.byteLength; i++) binary += String.fromCharCode(bytes[i]);
    return btoa(binary);
  }

  return { start, stop, get isActive() { return isCapturing; } };
})();

window.YashiAudio = AudioCapture;
