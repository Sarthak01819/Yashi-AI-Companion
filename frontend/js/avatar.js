/**
 * Yashi Avatar Controller
 * Handles: blinking, breathing, emotion expressions, cursor eye-tracking, lip sync
 * Live2D-ready architecture — wraps a 2D SVG avatar fallback.
 */

const Avatar = (() => {
  const BLINK_MIN = 2000;
  const BLINK_MAX = 6000;
  const BREATHE_PERIOD = 4000;

  const EMOTION_COLORS = {
    neutral:    { fill: '#a8d8ea', glow: '#a8d8ea40' },
    happy:      { fill: '#ffd93d', glow: '#ffd93d50' },
    joyful:     { fill: '#ff6b9d', glow: '#ff6b9d50' },
    content:    { fill: '#c3f584', glow: '#c3f58440' },
    sad:        { fill: '#6c9bd1', glow: '#6c9bd160' },
    concerned:  { fill: '#f0a868', glow: '#f0a86840' },
    distressed: { fill: '#ff6b6b', glow: '#ff6b6b60' },
    excited:    { fill: '#ff9ff3', glow: '#ff9ff360' },
  };

  let currentEmotion = 'neutral';
  let lipSyncActive = false;
  let blinkTimer = null;
  let avatarEl = null;

  function init(containerId) {
    avatarEl = document.getElementById(containerId);
    if (!avatarEl) return;
    scheduleNextBlink();
    startBreathing();
    startEyeTracking();
    console.log('[Avatar] Initialized');
  }

  // ── Blinking ──────────────────────────────────────────────────────────────
  function scheduleNextBlink() {
    const delay = BLINK_MIN + Math.random() * (BLINK_MAX - BLINK_MIN);
    blinkTimer = setTimeout(() => {
      blink();
      scheduleNextBlink();
    }, delay);
  }

  function blink() {
    const eyelids = avatarEl?.querySelectorAll('.eyelid');
    if (!eyelids) return;
    eyelids.forEach(el => {
      el.style.transform = 'scaleY(1)';
      el.style.transition = 'transform 60ms ease-in';
      setTimeout(() => {
        el.style.transform = 'scaleY(0)';
        el.style.transition = 'transform 90ms ease-out';
      }, 60);
    });
  }

  // ── Breathing ─────────────────────────────────────────────────────────────
  function startBreathing() {
    const body = avatarEl?.querySelector('.avatar-body');
    if (!body) return;
    body.style.animation = `breathe ${BREATHE_PERIOD}ms ease-in-out infinite`;
  }

  // ── Eye Tracking ─────────────────────────────────────────────────────────
  function startEyeTracking() {
    document.addEventListener('mousemove', (e) => {
      const pupils = avatarEl?.querySelectorAll('.pupil');
      if (!pupils || !avatarEl) return;

      const rect = avatarEl.getBoundingClientRect();
      const cx = rect.left + rect.width / 2;
      const cy = rect.top + rect.height / 3;

      const dx = (e.clientX - cx) / window.innerWidth;
      const dy = (e.clientY - cy) / window.innerHeight;

      const maxShift = 4;
      const px = Math.max(-maxShift, Math.min(maxShift, dx * maxShift * 2));
      const py = Math.max(-maxShift, Math.min(maxShift, dy * maxShift * 2));

      pupils.forEach(p => {
        p.style.transform = `translate(${px}px, ${py}px)`;
        p.style.transition = 'transform 80ms ease-out';
      });
    });
  }

  // ── Emotion ───────────────────────────────────────────────────────────────
  function setEmotion(emotion) {
    if (emotion === currentEmotion) return;
    currentEmotion = emotion;

    const colors = EMOTION_COLORS[emotion] || EMOTION_COLORS.neutral;
    const face = avatarEl?.querySelector('.avatar-face');
    const glowEl = avatarEl?.querySelector('.avatar-glow');

    if (face) {
      face.style.transition = 'fill 600ms ease';
      face.style.fill = colors.fill;
    }
    if (glowEl) {
      glowEl.style.transition = 'box-shadow 600ms ease, background 600ms ease';
      glowEl.style.boxShadow = `0 0 60px 20px ${colors.glow}`;
    }

    // Update expression overlay
    const expr = avatarEl?.querySelector('.expression-overlay');
    if (expr) {
      expr.dataset.emotion = emotion;
    }

    // Dispatch event for Live2D integration hook
    window.dispatchEvent(new CustomEvent('yashi:emotion', { detail: { emotion } }));
  }

  // ── Lip Sync ──────────────────────────────────────────────────────────────
  function startLipSync() {
    lipSyncActive = true;
    const mouth = avatarEl?.querySelector('.mouth');
    if (!mouth) return;

    let frame = 0;
    const mouth_shapes = ['m-rest', 'm-open-sm', 'm-open-md', 'm-open-sm', 'm-rest'];

    function animateMouth() {
      if (!lipSyncActive) {
        mouth.dataset.shape = 'm-rest';
        return;
      }
      mouth.dataset.shape = mouth_shapes[frame % mouth_shapes.length];
      frame++;
      setTimeout(animateMouth, 80 + Math.random() * 60);
    }
    animateMouth();
  }

  function stopLipSync() {
    lipSyncActive = false;
    const mouth = avatarEl?.querySelector('.mouth');
    if (mouth) mouth.dataset.shape = 'm-rest';
  }

  // ── Live2D Hook (stub) ────────────────────────────────────────────────────
  // When you integrate Live2D SDK, replace with:
  // window.YASHI_LIVE2D = { setExpression, setMotion, setLipSync }
  function initLive2D(canvasId, modelPath) {
    console.info('[Avatar] Live2D hook ready. Attach SDK to', canvasId);
    // Live2D Cubism SDK integration point
  }

  return { init, setEmotion, startLipSync, stopLipSync, blink, initLive2D };
})();

window.YashiAvatar = Avatar;
