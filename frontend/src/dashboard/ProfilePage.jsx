import { useEffect, useRef, useState } from "react";
import gsap from "gsap";

import { api, imageToDataUrl } from "../lib/api";
import RadarChart from "./RadarChart";
import { CountUp, Field, FillBar, Icon, Slider, TagInput, cx, reduceMotion } from "./ui";

const ENERGY = [
  { key: "willpower", label: "Willpower", icon: "bolt", color: "text-[#ffb347]" },
  { key: "health", label: "Health", icon: "heart", color: "text-[#ff5c7a]" },
  { key: "mood", label: "Mood", icon: "spark", color: "text-[#ff8da1]" },
];

const PANEL = "rounded-xl border border-white/[0.07] bg-[#151012]/90 p-4 shadow-[0_10px_30px_rgba(0,0,0,0.35)]";

function PanelTitle({ icon, children }) {
  return (
    <div className="mb-3 flex items-center gap-2 text-[0.78rem] font-black uppercase tracking-[0.16em] text-white">
      {icon ? <Icon className="h-4 w-4 text-[#ff5c7a]" name={icon} /> : null}
      <span>{children}</span>
    </div>
  );
}

function Segments({ value }) {
  return (
    <div className="flex gap-[3px]">
      {Array.from({ length: 10 }, (_, i) => (
        <span
          className={cx("h-2.5 flex-1 rounded-[2px] transition-colors duration-500",
            i < value ? "bg-[linear-gradient(180deg,#ff5c7a,#c8102e)]" : "bg-white/10")}
          key={i}
          style={{ transitionDelay: `${i * 35}ms` }}
        />
      ))}
    </div>
  );
}

/** Holographic portrait card: tilts toward the cursor, light sweeps across. */
function PortraitCard({ profile, onAvatar }) {
  const cardRef = useRef(null);
  const shineRef = useRef(null);
  const fileRef = useRef(null);

  useEffect(() => {
    const card = cardRef.current;
    if (!card || reduceMotion()) return undefined;
    gsap.set(card, { transformPerspective: 800 });
    const rx = gsap.quickTo(card, "rotationX", { duration: 0.5 });
    const ry = gsap.quickTo(card, "rotationY", { duration: 0.5 });
    const sweep = gsap.fromTo(shineRef.current, { xPercent: -160 }, {
      xPercent: 160, duration: 1.6, ease: "power2.inOut", repeat: -1, repeatDelay: 3.2,
    });
    const move = (event) => {
      const box = card.getBoundingClientRect();
      ry(((event.clientX - box.left) / box.width - 0.5) * 16);
      rx(-((event.clientY - box.top) / box.height - 0.5) * 16);
    };
    const leave = () => { rx(0); ry(0); };
    card.addEventListener("pointermove", move);
    card.addEventListener("pointerleave", leave);
    return () => {
      sweep.kill();
      card.removeEventListener("pointermove", move);
      card.removeEventListener("pointerleave", leave);
    };
  }, []);

  const initials = (profile.display_name || "You").split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase();

  return (
    <button
      className="group relative block aspect-[4/5] w-full overflow-hidden rounded-xl border border-[#ff5c7a]/40 bg-black shadow-[0_0_0_1px_rgba(200,16,46,0.25),0_20px_50px_rgba(200,16,46,0.25)]"
      onClick={() => fileRef.current?.click()}
      ref={cardRef}
      title="Change your picture"
      type="button"
    >
      {profile.avatar ? (
        <img alt="" className="h-full w-full object-cover" src={profile.avatar} />
      ) : (
        <div className="flex h-full w-full items-center justify-center bg-[radial-gradient(circle_at_30%_20%,#ff5c7a_0%,#8e0e24_45%,#120406_100%)]">
          <span className="text-[4.5rem] font-black tracking-tight text-white/90">{initials}</span>
        </div>
      )}
      <span
        aria-hidden="true"
        className="pointer-events-none absolute inset-y-0 left-0 w-1/2 bg-[linear-gradient(105deg,transparent_20%,rgba(255,255,255,0.35)_50%,transparent_80%)] mix-blend-overlay"
        ref={shineRef}
      />
      <span className="pointer-events-none absolute inset-0 bg-[repeating-linear-gradient(0deg,rgba(255,255,255,0.03)_0px,rgba(255,255,255,0.03)_1px,transparent_1px,transparent_3px)]" />
      <span className="absolute bottom-2 right-2 flex items-center gap-1 rounded-full bg-black/60 px-2.5 py-1 text-[0.65rem] font-bold text-white opacity-0 transition group-hover:opacity-100">
        <Icon className="h-3.5 w-3.5" name="camera" /> Change
      </span>
      <input
        accept="image/*"
        className="hidden"
        onChange={async (event) => {
          const file = event.target.files?.[0];
          event.target.value = "";
          if (file) onAvatar(await imageToDataUrl(file));
        }}
        ref={fileRef}
        type="file"
      />
    </button>
  );
}

export default function ProfilePage() {
  const [profile, setProfile] = useState(null);
  const [stats, setStats] = useState(null);
  const [checkin, setCheckin] = useState({ willpower: 5, health: 5, mood: 5 });
  const [saveState, setSaveState] = useState("");
  const [levelUp, setLevelUp] = useState(false);
  const rootRef = useRef(null);
  const burstRef = useRef(null);
  const saveTimer = useRef(0);
  const profileRef = useRef(null);

  async function refreshStats() {
    const next = await api.get("/api/profile/stats");
    setStats(next);
    if (next.today) setCheckin({ willpower: next.today.willpower, health: next.today.health, mood: next.today.mood });
    try {
      const seen = Number(localStorage.getItem("yashi-level") || 0);
      if (seen && next.level > seen) setLevelUp(true);
      localStorage.setItem("yashi-level", String(next.level));
    } catch (error) { /* storage unavailable */ }
  }

  useEffect(() => {
    api.get("/api/profile").then((p) => { profileRef.current = p; setProfile(p); });
    refreshStats();
  }, []);

  // Panels cascade in once data has arrived.
  useEffect(() => {
    if (!profile || !stats || !rootRef.current || reduceMotion()) return;
    gsap.from(rootRef.current.querySelectorAll("[data-panel]"), {
      opacity: 0, y: 26, rotationX: -8, transformPerspective: 900, duration: 0.7,
      stagger: 0.06, ease: "power3.out", clearProps: "all",
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [Boolean(profile && stats)]);

  useEffect(() => {
    if (!levelUp || !burstRef.current || reduceMotion()) return;
    gsap.timeline({ onComplete: () => setLevelUp(false) })
      .fromTo(burstRef.current, { scale: 0.4, opacity: 0 }, { scale: 1, opacity: 1, duration: 0.5, ease: "back.out(2)" })
      .to(burstRef.current, { opacity: 0, y: -30, duration: 0.6, delay: 1.4 });
  }, [levelUp]);

  // Autosave profile edits (debounced).
  function update(patch) {
    const next = { ...profileRef.current, ...patch };
    profileRef.current = next;
    setProfile(next);
    clearTimeout(saveTimer.current);
    setSaveState("Saving...");
    saveTimer.current = window.setTimeout(async () => {
      try {
        await api.put("/api/profile", profileRef.current);
        setSaveState("Saved");
      } catch (error) {
        setSaveState(`Couldn't save: ${error.message}`);
      }
    }, 650);
  }

  async function saveCheckin(event) {
    const button = event.currentTarget;
    await api.post("/api/profile/checkin", checkin);
    if (!reduceMotion()) {
      for (let i = 0; i < 12; i += 1) {
        const spark = document.createElement("span");
        spark.className = "pointer-events-none fixed z-50 h-1.5 w-1.5 rounded-full bg-[#ff5c7a]";
        const box = button.getBoundingClientRect();
        spark.style.left = `${box.left + box.width / 2}px`;
        spark.style.top = `${box.top + box.height / 2}px`;
        document.body.appendChild(spark);
        const angle = (i / 12) * Math.PI * 2;
        gsap.to(spark, {
          x: Math.cos(angle) * 60, y: Math.sin(angle) * 60, opacity: 0, duration: 0.7,
          ease: "power2.out", onComplete: () => spark.remove(),
        });
      }
    }
    refreshStats();
  }

  if (!profile || !stats) {
    return <div className="flex h-full items-center justify-center text-sm font-bold tracking-[0.2em] text-white/50">LOADING PROFILE...</div>;
  }

  const levelSpan = Math.max(1, stats.next_level_xp - stats.level_floor);
  const levelProgress = ((stats.xp - stats.level_floor) / levelSpan) * 100;
  const radarTotal = Object.values(stats.radar).reduce((a, b) => a + b, 0);

  return (
    <div className="relative mx-auto grid max-w-[1320px] gap-4 p-4 lg:grid-cols-[280px_minmax(0,1fr)_300px]" ref={rootRef}>
      {/* ── Left ─────────────────────────────────────────────────────── */}
      <div className="flex flex-col gap-4">
        <div className="flex items-center justify-between rounded-xl border border-[#ff5c7a]/30 bg-[linear-gradient(90deg,rgba(200,16,46,0.35),rgba(200,16,46,0.08))] px-4 py-3" data-panel>
          <div className="flex items-center gap-2 text-white">
            <span className="text-[1rem] font-black text-[#ff8da1]">⌃⌃</span>
            <span className="text-[1.05rem] font-black tracking-[0.12em]">LEVEL <CountUp value={stats.level} /></span>
          </div>
          <span className="text-[0.66rem] font-bold uppercase tracking-[0.18em] text-white/70">{stats.title}</span>
        </div>

        <div data-panel>
          <PortraitCard onAvatar={(avatar) => update({ avatar })} profile={profile} />
          <div className="mt-3 text-center">
            <div className="text-[1.15rem] font-black text-white">{profile.display_name || "Your name"}</div>
            <div className="text-[0.72rem] font-bold text-white/50">
              {[profile.pronouns, profile.title].filter(Boolean).join(" · ") || "Set your name and title below"}
            </div>
          </div>
        </div>

        <div className={PANEL} data-panel>
          <PanelTitle icon="heart">Daily energy</PanelTitle>
          <div className="flex flex-col gap-3">
            {ENERGY.map((item) => (
              <div className="rounded-lg border border-white/[0.06] bg-black/30 px-3 py-2.5" key={item.key}>
                <div className="mb-2 flex items-center justify-between">
                  <span className="flex items-center gap-2 text-[0.82rem] font-extrabold text-white">
                    <Icon className={cx("h-4 w-4", item.color)} name={item.icon} />
                    {item.label}
                  </span>
                  <span className="text-[0.8rem] font-black tabular-nums text-[#ff8da1]">{checkin[item.key]}/10</span>
                </div>
                <Segments value={checkin[item.key]} />
                <input
                  aria-label={`${item.label} today`}
                  className="yashi-range mt-2 w-full"
                  max="10"
                  min="1"
                  onChange={(event) => setCheckin((c) => ({ ...c, [item.key]: Number(event.target.value) }))}
                  style={{ "--fill": `${(checkin[item.key] - 1) / 9 * 100}%` }}
                  type="range"
                  value={checkin[item.key]}
                />
              </div>
            ))}
            <button
              className="rounded-lg bg-yashi-brand py-2.5 text-[0.78rem] font-black tracking-[0.14em] text-white transition hover:bg-[#e01a3a] active:scale-[0.97]"
              onClick={saveCheckin}
              type="button"
            >
              {stats.today ? "UPDATE TODAY'S CHECK-IN" : "SAVE TODAY'S CHECK-IN  +20 XP"}
            </button>
          </div>
        </div>
      </div>

      {/* ── Center ───────────────────────────────────────────────────── */}
      <div className="flex min-w-0 flex-col gap-4">
        <div className={cx(PANEL, "flex flex-col items-center")} data-panel>
          <div className="self-start"><PanelTitle icon="spark">Bond stats</PanelTitle></div>
          <RadarChart stats={stats.radar} />
          <div className="mt-1 text-center text-[0.68rem] text-white/40">
            Grows from your real chats, check-ins and what you share with Yashi.
          </div>
        </div>

        <div className={cx(PANEL, "border-l-2 border-l-yashi-brand")} data-panel>
          <PanelTitle icon="flame">Your arc</PanelTitle>
          <textarea
            className="w-full resize-none bg-transparent text-[0.95rem] font-bold italic leading-relaxed text-white outline-none placeholder:text-white/25"
            maxLength={160}
            onChange={(event) => update({ motto: event.target.value })}
            placeholder={"Fear is just a feeling.\nTurn resistance into momentum."}
            rows={3}
            value={profile.motto}
          />
        </div>

        <div className={PANEL} data-panel>
          <div className="flex items-center justify-between">
            <PanelTitle icon="user">Who you are</PanelTitle>
            <span className="text-[0.68rem] font-bold text-white/40">{saveState}</span>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Name" maxLength={32} onChange={(v) => update({ display_name: v })} placeholder="What should Yashi call you?" value={profile.display_name} />
            <Field label="Pronouns" maxLength={20} onChange={(v) => update({ pronouns: v })} placeholder="he/him, she/her, they/them" value={profile.pronouns} />
            <Field label="Title" maxLength={40} onChange={(v) => update({ title: v })} placeholder="Night Owl, Code Wizard..." value={profile.title} />
            <Field label="Birthday (MM-DD)" maxLength={5} onChange={(v) => update({ birthday: v })} placeholder="05-27" value={profile.birthday} />
          </div>
          <div className="mt-3 grid gap-3">
            <Field label="About you" maxLength={400} multiline onChange={(v) => update({ about: v })} placeholder="A few lines Yashi should know about you." value={profile.about} />
            <TagInput label="Interests" onChange={(v) => update({ interests: v })} values={profile.interests} />
            <TagInput label="Goals" onChange={(v) => update({ goals: v })} placeholder="Add a goal and press Enter" values={profile.goals} />
          </div>
        </div>
      </div>

      {/* ── Right ────────────────────────────────────────────────────── */}
      <div className="flex flex-col gap-4">
        <div className={PANEL} data-panel>
          <div className="flex items-center gap-2 text-[0.78rem] font-black uppercase tracking-[0.16em] text-[#ffb347]">
            <Icon className="h-4 w-4" name="bolt" /> Current XP: <CountUp className="text-white" value={stats.xp} />
          </div>
          <div className="mt-1 text-[0.72rem] font-semibold italic text-[#ff8da1]">
            To reach Level {stats.level + 1}, earn {Math.max(0, stats.next_level_xp - stats.xp)} more XP
          </div>
          <FillBar barClass="bg-[linear-gradient(90deg,#c8102e,#ffb347)]" className="mt-3 h-2.5" percent={levelProgress} />
          <div className="mt-2 grid grid-cols-3 gap-2 text-center">
            {[["Messages", stats.messages], ["Facts", stats.facts], ["Check-ins", stats.checkins]].map(([label, value]) => (
              <div className="rounded-lg bg-black/30 py-2" key={label}>
                <div className="text-[1rem] font-black text-white"><CountUp value={value} /></div>
                <div className="text-[0.6rem] font-bold uppercase tracking-wider text-white/40">{label}</div>
              </div>
            ))}
          </div>
        </div>

        <div className={cx(PANEL, "flex items-center gap-4")} data-panel>
          <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-[radial-gradient(circle,#ff5c7a_0%,#c8102e_60%,#5a0716_100%)] shadow-[0_0_24px_rgba(255,92,122,0.55)]">
            <Icon className="h-7 w-7 animate-[yashi-pulse_1.8s_infinite] text-white" name="flame" />
          </div>
          <div>
            <div className="text-[0.66rem] font-black uppercase tracking-[0.18em] text-white/50">Daily streak</div>
            <div className="text-[1.6rem] font-black leading-none text-white">
              <CountUp value={stats.streak} /> <span className="text-[0.8rem] text-white/50">days</span>
            </div>
            <div className="text-[0.68rem] font-semibold text-[#ff8da1]">{stats.days_together} days together in total</div>
          </div>
        </div>

        <div className={PANEL} data-panel>
          <PanelTitle icon="sliders">Stats</PanelTitle>
          <div className="mb-1 flex justify-between text-[0.62rem] font-bold uppercase tracking-wider text-white/35">
            <span>Area</span><span>Points</span>
          </div>
          {Object.entries(stats.radar).map(([label, value], i) => (
            <div className="flex items-center gap-3 border-b border-white/[0.05] py-2 last:border-0" key={label}>
              <span className="w-[86px] text-[0.8rem] font-extrabold text-white">{label}</span>
              <span className="w-8 text-right text-[0.78rem] font-black tabular-nums text-[#ff8da1]">{value}</span>
              <FillBar barClass="bg-[linear-gradient(90deg,#c8102e,#ff5c7a)]" className="flex-1" delay={0.1 * i} percent={value} />
            </div>
          ))}
          <div className="mt-2 text-right text-[0.7rem] font-bold text-white/50">sum <CountUp className="text-white" value={radarTotal} /></div>
        </div>

        <div className={PANEL} data-panel>
          <PanelTitle icon="heart">Last check-ins</PanelTitle>
          {stats.checkin_history.length ? (
            <div className="flex h-24 items-end gap-1.5">
              {stats.checkin_history.slice(-7).map((day) => {
                const avg = (day.willpower + day.health + day.mood) / 3;
                return (
                  <div className="flex flex-1 flex-col items-center gap-1" key={day.date} title={`${day.date}: W${day.willpower} H${day.health} M${day.mood}`}>
                    <div className="w-full rounded-t bg-[linear-gradient(180deg,#ff5c7a,#8e0e24)] transition-all duration-700" style={{ height: `${avg * 8}px` }} />
                    <span className="text-[0.56rem] font-bold text-white/40">{day.date.slice(8)}</span>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="text-[0.75rem] text-white/40">Check in today to start your energy history.</div>
          )}
        </div>
      </div>

      {levelUp ? (
        <div className="pointer-events-none fixed inset-0 z-50 flex items-center justify-center">
          <div className="rounded-2xl border border-[#ffb347]/60 bg-black/80 px-10 py-6 text-center shadow-[0_0_60px_rgba(255,179,71,0.4)]" ref={burstRef}>
            <div className="text-[0.75rem] font-black tracking-[0.4em] text-[#ffb347]">LEVEL UP</div>
            <div className="text-[3rem] font-black text-white">{stats.level}</div>
            <div className="text-[0.8rem] font-bold text-[#ff8da1]">{stats.title}</div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
