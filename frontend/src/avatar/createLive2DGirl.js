import imageUrl from "../../assets/ag1.jpeg";

// ─────────────────────────────────────────────────────────────────────────────
//  Yashi Avatar Engine  —  Canvas-based anime character with full animation rig
//
//  Animations implemented:
//    • Natural blinking (random interval, occasional double-blink)
//    • Smooth eye-gaze tracking with lerped follow and lag
//    • Breathing — subtle vertical bob + scale, emotion-speed-scaled
//    • Idle head sway — slow sine drift left/right
//    • Thinking pose — head tilts left, micro-bounce, slightly raised
//    • Listening state — slight lean forward, rapid micro-sways
//    • Lip sync — real-time audio analyser OR fallback random flutter
//    • Emotion reactions — each emotion has a unique body language signature
//    • Emotion glow — coloured radial overlay on the glow element
//    • Squint — eyes narrow on happy/joyful
//    • Hair parallax — front hair shifts slightly behind gaze
//    • Bounce impulse — a snappy bounce fires on new messages
//    • Fade-in on load
// ─────────────────────────────────────────────────────────────────────────────

const SW = 736;   // source image width
const SH = 977;   // source image height

// ── Eye / mouth pixel regions in the source image ────────────────────────────
const FEATURE = {
  leftEye:  { x: 205, y: 244, w: 126, h: 86,  coverX: 202, coverY: 206, coverW: 132, coverH: 40 },
  rightEye: { x: 389, y: 221, w: 132, h: 84,  coverX: 385, coverY: 188, coverW: 138, coverH: 38 },
  mouth:    { x: 318, y: 486, w: 74,  h: 40 },
};

// ── Per-emotion configuration ────────────────────────────────────────────────
const EMOTION_CONFIG = {
  neutral:    { glow: "#f5ddab55", breathSpeed: 1.0,  swayAmp: 1.0,  squint: 0,    tilt: 0,     bounceDecay: 0.88 },
  happy:      { glow: "#ffd37d70", breathSpeed: 1.25, swayAmp: 1.3,  squint: 0.25, tilt:  1.5,  bounceDecay: 0.84 },
  joyful:     { glow: "#ffcf8d80", breathSpeed: 1.4,  swayAmp: 1.6,  squint: 0.40, tilt:  2.0,  bounceDecay: 0.80 },
  content:    { glow: "#f2d7a760", breathSpeed: 0.85, swayAmp: 0.8,  squint: 0.10, tilt:  0.5,  bounceDecay: 0.90 },
  sad:        { glow: "#b7c8f05e", breathSpeed: 0.65, swayAmp: 0.5,  squint: 0,    tilt: -2.5,  bounceDecay: 0.93 },
  concerned:  { glow: "#f6c28d68", breathSpeed: 0.80, swayAmp: 0.7,  squint: 0,    tilt: -1.0,  bounceDecay: 0.91 },
  distressed: { glow: "#f8a0a066", breathSpeed: 1.5,  swayAmp: 0.4,  squint: 0,    tilt: -3.0,  bounceDecay: 0.94 },
  excited:    { glow: "#ffe39b7a", breathSpeed: 1.6,  swayAmp: 2.0,  squint: 0.18, tilt:  1.0,  bounceDecay: 0.78 },
};

function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }
function lerp(a, b, t)    { return a + (b - a) * t; }
function easeOut(t)        { return 1 - (1 - t) * (1 - t); }

// ─────────────────────────────────────────────────────────────────────────────
export function createLive2DGirl({ canvas, glow }) {
  const ctx = canvas.getContext("2d");
  const img = new Image();

  // ── Mutable animation state ───────────────────────────────────────────────
  const s = {
    ready:       false,
    destroyed:   false,
    loaded:      false,
    loadAlpha:   0,        // fade-in 0→1

    // emotion
    emotion:     "neutral",

    // blink
    blinkOpen:     1,      // 1 = fully open, 0 = fully closed
    blinkPhase:    "idle", // idle | closing | hold | opening
    blinkElapsed:  0,
    blinkNext:     0,
    doubleBlink:   false,
    doublePhase:   0,

    // gaze — raw target
    gazeTX: 0, gazeTY: 0,
    // gaze — smoothed current
    gazeX: 0,  gazeY: 0,
    // hair parallax — lags behind gaze
    hairX: 0,  hairY: 0,

    // breath
    breathT: 0,

    // idle head sway
    swayT: 0,
    swayPhase: Math.random() * Math.PI * 2,

    // thinking
    thinking: false,
    thinkBob: 0, thinkBobDir: 1,

    // listening
    listening: false,

    // bounce impulse (triggered on new message)
    bounceY: 0, bounceV: 0,

    // speaking / lip
    speaking: false,
    audioLevel: 0,
    fallbackLevel: 0,
    fallbackTimer: 0,
    analyser: null,
    audioData: null,
    audioFrame: 0,
    audioCtx: null,
  };

  let raf = 0;
  let prevNow = performance.now();

  // ── Canvas DPI setup ──────────────────────────────────────────────────────
  function setupCanvas() {
    const dpr = window.devicePixelRatio || 1;
    canvas.width  = Math.round(SW * dpr);
    canvas.height = Math.round(SH * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = "high";
  }

  // ── Blink state machine ───────────────────────────────────────────────────
  const BLINK = { closeMs: 75, holdMs: 22, openMs: 100 };

  function scheduleBlink() {
    s.blinkNext    = 2000 + Math.random() * 4500;
    s.blinkElapsed = 0;
    s.blinkPhase   = "idle";
    s.blinkOpen    = 1;
    // 15 % chance of a double-blink
    s.doubleBlink  = Math.random() < 0.15;
    s.doublePhase  = 0;
  }

  function tickBlink(dt) {
    if (s.blinkPhase === "idle") {
      s.blinkNext -= dt;
      if (s.blinkNext <= 0) s.blinkPhase = "closing";
      return;
    }
    s.blinkElapsed += dt;
    const { closeMs, holdMs, openMs } = BLINK;
    const total = closeMs + holdMs + openMs;

    if (s.blinkPhase === "closing" || s.blinkPhase === "hold" || s.blinkPhase === "opening") {
      if (s.blinkElapsed <= closeMs) {
        s.blinkOpen = lerp(1, 0.02, easeOut(s.blinkElapsed / closeMs));
      } else if (s.blinkElapsed <= closeMs + holdMs) {
        s.blinkOpen = 0.02;
      } else if (s.blinkElapsed <= total) {
        s.blinkOpen = lerp(0.02, 1, easeOut((s.blinkElapsed - closeMs - holdMs) / openMs));
      } else {
        s.blinkOpen = 1;
        if (s.doubleBlink && s.doublePhase === 0) {
          s.doublePhase   = 1;
          s.blinkElapsed  = 0;
          // slight pause before second blink
          s.blinkNext     = 95;
          s.blinkPhase    = "idle";
        } else {
          scheduleBlink();
        }
      }
    }
  }

  // ── Draw a single eye with blink + squint ─────────────────────────────────
  function drawEye(feat, openAmount, squint) {
    // squint: 0 = fully open, 1 = half closed (happy face)
    const effectiveOpen = openAmount * (1 - squint * 0.48);

    // cover strip (skin over eye = closed-lid colour)
    ctx.save();
    ctx.drawImage(img,
      feat.coverX, feat.coverY, feat.coverW, feat.coverH,
      feat.x,      feat.y,      feat.w,      feat.h
    );

    const sh = Math.max(2, feat.h * effectiveOpen);
    const sy = feat.y + (feat.h - sh) * 0.45;

    // eye graphic — vertically squashed
    ctx.globalAlpha = clamp(0.55 + effectiveOpen * 0.45, 0, 1);
    ctx.drawImage(img, feat.x, feat.y, feat.w, feat.h,
                       feat.x, sy,     feat.w, sh);

    // lash shadow at bottom
    ctx.globalAlpha = 0.82;
    ctx.drawImage(img, feat.x, feat.y + 4, feat.w, 10,
                       feat.x, feat.y + feat.h * 0.42, feat.w,
                       Math.max(4, 7 - effectiveOpen * 3));

    // dark crease when closing
    const crease = 1 - effectiveOpen;
    if (crease > 0.05) {
      ctx.globalAlpha = crease * 0.18;
      ctx.fillStyle = "#7a4a45";
      ctx.fillRect(feat.x, feat.y + feat.h * 0.48, feat.w, 3);
    }

    ctx.restore();
  }

  // ── Mouth / lip sync ──────────────────────────────────────────────────────
  function drawMouth(lipOpen) {
    const { x, y, w, h } = FEATURE.mouth;
    const stretch   = 1 + lipOpen * 0.60;
    const mouthH    = h * stretch;
    const mouthY    = y - (mouthH - h) * 0.30;

    ctx.save();
    // clip to rounded ellipse
    ctx.beginPath();
    ctx.ellipse(x + w / 2, y + h / 2 + lipOpen * 5, w * 0.54, h * (0.55 + lipOpen * 0.32), 0, 0, Math.PI * 2);
    ctx.clip();

    ctx.globalAlpha = 0.92;
    ctx.drawImage(img, x, y - 2, w, h + 4,  x - 1, mouthY, w + 2, mouthH);

    // dark interior when open
    if (lipOpen > 0.05) {
      ctx.globalAlpha = 0.12 + lipOpen * 0.36;
      ctx.fillStyle = "#3e1220";
      ctx.beginPath();
      ctx.ellipse(x + w / 2, y + h / 2 + lipOpen * 7,
                  w * (0.18 + lipOpen * 0.14), h * (0.10 + lipOpen * 0.28),
                  0, 0, Math.PI * 2);
      ctx.fill();

      // teeth glint
      ctx.globalAlpha = 0.10 + lipOpen * 0.12;
      ctx.fillStyle = "#fff8f0";
      ctx.beginPath();
      ctx.ellipse(x + w / 2, y + h * 0.38 + lipOpen * 4,
                  w * (0.22 + lipOpen * 0.08), h * (0.06 + lipOpen * 0.08),
                  0, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();
  }

  // ── Main render loop ──────────────────────────────────────────────────────
  function render(now) {
    if (s.destroyed) return;
    const dt = clamp(now - prevNow, 0, 50);
    prevNow = now;

    if (!s.ready) { raf = requestAnimationFrame(render); return; }

    // ── Load fade-in ──────────────────────────────────────────────────────
    if (s.loadAlpha < 1) s.loadAlpha = Math.min(1, s.loadAlpha + dt * 0.003);

    const cfg = EMOTION_CONFIG[s.emotion] || EMOTION_CONFIG.neutral;

    // ── Smooth gaze lerp ──────────────────────────────────────────────────
    const gazeSmooth = 0.045;
    s.gazeX = lerp(s.gazeX, s.gazeTX, gazeSmooth);
    s.gazeY = lerp(s.gazeY, s.gazeTY, gazeSmooth);
    // hair lags even further behind
    s.hairX = lerp(s.hairX, s.gazeX * 0.45, 0.025);
    s.hairY = lerp(s.hairY, s.gazeY * 0.25, 0.025);

    // ── Blink ─────────────────────────────────────────────────────────────
    tickBlink(dt);

    // ── Breathing ─────────────────────────────────────────────────────────
    s.breathT += dt * 0.0018 * cfg.breathSpeed;
    const breath       = Math.sin(s.breathT);
    const breathScale  = 1.012 + breath * 0.005;
    const breathTransY = breath * 3.2;

    // ── Idle head sway ────────────────────────────────────────────────────
    s.swayT += dt * 0.00045 * cfg.swayAmp;
    const sway = Math.sin(s.swayT + s.swayPhase) * 1.8 * cfg.swayAmp;

    // ── Thinking ──────────────────────────────────────────────────────────
    let thinkTilt = 0, thinkTransY = 0;
    if (s.thinking) {
      s.thinkBob += dt * 0.0042 * s.thinkBobDir;
      if (Math.abs(s.thinkBob) > 1) s.thinkBobDir *= -1;
      thinkTilt   = -8 + Math.sin(s.thinkBob * Math.PI) * 1.5;
      thinkTransY = -6 + s.thinkBob * 2;
    }

    // ── Listening ─────────────────────────────────────────────────────────
    let listenSway = 0;
    if (s.listening) {
      listenSway = Math.sin(now * 0.006) * 2.2;
    }

    // ── Bounce impulse ────────────────────────────────────────────────────
    s.bounceV  *= cfg.bounceDecay;
    s.bounceY  += s.bounceV;
    s.bounceY  *= 0.78;  // spring back to 0

    // ── Lip open amount ───────────────────────────────────────────────────
    const lipOpen = s.speaking
      ? clamp(Math.max(s.audioLevel, s.fallbackLevel), 0, 1)
      : 0;
    s.fallbackLevel *= 0.80;

    // ── Squint ────────────────────────────────────────────────────────────
    const squint = cfg.squint;

    // ── Composite tilt ────────────────────────────────────────────────────
    const totalTilt = cfg.tilt + sway + thinkTilt + listenSway + s.gazeX * 2.5;
    const totalTransX = s.gazeX * 8;
    const totalTransY = s.gazeY * 4 + breathTransY + thinkTransY + s.bounceY;

    // ── Draw ──────────────────────────────────────────────────────────────
    ctx.clearRect(0, 0, SW, SH);
    ctx.save();
    ctx.globalAlpha = s.loadAlpha;
    ctx.translate(SW / 2, SH / 2);
    ctx.rotate((totalTilt * Math.PI) / 180);
    ctx.scale(breathScale, breathScale);
    ctx.translate(-SW / 2 + totalTransX, -SH / 2 + totalTransY);

    // Base image
    ctx.drawImage(img, 0, 0, SW, SH);

    // Eye blink + squint
    if (s.blinkOpen < 0.995 || squint > 0.01) {
      drawEye(FEATURE.leftEye,  s.blinkOpen, squint);
      drawEye(FEATURE.rightEye, s.blinkOpen, squint);
    }

    // Mouth
    if (lipOpen > 0.03) drawMouth(lipOpen);

    ctx.restore();

    // ── Glow element ──────────────────────────────────────────────────────
    if (glow) {
      const gc = (EMOTION_CONFIG[s.emotion] || EMOTION_CONFIG.neutral).glow;
      glow.style.background = `radial-gradient(ellipse, ${gc} 0%, rgba(255,239,210,0.10) 44%, transparent 76%)`;
      glow.style.boxShadow  = `0 0 72px ${gc}`;
    }

    raf = requestAnimationFrame(render);
  }

  // ── Audio helpers ─────────────────────────────────────────────────────────
  function stopAudioTracking() {
    if (s.audioFrame) { cancelAnimationFrame(s.audioFrame); s.audioFrame = 0; }
    try { s.analyser?.disconnect(); } catch (_) {}
    s.analyser = null; s.audioData = null; s.audioLevel = 0;
  }

  function ensureAudioCtx() {
    const Ctor = window.AudioContext || window.webkitAudioContext;
    if (!Ctor) return null;
    if (!s.audioCtx) s.audioCtx = new Ctor();
    if (s.audioCtx.state === "suspended") s.audioCtx.resume().catch(() => {});
    return s.audioCtx;
  }

  function pollAudio() {
    if (!s.analyser || !s.audioData) return;
    s.analyser.getByteFrequencyData(s.audioData);
    let sum = 0;
    for (let i = 0; i < s.audioData.length; i++) sum += s.audioData[i];
    s.audioLevel = clamp((sum / s.audioData.length - 8) / 52, 0, 1);
    s.audioFrame = requestAnimationFrame(pollAudio);
  }

  function startFallbackLip() {
    clearInterval(s.fallbackTimer);
    s.fallbackTimer = window.setInterval(() => {
      s.fallbackLevel = 0.10 + Math.random() * 0.52;
    }, 90 + Math.random() * 30);
  }

  // ── Pointer tracking ──────────────────────────────────────────────────────
  function onPointerMove(e) {
    const r = canvas.getBoundingClientRect();
    s.gazeTX = clamp(((e.clientX - r.left) / r.width)  * 2 - 1, -1, 1);
    s.gazeTY = clamp(((e.clientY - r.top)  / r.height) * 2 - 1, -1, 1);
  }

  // ── Public API ────────────────────────────────────────────────────────────
  function startLip(audioEl) {
    s.speaking = true;
    s.audioLevel = 0;
    s.fallbackLevel = 0.18;
    clearInterval(s.fallbackTimer);
    stopAudioTracking();

    if (!audioEl) { startFallbackLip(); return; }

    const actx = ensureAudioCtx();
    if (!actx) { startFallbackLip(); return; }

    try {
      if (!audioEl._yashiNode) {
        const src = actx.createMediaElementSource(audioEl);
        src.connect(actx.destination);
        audioEl._yashiNode = src;
      }
      s.analyser  = actx.createAnalyser();
      s.analyser.fftSize = 128;
      s.audioData = new Uint8Array(s.analyser.frequencyBinCount);
      audioEl._yashiNode.connect(s.analyser);
      pollAudio();
    } catch (_) {
      startFallbackLip();
    }
  }

  function stopLip() {
    s.speaking = false;
    s.fallbackLevel = 0;
    clearInterval(s.fallbackTimer);
    s.fallbackTimer = 0;
    stopAudioTracking();
  }

  function setEmotion(emotion) {
    const prev = s.emotion;
    s.emotion = emotion || "neutral";
    // fire a small bounce when emotion changes to positive
    if (prev !== s.emotion && ["happy","joyful","excited"].includes(s.emotion)) {
      s.bounceV = -4.5;
    }
  }

  function setListening(active) {
    s.listening = Boolean(active);
  }

  function setThinking(active) {
    s.thinking = Boolean(active);
    if (active) { s.thinkBob = 0; s.thinkBobDir = 1; }
  }

  // Call this when Yashi sends a new message to get a cute bounce
  function triggerBounce() {
    s.bounceV = -6;
  }

  function destroy() {
    s.destroyed = true;
    clearInterval(s.fallbackTimer);
    stopAudioTracking();
    s.audioCtx?.close().catch(() => {});
    cancelAnimationFrame(raf);
    document.removeEventListener("pointermove", onPointerMove);
    window.removeEventListener("resize", setupCanvas);
  }

  // ── Boot ──────────────────────────────────────────────────────────────────
  setupCanvas();
  scheduleBlink();
  document.addEventListener("pointermove", onPointerMove);
  window.addEventListener("resize", setupCanvas);

  img.onload = () => {
    if (s.destroyed) return;
    s.ready = true;
    raf = requestAnimationFrame(render);
  };
  img.src = imageUrl;

  return { destroy, setEmotion, setListening, setThinking, startLip, stopLip, triggerBounce };
}