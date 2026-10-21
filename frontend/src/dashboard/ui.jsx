import { useEffect, useRef, useState } from "react";
import gsap from "gsap";

export const reduceMotion = () =>
  typeof window !== "undefined" &&
  window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

export function cx(...values) {
  return values.filter(Boolean).join(" ");
}

/** Number that counts up to its value whenever it changes. */
export function CountUp({ value = 0, duration = 1.2, className = "" }) {
  const ref = useRef(null);
  const shown = useRef({ v: 0 });
  useEffect(() => {
    if (!ref.current) return undefined;
    if (reduceMotion()) {
      ref.current.textContent = Math.round(value).toLocaleString();
      return undefined;
    }
    const tween = gsap.to(shown.current, {
      v: value,
      duration,
      ease: "power2.out",
      onUpdate: () => {
        if (ref.current) ref.current.textContent = Math.round(shown.current.v).toLocaleString();
      },
    });
    return () => tween.kill();
  }, [value, duration]);
  return <span className={className} ref={ref}>0</span>;
}

/** Horizontal bar that fills to `percent` with a smooth tween. */
export function FillBar({ percent = 0, className = "", barClass = "", delay = 0 }) {
  const ref = useRef(null);
  useEffect(() => {
    if (!ref.current) return;
    const width = `${Math.max(0, Math.min(100, percent))}%`;
    if (reduceMotion()) {
      ref.current.style.width = width;
      return;
    }
    gsap.to(ref.current, { width, duration: 1, delay, ease: "power3.out" });
  }, [percent, delay]);
  return (
    <div className={cx("h-2 overflow-hidden rounded-full bg-white/10", className)}>
      <div className={cx("h-full w-0 rounded-full", barClass)} ref={ref} />
    </div>
  );
}

/** Range slider styled for the dashboard; shows its value live. */
export function Slider({ label, sub, value, min = 0, max = 100, onChange, onCommit, tone = "dark" }) {
  const percent = ((value - min) / (max - min)) * 100;
  const light = tone === "light";
  return (
    <label className="block">
      <div className="mb-1.5 flex items-baseline justify-between gap-2">
        <span className={cx("text-[0.8rem] font-extrabold", light ? "text-[#2b1a1d]" : "text-white")}>
          {label}
          {sub ? <span className="ml-2 text-[0.66rem] font-bold text-[#ff5c7a]">{sub}</span> : null}
        </span>
        <span className={cx("text-[0.78rem] font-black tabular-nums", light ? "text-yashi-brand" : "text-[#ff8da1]")}>
          {value}
        </span>
      </div>
      <input
        className="yashi-range w-full"
        max={max}
        min={min}
        onChange={(event) => onChange(Number(event.target.value))}
        onKeyUp={() => onCommit?.()}
        onPointerUp={() => onCommit?.()}
        style={{ "--fill": `${percent}%` }}
        type="range"
        value={value}
      />
    </label>
  );
}

/** Text input / textarea with label. */
export function Field({ label, value, onChange, placeholder, multiline = false, maxLength, tone = "dark", type = "text" }) {
  const light = tone === "light";
  const cls = cx(
    "w-full rounded-lg border px-3 py-2 text-[0.85rem] outline-none transition",
    light
      ? "border-[#f0d2d7] bg-white/80 text-[#2b1a1d] placeholder:text-[#b8a0a6] focus:border-yashi-brand"
      : "border-white/10 bg-black/30 text-white placeholder:text-white/30 focus:border-[#ff5c7a]"
  );
  return (
    <label className="block">
      <div className={cx("mb-1 text-[0.66rem] font-extrabold uppercase tracking-[0.18em]", light ? "text-[#6b4a51]" : "text-white/50")}>
        {label}
      </div>
      {multiline ? (
        <textarea
          className={cx(cls, "min-h-[88px] resize-y")}
          maxLength={maxLength}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          value={value}
        />
      ) : (
        <input
          className={cls}
          maxLength={maxLength}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          type={type}
          value={value}
        />
      )}
    </label>
  );
}

/** Editable list of short tags (interests, likes, goals). */
export function TagInput({ label, values = [], onChange, placeholder = "Add and press Enter", max = 12, tone = "dark" }) {
  const [draft, setDraft] = useState("");
  const light = tone === "light";
  function add() {
    const value = draft.trim();
    if (!value || values.includes(value) || values.length >= max) return;
    onChange([...values, value]);
    setDraft("");
  }
  return (
    <div>
      <div className={cx("mb-1 text-[0.66rem] font-extrabold uppercase tracking-[0.18em]", light ? "text-[#6b4a51]" : "text-white/50")}>
        {label}
      </div>
      <div
        className={cx(
          "flex flex-wrap gap-1.5 rounded-lg border p-2",
          light ? "border-[#f0d2d7] bg-white/80" : "border-white/10 bg-black/30"
        )}
      >
        {values.map((value) => (
          <button
            className={cx(
              "rounded-full px-2.5 py-1 text-[0.72rem] font-bold transition",
              light ? "bg-[#fde8eb] text-yashi-brand hover:bg-[#fbd5db]" : "bg-yashi-brand/25 text-[#ffb3c0] hover:bg-yashi-brand/40"
            )}
            key={value}
            onClick={() => onChange(values.filter((v) => v !== value))}
            title="Remove"
            type="button"
          >
            {value} ×
          </button>
        ))}
        <input
          className={cx(
            "min-w-[120px] flex-1 bg-transparent px-1 text-[0.8rem] outline-none",
            light ? "text-[#2b1a1d] placeholder:text-[#b8a0a6]" : "text-white placeholder:text-white/30"
          )}
          maxLength={40}
          onBlur={add}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              add();
            }
          }}
          placeholder={values.length >= max ? "Full" : placeholder}
          value={draft}
        />
      </div>
    </div>
  );
}

/** Segmented choice (e.g. reply length). */
export function Segmented({ options, value, onChange, tone = "dark" }) {
  const light = tone === "light";
  return (
    <div className={cx("inline-flex flex-wrap gap-1 rounded-lg p-1", light ? "bg-[#fde8eb]" : "bg-black/30")}>
      {options.map((option) => (
        <button
          className={cx(
            "rounded-md px-3 py-1.5 text-[0.74rem] font-extrabold transition",
            value === option.id
              ? "bg-yashi-brand text-white shadow-[0_4px_14px_rgba(200,16,46,0.35)]"
              : light
              ? "text-[#6b4a51] hover:text-yashi-brand"
              : "text-white/60 hover:text-white"
          )}
          key={option.id}
          onClick={() => onChange(option.id)}
          type="button"
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

/** Minimal line icons (stroke = currentColor). */
export function Icon({ name, className = "h-5 w-5" }) {
  const paths = {
    user: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm-7 8a7 7 0 0 1 14 0",
    heart: "M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10Z",
    spark: "M12 3v4m0 10v4M3 12h4m10 0h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6",
    sliders: "M4 6h10m4 0h2M4 12h4m4 0h8M4 18h12m4 0h0M14 4v4M8 10v4M16 16v4",
    mic: "M12 15a3 3 0 0 0 3-3V6a3 3 0 1 0-6 0v6a3 3 0 0 0 3 3Zm-6-3a6 6 0 0 0 12 0M12 18v3",
    note: "M5 4h10l4 4v12H5Z M15 4v4h4 M8 12h8M8 16h6",
    key: "M8 15a4 4 0 1 1 3.5-6L20 9v3h-2v2h-3l-1.5 1.5A4 4 0 0 1 8 15Zm-1-4h.01",
    chat: "M5 5h14v10H9l-4 4Z",
    flame: "M12 21a6 6 0 0 0 6-6c0-4-3-6-4-10-2 2-3 4-3 6-1-1-2-2-2-4-2 2-3 4-3 8a6 6 0 0 0 6 6Z",
    bolt: "M13 2 4 14h7l-1 8 9-12h-7l1-8Z",
    play: "M8 5v14l11-7Z",
    pause: "M8 5h3v14H8ZM13 5h3v14h-3Z",
    reset: "M4 12a8 8 0 1 0 2.3-5.7M4 4v4h4",
    camera: "M4 8h3l2-2h6l2 2h3v11H4Z M12 17a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z",
    check: "M5 12l4 4 10-10",
  };
  return (
    <svg aria-hidden="true" className={className} fill="none" stroke="currentColor" strokeLinecap="round"
      strokeLinejoin="round" strokeWidth="1.8" viewBox="0 0 24 24">
      <path d={paths[name] || paths.spark} />
    </svg>
  );
}
