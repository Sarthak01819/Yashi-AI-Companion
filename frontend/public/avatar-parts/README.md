Avatar parts go in this folder.

Recommended workflow:

1. Use the current avatar image as the master reference.
2. Repaint or cut each piece on the same `736 x 977` canvas.
3. Export each piece as a transparent PNG.
4. Save the files here using the names referenced in:
   `frontend/src/avatar/avatarPartsManifest.js`

Suggested files:

- `hair-back.png`
- `skull-face-base.png`
- `neck.png`
- `upper-body.png`
- `left-hand.png`
- `right-hand.png`
- `hair-front.png`
- `left-eyebrow.png`
- `right-eyebrow.png`
- `left-eye.png`
- `right-eye.png`
- `nose.png`
- `lips.png`

Important:

- Keep every part aligned to the same original artboard.
- Do not flatten the parts back together.
- Leave transparent padding around moving parts like eyes, brows, lips, and hands.
- If you make alternate expressions, create additional files like:
  `left-eye-closed.png`, `right-eye-closed.png`, `lips-open-a.png`, `lips-open-o.png`
