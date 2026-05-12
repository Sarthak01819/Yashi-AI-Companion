(function () {
  const IMAGE_URL = '/static/assets/ag1.jpeg';
  const SOURCE_WIDTH = 736;
  const SOURCE_HEIGHT = 977;

  const EMOTION_GLOW = {
    neutral: '#f5ddab55',
    happy: '#ffd37d70',
    joyful: '#ffcf8d80',
    content: '#f2d7a760',
    sad: '#b7c8f05e',
    concerned: '#f6c28d68',
    distressed: '#f8a0a066',
    excited: '#ffe39b7a'
  };

  const FEATURE = {
    leftEye: {
      x: 205,
      y: 244,
      w: 126,
      h: 86,
      coverX: 202,
      coverY: 206,
      coverW: 132,
      coverH: 40
    },
    rightEye: {
      x: 389,
      y: 221,
      w: 132,
      h: 84,
      coverX: 385,
      coverY: 188,
      coverW: 138,
      coverH: 38
    },
    mouth: {
      x: 318,
      y: 486,
      w: 74,
      h: 40
    }
  };

  const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
  const lerp = (a, b, t) => a + (b - a) * t;

  const state = {
    initialized: false,
    ready: false,
    emotion: 'neutral',
    listening: false,
    thinking: false,
    speaking: false,
    gazeX: 0,
    gazeY: 0,
    blinkStart: 0,
    nextBlink: 0,
    audioLevel: 0,
    fallbackLevel: 0,
    fallbackTimer: 0,
    analyser: null,
    audioData: null,
    audioRAF: 0,
    audioCtx: null
  };

  let wrapEl = null;
  let glowEl = null;
  let canvasEl = null;
  let ctx = null;
  let sourceImage = null;

  function init() {
    if (state.initialized) return;

    wrapEl = document.getElementById('av');
    glowEl = document.getElementById('aglow');
    canvasEl = document.getElementById('avatarCanvas');

    if (!wrapEl || !canvasEl) return;

    ctx = canvasEl.getContext('2d');
    state.initialized = true;

    setupCanvas();
    bindPointer();

    sourceImage = new Image();
    sourceImage.onload = function () {
      state.ready = true;
      scheduleBlink(performance.now());
      requestAnimationFrame(render);
    };
    sourceImage.src = IMAGE_URL;

    window.addEventListener('resize', setupCanvas);
  }

  function setupCanvas() {
    if (!canvasEl || !ctx) return;
    const dpr = window.devicePixelRatio || 1;
    canvasEl.width = Math.round(SOURCE_WIDTH * dpr);
    canvasEl.height = Math.round(SOURCE_HEIGHT * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = 'high';
  }

  function bindPointer() {
    document.addEventListener('mousemove', function (event) {
      if (!wrapEl) return;
      const rect = wrapEl.getBoundingClientRect();
      const px = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      const py = ((event.clientY - rect.top) / rect.height) * 2 - 1;
      state.gazeX = clamp(px, -1, 1);
      state.gazeY = clamp(py, -1, 1);
    });
  }

  function scheduleBlink(now) {
    state.blinkStart = 0;
    state.nextBlink = now + 1800 + Math.random() * 3000;
  }

  function blinkOpen(now) {
    if (!state.blinkStart) {
      if (now >= state.nextBlink) {
        state.blinkStart = now;
      } else {
        return 1;
      }
    }

    const elapsed = now - state.blinkStart;
    const closeMs = 80;
    const holdMs = 28;
    const openMs = 110;

    if (elapsed <= closeMs) {
      return lerp(1, 0.03, elapsed / closeMs);
    }
    if (elapsed <= closeMs + holdMs) {
      return 0.03;
    }
    if (elapsed <= closeMs + holdMs + openMs) {
      return lerp(0.03, 1, (elapsed - closeMs - holdMs) / openMs);
    }

    scheduleBlink(now);
    return 1;
  }

  function emotionGlow(emotion) {
    return EMOTION_GLOW[emotion] || EMOTION_GLOW.neutral;
  }

  function render(now) {
    if (!state.ready || !ctx || !sourceImage) {
      requestAnimationFrame(render);
      return;
    }

    const breath = Math.sin(now * 0.0022);
    const breathingScale = 1.014 + breath * 0.004;
    const tiltDeg = state.gazeX * 1.6 + (state.thinking ? -1.2 : 0) + (state.listening ? 0.5 : 0);
    const translateX = state.gazeX * 7;
    const translateY = state.gazeY * 4 + (state.thinking ? -3 : 0) + breath * 3.4;
    const eyeOpen = blinkOpen(now);
    const lipOpen = state.speaking ? Math.max(state.audioLevel, state.fallbackLevel) : 0;

    state.fallbackLevel *= 0.82;

    ctx.clearRect(0, 0, SOURCE_WIDTH, SOURCE_HEIGHT);

    ctx.save();
    ctx.translate(SOURCE_WIDTH / 2, SOURCE_HEIGHT / 2);
    ctx.rotate(tiltDeg * Math.PI / 180);
    ctx.scale(breathingScale, breathingScale);
    ctx.translate(-SOURCE_WIDTH / 2 + translateX, -SOURCE_HEIGHT / 2 + translateY);

    ctx.drawImage(sourceImage, 0, 0, SOURCE_WIDTH, SOURCE_HEIGHT);

    if (eyeOpen < 0.995) {
      drawEyeBlink(FEATURE.leftEye, eyeOpen);
      drawEyeBlink(FEATURE.rightEye, eyeOpen);
    }

    if (lipOpen > 0.035) {
      drawMouth(lipOpen);
    }

    ctx.restore();

    if (glowEl) {
      const glow = emotionGlow(state.emotion);
      glowEl.style.background =
        'radial-gradient(ellipse, ' + glow + ' 0%, rgba(255, 239, 210, 0.12) 44%, transparent 76%)';
      glowEl.style.boxShadow = '0 0 64px ' + glow;
    }

    requestAnimationFrame(render);
  }

  function drawEyeBlink(feature, open) {
    const closedAmount = 1 - open;

    ctx.save();

    ctx.drawImage(
      sourceImage,
      feature.coverX,
      feature.coverY,
      feature.coverW,
      feature.coverH,
      feature.x,
      feature.y,
      feature.w,
      feature.h
    );

    const squashedHeight = Math.max(3, feature.h * open);
    const squashedY = feature.y + (feature.h - squashedHeight) * 0.48;

    ctx.globalAlpha = clamp(0.55 + open * 0.45, 0, 1);
    ctx.drawImage(
      sourceImage,
      feature.x,
      feature.y,
      feature.w,
      feature.h,
      feature.x,
      squashedY,
      feature.w,
      squashedHeight
    );

    ctx.globalAlpha = 0.85;
    ctx.drawImage(
      sourceImage,
      feature.x,
      feature.y + 4,
      feature.w,
      12,
      feature.x,
      feature.y + feature.h * 0.45,
      feature.w,
      Math.max(5, 8 - open * 3)
    );

    ctx.globalAlpha = clamp(closedAmount * 0.20, 0, 0.20);
    ctx.fillStyle = '#8f695f';
    ctx.fillRect(feature.x, feature.y + feature.h * 0.50, feature.w, 3);

    ctx.restore();
  }

  function drawMouth(open) {
    const mouth = FEATURE.mouth;
    const stretch = 1 + open * 0.55;
    const targetHeight = mouth.h * stretch;
    const targetY = mouth.y - (targetHeight - mouth.h) * 0.35;

    ctx.save();
    ctx.beginPath();
    ctx.ellipse(
      mouth.x + mouth.w / 2,
      mouth.y + mouth.h / 2 + open * 5,
      mouth.w * 0.55,
      mouth.h * (0.58 + open * 0.30),
      0,
      0,
      Math.PI * 2
    );
    ctx.clip();

    ctx.globalAlpha = 0.90;
    ctx.drawImage(
      sourceImage,
      mouth.x,
      mouth.y - 2,
      mouth.w,
      mouth.h + 4,
      mouth.x - 1,
      targetY,
      mouth.w + 2,
      targetHeight
    );

    ctx.globalAlpha = 0.16 + open * 0.32;
    ctx.fillStyle = '#4f1724';
    ctx.beginPath();
    ctx.ellipse(
      mouth.x + mouth.w / 2,
      mouth.y + mouth.h / 2 + open * 6,
      mouth.w * (0.20 + open * 0.12),
      mouth.h * (0.12 + open * 0.26),
      0,
      0,
      Math.PI * 2
    );
    ctx.fill();

    ctx.restore();
  }

  function ensureAudioContext() {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return null;
    if (!state.audioCtx) {
      state.audioCtx = new Ctx();
    }
    if (state.audioCtx.state === 'suspended') {
      state.audioCtx.resume().catch(function () {});
    }
    return state.audioCtx;
  }

  function stopAudioTracking() {
    if (state.audioRAF) {
      cancelAnimationFrame(state.audioRAF);
      state.audioRAF = 0;
    }
    if (state.analyser) {
      try { state.analyser.disconnect(); } catch (error) {}
      state.analyser = null;
    }
    state.audioData = null;
    state.audioLevel = 0;
  }

  function pollAudioLevel() {
    if (!state.analyser || !state.audioData) return;
    state.analyser.getByteFrequencyData(state.audioData);
    let total = 0;
    for (let i = 0; i < state.audioData.length; i++) total += state.audioData[i];
    const avg = total / state.audioData.length;
    state.audioLevel = clamp((avg - 8) / 54, 0, 1);
    state.audioRAF = requestAnimationFrame(pollAudioLevel);
  }

  function startFallbackLip() {
    clearInterval(state.fallbackTimer);
    state.fallbackTimer = setInterval(function () {
      state.fallbackLevel = 0.12 + Math.random() * 0.48;
    }, 95);
  }

  function startLip(audioEl) {
    state.speaking = true;
    state.audioLevel = 0;
    state.fallbackLevel = 0.18;

    clearInterval(state.fallbackTimer);
    state.fallbackTimer = 0;
    stopAudioTracking();

    if (!audioEl) {
      startFallbackLip();
      return;
    }

    const audioCtx = ensureAudioContext();
    if (!audioCtx) {
      startFallbackLip();
      return;
    }

    try {
      if (!audioEl._yashiSourceNode) {
        const sourceNode = audioCtx.createMediaElementSource(audioEl);
        sourceNode.connect(audioCtx.destination);
        audioEl._yashiSourceNode = sourceNode;
      }

      state.analyser = audioCtx.createAnalyser();
      state.analyser.fftSize = 128;
      state.audioData = new Uint8Array(state.analyser.frequencyBinCount);
      audioEl._yashiSourceNode.connect(state.analyser);
      pollAudioLevel();
    } catch (error) {
      startFallbackLip();
    }
  }

  function stopLip() {
    state.speaking = false;
    state.fallbackLevel = 0;
    clearInterval(state.fallbackTimer);
    state.fallbackTimer = 0;
    stopAudioTracking();
  }

  function setEmotion(emotion) {
    state.emotion = emotion || 'neutral';
  }

  function setListening(active) {
    state.listening = !!active;
  }

  function setThinking(active) {
    state.thinking = !!active;
  }

  window.Live2DGirl = {
    init: init,
    setEmotion: setEmotion,
    setListening: setListening,
    setThinking: setThinking,
    startLip: startLip,
    stopLip: stopLip
  };
})();
