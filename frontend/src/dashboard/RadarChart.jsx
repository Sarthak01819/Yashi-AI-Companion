import { useEffect, useRef, useState } from "react";
import gsap from "gsap";

import { reduceMotion } from "./ui";

const SIZE = 320;
const CENTER = SIZE / 2;
const RADIUS = 112;
const RINGS = 5;

function point(index, count, fraction) {
  const angle = -Math.PI / 2 + (index / count) * Math.PI * 2;
  return [CENTER + Math.cos(angle) * RADIUS * fraction, CENTER + Math.sin(angle) * RADIUS * fraction];
}

const polygon = (fractions) =>
  fractions.map((f, i) => point(i, fractions.length, f).join(",")).join(" ");

/** Animated pentagon stat chart (values 0..100). Morphs between updates. */
export default function RadarChart({ stats = {} }) {
  const labels = Object.keys(stats);
  const targets = labels.map((label) => Math.max(0.04, Math.min(1, (stats[label] || 0) / 100)));
  const [shown, setShown] = useState(() => targets.map(() => 0));
  const shownRef = useRef(shown);
  const key = targets.join("|");

  useEffect(() => {
    if (!labels.length) return undefined;
    if (reduceMotion()) {
      shownRef.current = targets;
      setShown(targets);
      return undefined;
    }
    const state = { t: 0 };
    const from = shownRef.current.length === targets.length ? shownRef.current : targets.map(() => 0);
    const tween = gsap.to(state, {
      t: 1,
      duration: 1.4,
      ease: "elastic.out(1, 0.75)",
      onUpdate: () => {
        const next = targets.map((target, i) => from[i] + (target - from[i]) * state.t);
        shownRef.current = next;
        setShown(next);
      },
    });
    return () => tween.kill();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  if (!labels.length) return null;
  const count = labels.length;

  return (
    <svg aria-label="Stats chart" className="h-auto w-full max-w-[360px]" role="img" viewBox={`0 0 ${SIZE} ${SIZE}`}>
      <defs>
        <radialGradient id="radar-fill" cx="50%" cy="50%" r="60%">
          <stop offset="0%" stopColor="#ff5c7a" stopOpacity="0.55" />
          <stop offset="100%" stopColor="#c8102e" stopOpacity="0.25" />
        </radialGradient>
        <filter id="radar-glow" x="-30%" y="-30%" width="160%" height="160%">
          <feGaussianBlur stdDeviation="4" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      {Array.from({ length: RINGS }, (_, ring) => (
        <polygon
          fill="none"
          key={ring}
          points={polygon(labels.map(() => (ring + 1) / RINGS))}
          stroke="#c8102e"
          strokeOpacity={ring === RINGS - 1 ? 0.55 : 0.18}
          strokeWidth="1"
        />
      ))}
      {labels.map((label, i) => {
        const [x, y] = point(i, count, 1);
        return <line key={label} stroke="#c8102e" strokeOpacity="0.22" x1={CENTER} x2={x} y1={CENTER} y2={y} />;
      })}

      <polygon
        fill="url(#radar-fill)"
        filter="url(#radar-glow)"
        points={polygon(shown)}
        stroke="#ff5c7a"
        strokeLinejoin="round"
        strokeWidth="2"
      />
      {shown.map((fraction, i) => {
        const [x, y] = point(i, count, fraction);
        return <circle className="radar-dot" cx={x} cy={y} fill="#fff" key={labels[i]} r="3.2" />;
      })}

      {labels.map((label, i) => {
        const [x, y] = point(i, count, 1.2);
        return (
          <g key={label}>
            <text
              className="fill-white/80 text-[11px] font-extrabold tracking-wider"
              dominantBaseline="middle"
              textAnchor="middle"
              x={x}
              y={y - 6}
            >
              {label}
            </text>
            <text
              className="fill-[#ff8da1] text-[10px] font-black"
              dominantBaseline="middle"
              textAnchor="middle"
              x={x}
              y={y + 8}
            >
              {Math.round(stats[label] || 0)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
