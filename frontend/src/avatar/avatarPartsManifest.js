export const avatarCanvasSize = {
  width: 736,
  height: 977,
};

export const avatarLayerOrder = [
  "hairBack",
  "skull",
  "neck",
  "upperBody",
  "leftHand",
  "rightHand",
  "hairFront",
  "leftEyebrow",
  "rightEyebrow",
  "leftEye",
  "rightEye",
  "nose",
  "lips",
];

export const avatarPartsManifest = {
  hairBack: {
    label: "Back Hair",
    source: "/avatar-parts/hair-back.png",
    anchor: { x: 368, y: 470 },
    size: { width: 736, height: 977 },
    notes: "Long hair behind the head and shoulders.",
  },
  skull: {
    label: "Head / Face Base",
    source: "/avatar-parts/skull-face-base.png",
    anchor: { x: 368, y: 292 },
    size: { width: 430, height: 470 },
    notes: "Face skin, cheeks, ears, and jawline without eyes, brows, nose, or mouth.",
  },
  neck: {
    label: "Neck",
    source: "/avatar-parts/neck.png",
    anchor: { x: 368, y: 560 },
    size: { width: 180, height: 150 },
    notes: "Neck only, separated from head and torso.",
  },
  upperBody: {
    label: "Upper Body",
    source: "/avatar-parts/upper-body.png",
    anchor: { x: 368, y: 760 },
    size: { width: 520, height: 380 },
    notes: "Torso, dress, shoulders, and chest area without hands.",
  },
  leftHand: {
    label: "Left Hand / Arm",
    source: "/avatar-parts/left-hand.png",
    anchor: { x: 180, y: 760 },
    size: { width: 180, height: 280 },
    notes: "Left arm or hand if visible.",
  },
  rightHand: {
    label: "Right Hand / Arm",
    source: "/avatar-parts/right-hand.png",
    anchor: { x: 556, y: 760 },
    size: { width: 180, height: 280 },
    notes: "Right arm or hand if visible.",
  },
  hairFront: {
    label: "Front Hair / Bangs",
    source: "/avatar-parts/hair-front.png",
    anchor: { x: 368, y: 314 },
    size: { width: 500, height: 580 },
    notes: "All front hair strands that should overlap the face.",
  },
  leftEyebrow: {
    label: "Left Eyebrow",
    source: "/avatar-parts/left-eyebrow.png",
    anchor: { x: 258, y: 202 },
    size: { width: 126, height: 42 },
    notes: "Transparent PNG, only the left brow.",
  },
  rightEyebrow: {
    label: "Right Eyebrow",
    source: "/avatar-parts/right-eyebrow.png",
    anchor: { x: 474, y: 182 },
    size: { width: 132, height: 42 },
    notes: "Transparent PNG, only the right brow.",
  },
  leftEye: {
    label: "Left Eye",
    source: "/avatar-parts/left-eye.png",
    anchor: { x: 268, y: 286 },
    size: { width: 126, height: 86 },
    notes: "Include lashes and iris. Keep the eyeball centered in the transparent area.",
  },
  rightEye: {
    label: "Right Eye",
    source: "/avatar-parts/right-eye.png",
    anchor: { x: 455, y: 263 },
    size: { width: 132, height: 84 },
    notes: "Include lashes and iris. Match left eye scale.",
  },
  nose: {
    label: "Nose",
    source: "/avatar-parts/nose.png",
    anchor: { x: 368, y: 430 },
    size: { width: 66, height: 94 },
    notes: "Transparent PNG with only the nose line/shading.",
  },
  lips: {
    label: "Lips / Mouth",
    source: "/avatar-parts/lips.png",
    anchor: { x: 355, y: 504 },
    size: { width: 74, height: 40 },
    notes: "Closed neutral mouth. Make a separate open-mouth sheet later if needed.",
  },
};

export const avatarRigNotes = [
  "Export each part against the same 736x977 artboard so alignment stays stable.",
  "Use transparent PNG files and do not crop too tightly around parts that need animation room.",
  "For eyes and lips, keep consistent padding so blinking and mouth-open transforms do not clip.",
  "Hair should usually be split into back hair and front hair so face parts can animate underneath.",
  "If you later add Live2D-style motion, anchor points above define the natural pivot or reference center.",
];
