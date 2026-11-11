import { useRef } from "react";

// Drag handle between Yashi's stage and the chat (wide screens only).
//
// The split lives in a CSS variable on the shell (`--stage-w`). While dragging, the
// variable is written directly so the big App tree doesn't re-render on every pointer
// move; the final value is reported once, on release.
export const STAGE_MIN_PX = 300;
export const CHAT_MIN_PX = 420;              // the header's four buttons fit on one row

// Clamped in CSS too, so both sides keep a usable width when the window is resized.
export function stageWidthCss(percent) {
  return `clamp(${STAGE_MIN_PX}px, ${percent}%, calc(100% - ${CHAT_MIN_PX}px))`;
}

export default function Splitter({ shellRef, percent, defaultPercent, onChange }) {
  const drag = useRef(null);

  // Percent of the shell for a stage edge at `x` px from the shell's left, kept inside
  // the same limits the CSS uses so what is saved is what is shown.
  function toPercent(x) {
    const width = shellRef.current?.getBoundingClientRect().width || window.innerWidth;
    const px = Math.min(Math.max(x, STAGE_MIN_PX), Math.max(STAGE_MIN_PX, width - CHAT_MIN_PX));
    return Math.round((px / width) * 1000) / 10;
  }

  function show(value) {
    shellRef.current?.style.setProperty("--stage-w", stageWidthCss(value));
  }

  function finish() {
    if (!drag.current) return;
    const { value } = drag.current;
    drag.current = null;
    document.documentElement.style.cursor = "";
    document.body.style.userSelect = "";
    onChange(value);
  }

  function onPointerDown(event) {
    if (event.button !== 0) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    drag.current = { value: percent };
    document.documentElement.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }

  function onPointerMove(event) {
    if (!drag.current) return;
    const left = shellRef.current?.getBoundingClientRect().left || 0;
    drag.current.value = toPercent(event.clientX - left);
    show(drag.current.value);
  }

  function onKeyDown(event) {
    const width = shellRef.current?.getBoundingClientRect().width || window.innerWidth;
    const step = event.shiftKey ? 10 : 2;
    const at = (percent / 100) * width;
    const moves = {
      ArrowLeft: at - (step / 100) * width,
      ArrowRight: at + (step / 100) * width,
      Home: 0,
      End: width,
    };
    if (!(event.key in moves)) return;
    event.preventDefault();
    onChange(toPercent(moves[event.key]));
  }

  return (
    <div
      aria-label="Resize Yashi and the chat"
      aria-orientation="vertical"
      aria-valuemax={100}
      aria-valuemin={0}
      aria-valuenow={Math.round(percent)}
      className="group absolute inset-y-0 z-30 hidden w-4 -translate-x-1/2 cursor-col-resize touch-none outline-none min-[900px]:flex min-[900px]:items-center min-[900px]:justify-center left-[var(--stage-w)]"
      onDoubleClick={() => onChange(defaultPercent)}
      onKeyDown={onKeyDown}
      onLostPointerCapture={finish}
      onPointerCancel={finish}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={finish}
      role="separator"
      tabIndex={0}
      title="Drag to resize · double-click for half and half"
    >
      <span className="absolute inset-y-0 left-1/2 w-[2px] -translate-x-1/2 bg-transparent transition-colors group-hover:bg-yashi-brand/50 group-focus-visible:bg-yashi-brand/70 group-active:bg-yashi-brand" />
      <span className="relative h-14 w-[7px] rounded-full border border-black/25 bg-white shadow-[0_2px_8px_rgba(0,0,0,0.35)] transition-colors group-hover:border-yashi-brand group-hover:bg-yashi-brand group-focus-visible:border-yashi-brand group-focus-visible:bg-yashi-brand group-active:bg-yashi-brand" />
    </div>
  );
}
