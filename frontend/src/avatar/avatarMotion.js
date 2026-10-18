// Procedural "alive" motion for a VRM avatar.
//
// Everything is layered and frame-rate independent:
//   base pose -> breathing -> weight shift / sway -> mood posture
//   -> head & gaze (springs) -> blinks -> lip-sync -> expressions.
// Springs give a little overshoot and follow-through, which is what makes
// motion read as organic rather than mechanically interpolated.

const TAU = Math.PI * 2;

// Yashi's detected emotion -> VRM expression weights.
export const EMOTION_FACES = {
  joyful:     { happy: 1.0 },
  happy:      { happy: 0.7 },
  excited:    { happy: 0.6, surprised: 0.4 },
  content:    { relaxed: 0.5, happy: 0.15 },
  neutral:    { relaxed: 0.1 },
  concerned:  { sad: 0.4 },
  sad:        { sad: 0.75 },
  distressed: { sad: 1.0 },
};

// Head pitch (+ = down), tilt, and breathing speed per mood.
const MOOD_POSTURE = {
  joyful:     { pitch: -0.05, tilt: 0.05, breath: 1.15 },
  happy:      { pitch: -0.035, tilt: 0.04, breath: 1.05 },
  excited:    { pitch: -0.06, tilt: 0.02, breath: 1.3 },
  content:    { pitch: -0.01, tilt: 0.06, breath: 0.9 },
  neutral:    { pitch: 0, tilt: 0, breath: 1 },
  concerned:  { pitch: 0.04, tilt: -0.07, breath: 1.1 },
  sad:        { pitch: 0.11, tilt: -0.04, breath: 0.8 },
  distressed: { pitch: 0.14, tilt: -0.02, breath: 1.35 },
};

// Short interactive reactions (headpat, tease, cheer): face + head gesture.
const REACTIONS = {
  headpat: { face: { happy: 1.0 }, seconds: 2.4, pitch: 1.1, yaw: 0, tilt: 0.5 },
  tease:   { face: { angry: 0.55, sad: 0.1 }, seconds: 2.2, pitch: -0.3, yaw: 1.2, tilt: -0.6 },
  cheer:   { face: { happy: 0.9, surprised: 0.5 }, seconds: 2.0, pitch: -1.3, yaw: 0, tilt: 0.3 },
};

const EMOTION_KEYS = ["happy", "sad", "angry", "relaxed", "surprised"];
const VISEMES = ["aa", "ih", "ou", "ee", "oh"];
const VISEME_ODDS = [0.34, 0.16, 0.16, 0.14, 0.2];

const rand = (min, max) => min + Math.random() * (max - min);
const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
const damp = (current, target, lambda, dt) =>
  current + (target - current) * (1 - Math.exp(-lambda * dt));
const smoothstep = (x) => x * x * (3 - 2 * x);

function pickViseme() {
  let roll = Math.random();
  for (let i = 0; i < VISEMES.length; i += 1) {
    roll -= VISEME_ODDS[i];
    if (roll <= 0) return VISEMES[i];
  }
  return "aa";
}

// Smooth, non-repeating drift: sum of sines at incommensurate frequencies.
function drift(t, seed) {
  return (
    Math.sin(t * 0.31 + seed) * 0.5 +
    Math.sin(t * 0.67 + seed * 1.7) * 0.3 +
    Math.sin(t * 1.13 + seed * 2.3) * 0.2
  );
}

// Damped harmonic spring (semi-implicit Euler, sub-stepped for stability).
class Spring {
  constructor(frequency = 2, damping = 0.75, value = 0) {
    this.value = value;
    this.velocity = 0;
    this.target = value;
    this.omega = TAU * frequency;
    this.zeta = damping;
  }

  kick(impulse) {
    this.velocity += impulse;
  }

  update(dt) {
    const steps = Math.ceil(dt / (1 / 120));
    const h = dt / steps;
    for (let i = 0; i < steps; i += 1) {
      const force =
        -2 * this.zeta * this.omega * this.velocity -
        this.omega * this.omega * (this.value - this.target);
      this.velocity += force * h;
      this.value += this.velocity * h;
    }
    return this.value;
  }
}

export class AvatarMotion {
  /**
   * @param vrm   loaded VRM
   * @param flip  -1 for VRM 0.x rigs (turned around on load: X and Z axes invert)
   */
  constructor(vrm, flip = 1) {
    this.vrm = vrm;
    this.flip = flip;
    this.t = 0;

    // Posture springs.
    this.headPitch = new Spring(1.6, 0.7);
    this.headYaw = new Spring(1.3, 0.8);
    this.headTilt = new Spring(1.1, 0.75);
    this.lean = new Spring(0.8, 0.9);
    this.weight = new Spring(0.35, 0.85);
    this.nextWeightShift = rand(4, 9);

    // Gaze: a slow "attention" point plus fast saccades on top.
    this.gazeX = new Spring(0.9, 0.9);
    this.gazeY = new Spring(0.9, 0.9);
    this.saccadeX = new Spring(9, 0.85);
    this.saccadeY = new Spring(9, 0.85);
    this.nextSaccade = rand(0.6, 2);

    // Blinks.
    this.blinkAt = rand(1, 3);
    this.blinkQueue = [];
    this.blinkValue = 0;

    // Lip-sync.
    this.envelope = 0;
    this.prevLoudness = 0;
    this.viseme = "aa";
    this.syllable = { end: 0, gapEnd: 0, level: 0 };
    this.weights = {};

    this.breathPhase = 0;
    this.reaction = null;       // { face, until }
  }

  bone(name) {
    return this.vrm.humanoid.getNormalizedBoneNode(name);
  }

  // Rotations are authored in VRM 1.0 space; flip X/Z for VRM 0.x rigs.
  pose(name, x = 0, y = 0, z = 0) {
    const node = this.bone(name);
    if (node) node.rotation.set(x * this.flip, y, z * this.flip);
  }

  scheduleBlink(now, double = Math.random() < 0.15) {
    this.blinkQueue.push(now);
    if (double) this.blinkQueue.push(now + 0.24);
  }

  /**
   * @param dt      seconds since last frame
   * @param state   { emotion, thinking, listening, speaking, loudness (0..1|null),
   *                  bounce (set true to request a nod; consumed here),
   *                  reaction ("headpat" | "tease" | "cheer"; consumed here) }
   * @param pointer { x, y } in -1..1 screen space
   * @param lookTarget Object3D the eyes look at (child of the camera)
   */
  update(dt, state, pointer, lookTarget) {
    this.t += dt;
    const t = this.t;
    const mood = MOOD_POSTURE[state.emotion] || MOOD_POSTURE.neutral;

    // ── Breathing: quicker inhale, slower exhale ────────────────────────────
    this.breathPhase += dt * (TAU / 4.2) * mood.breath;
    const cycle = (this.breathPhase % TAU) / TAU;
    const breath = cycle < 0.4 ? smoothstep(cycle / 0.4) : 1 - smoothstep((cycle - 0.4) / 0.6);

    // ── Weight shift every few seconds; hips sway, spine counter-balances ──
    if (t >= this.nextWeightShift) {
      this.weight.target = rand(-1, 1);
      this.nextWeightShift = t + rand(5, 11);
    }
    const weight = this.weight.update(dt);
    const sway = drift(t, 1.3);

    // ── Lean: in while listening, slightly back while thinking ──────────────
    this.lean.target = state.listening ? 0.05 : state.thinking ? -0.02 : 0;
    const lean = this.lean.update(dt);

    this.pose("hips", 0, sway * 0.02, weight * 0.025 + sway * 0.006);
    this.pose("spine", lean * 0.5 - breath * 0.012, sway * -0.015, -weight * 0.02);
    this.pose("chest", lean * 0.5 - breath * 0.02, 0, -weight * 0.008);

    const shoulderLift = breath * 0.025 + (mood.pitch > 0.08 ? -0.03 : 0);
    this.pose("leftShoulder", 0, 0, shoulderLift);
    this.pose("rightShoulder", 0, 0, -shoulderLift);

    // Arms hang relaxed and swing very slightly with the sway.
    const armSwing = sway * 0.03 + weight * 0.02;
    this.pose("leftUpperArm", armSwing * 0.5, 0, -1.22 + breath * 0.02 + armSwing);
    this.pose("rightUpperArm", -armSwing * 0.5, 0, 1.22 - breath * 0.02 + armSwing);
    this.pose("leftLowerArm", 0, -0.08, -0.14);
    this.pose("rightLowerArm", 0, 0.08, 0.14);
    this.pose("leftHand", 0, 0, -0.08);
    this.pose("rightHand", 0, 0, 0.08);

    // ── Head: attention + mood + talking emphasis, all through springs ─────
    if (state.reaction && REACTIONS[state.reaction]) {
      const r = REACTIONS[state.reaction];
      this.reaction = { face: r.face, until: t + r.seconds };
      this.headPitch.kick(r.pitch);
      this.headYaw.kick(r.yaw);
      this.headTilt.kick(r.tilt);
      this.blinkQueue = [];
      state.reaction = null;
    }
    if (state.bounce) {                                         // nod when a reply lands
      this.headPitch.kick(1.4);
      state.bounce = false;
    }

    const thinking = state.thinking ? 1 : 0;
    this.headPitch.target =
      mood.pitch - thinking * 0.07 + drift(t, 4.1) * 0.025 + (state.listening ? 0.03 : 0);
    this.headYaw.target = pointer.x * 0.14 + drift(t, 7.7) * 0.06 + thinking * 0.08;
    this.headTilt.target =
      mood.tilt + thinking * 0.13 + (state.listening ? -0.09 : 0) + drift(t, 2.9) * 0.03;

    // ── Lip-sync: envelope follower + a new mouth shape per syllable ───────
    let loudness = 0;
    if (state.speaking) {
      if (typeof state.loudness === "number") {
        loudness = state.loudness;
      } else {
        // Browser speech gives us no audio, so synthesise a syllable rhythm.
        const s = this.syllable;
        if (t >= s.gapEnd) {
          const length = rand(0.09, 0.2);
          s.end = t + length;
          s.gapEnd = s.end + (Math.random() < 0.12 ? rand(0.25, 0.45) : rand(0.03, 0.08));
          s.level = rand(0.45, 0.95);
        }
        loudness = t < s.end ? s.level : 0;
      }
    }
    const attack = loudness > this.envelope ? 30 : 11;
    this.envelope = damp(this.envelope, loudness, attack, dt);
    // Syllable onset: pick a new vowel and add a little emphasis to the head.
    if (loudness > 0.3 && this.prevLoudness <= 0.3) {
      this.viseme = pickViseme();
      this.headPitch.kick(rand(0.15, 0.4));
      this.headYaw.kick(rand(-0.15, 0.15));
    }
    this.prevLoudness = loudness;

    const neck = 0.4;
    const headPitch = this.headPitch.update(dt);
    const headYaw = this.headYaw.update(dt);
    const headTilt = this.headTilt.update(dt);
    this.pose("neck", headPitch * neck, headYaw * neck, headTilt * neck);
    this.pose("head", headPitch * (1 - neck), headYaw * (1 - neck), headTilt * (1 - neck));

    // ── Gaze: drifts toward the pointer, quick saccades on top ─────────────
    this.gazeX.target = state.thinking ? -0.32 : pointer.x * 0.45;
    this.gazeY.target = state.thinking ? 0.3 : -pointer.y * 0.25 - mood.pitch * 0.8;
    if (t >= this.nextSaccade) {
      const reach = state.speaking ? 0.04 : 0.07;
      this.saccadeX.target = rand(-reach, reach);
      this.saccadeY.target = rand(-reach * 0.6, reach * 0.6);
      const jump = Math.hypot(
        this.saccadeX.target - this.saccadeX.value,
        this.saccadeY.target - this.saccadeY.value
      );
      // People often blink with a bigger eye movement.
      if (jump > 0.07 && Math.random() < 0.35 && !this.blinkQueue.length) this.scheduleBlink(t, false);
      this.nextSaccade = t + rand(0.5, state.thinking ? 1.2 : 2.6);
    }
    lookTarget.position.set(
      this.gazeX.update(dt) + this.saccadeX.update(dt),
      this.gazeY.update(dt) + this.saccadeY.update(dt),
      0
    );

    const face = this.vrm.expressionManager;
    if (!face) return;

    // Mouth shapes: main vowel follows the envelope, "aa" carries jaw opening.
    for (const name of VISEMES) {
      const target =
        name === this.viseme ? this.envelope * 0.85 : name === "aa" ? this.envelope * 0.3 : 0;
      this.weights[name] = damp(this.weights[name] || 0, target, 22, dt);
      face.setValue(name, this.weights[name]);
    }

    // ── Expressions ease in/out over ~0.4 s; softened while talking ────────
    const reacting = this.reaction && t < this.reaction.until;
    const goal = reacting
      ? this.reaction.face
      : state.thinking ? { relaxed: 0.2 } : EMOTION_FACES[state.emotion] || {};
    const soften = state.speaking ? 0.65 : 1;
    for (const name of EMOTION_KEYS) {
      this.weights[name] = damp(this.weights[name] || 0, (goal[name] || 0) * soften, reacting ? 9 : 5, dt);
      face.setValue(name, this.weights[name]);
    }

    // ── Blinks: fast close, brief hold, slower open; sometimes double ──────
    if (t >= this.blinkAt) {
      this.scheduleBlink(t);
      this.blinkAt = t + rand(2.2, 5.5);
    }
    let blink = 0;
    while (this.blinkQueue.length && t - this.blinkQueue[0] > 0.26) this.blinkQueue.shift();
    for (const start of this.blinkQueue) {
      const p = t - start;
      if (p < 0) continue;
      if (p < 0.07) blink = Math.max(blink, smoothstep(p / 0.07));
      else if (p < 0.1) blink = 1;
      else blink = Math.max(blink, 1 - smoothstep((p - 0.1) / 0.16));
    }
    // A big smile already closes the eyes; don't blink through it.
    const happyClosed = clamp((this.weights.happy || 0) * 1.4, 0, 1);
    this.blinkValue = blink * (1 - happyClosed);
    face.setValue("blink", this.blinkValue);
  }
}
