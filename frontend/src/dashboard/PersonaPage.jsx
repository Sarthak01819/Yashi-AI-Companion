import { Suspense, lazy, useEffect, useRef, useState } from "react";
import gsap from "gsap";

import { api } from "../lib/api";
import { Field, Icon, Segmented, Slider, TagInput, cx, reduceMotion } from "./ui";

const VrmAvatar = lazy(() => import("../avatar/VrmAvatar"));

const GLASS = "border border-white/60 bg-white/30 shadow-[0_20px_60px_rgba(142,14,36,0.18)] backdrop-blur-2xl";

const TRAITS = [
  { key: "warmth", label: "Warmth", reaction: "headpat" },
  { key: "playfulness", label: "Playfulness", reaction: "cheer" },
  { key: "sass", label: "Sass", reaction: "tease" },
  { key: "energy", label: "Energy", reaction: "cheer" },
  { key: "curiosity", label: "Curiosity", reaction: "headpat" },
];

const ROLE_LABELS = {
  friend: "Friend", best_friend: "Best friend", mentor: "Mentor", study_buddy: "Study buddy", hype_buddy: "Hype buddy",
};

const PRESET_TINTS = {
  sunny: "from-[#ffd1dc] to-[#fff2f4]",
  senpai: "from-[#f3d6db] to-[#ffffff]",
  tsundere: "from-[#ff9fb2] to-[#ffe3e8]",
  gremlin: "from-[#c8102e] to-[#ff7a92]",
  healer: "from-[#fde8eb] to-[#ffffff]",
};

const SECTIONS = [
  { id: "identity", icon: "user", label: "Identity" },
  { id: "traits", icon: "sliders", label: "Personality" },
  { id: "style", icon: "chat", label: "Talking style" },
  { id: "likes", icon: "heart", label: "Likes & story" },
  { id: "instructions", icon: "note", label: "Instructions" },
];

function Clock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);
  const time = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
  const day = now.toLocaleDateString([], { weekday: "long" });
  const date = now.toLocaleDateString([], { month: "2-digit", day: "2-digit" });
  return (
    <div>
      <div className="font-mono text-[3.4rem] font-black leading-none tracking-tight text-[#2b1a1d] [text-shadow:0_2px_0_rgba(255,255,255,0.6)]">
        {time}
      </div>
      <div className="mt-1 font-mono text-[0.8rem] font-bold text-[#6b4a51]">{day} {date}</div>
    </div>
  );
}

function Calendar({ activeDays = [] }) {
  const now = new Date();
  const year = now.getFullYear();
  const month = now.getMonth();
  const first = new Date(year, month, 1).getDay();
  const days = new Date(year, month + 1, 0).getDate();
  const active = new Set(activeDays.map((d) => Number(d.slice(8))));
  const cells = [...Array(first).fill(null), ...Array.from({ length: days }, (_, i) => i + 1)];
  return (
    <div className="rounded-2xl bg-[#2b1a1d] p-4 text-white shadow-[0_14px_40px_rgba(43,26,29,0.35)]">
      <div className="mb-2 border-b border-white/15 pb-2 text-center text-[1rem] font-black">
        {now.toLocaleDateString([], { month: "long" })}
      </div>
      <div className="grid grid-cols-7 gap-y-1 text-center text-[0.68rem]">
        {["S", "M", "T", "W", "T", "F", "S"].map((d, i) => (
          <span className="font-bold text-white/45" key={i}>{d}</span>
        ))}
        {cells.map((day, i) => (
          <span
            className={cx(
              "relative mx-auto flex h-6 w-6 items-center justify-center rounded-full font-bold",
              day === now.getDate() && "bg-white text-[#2b1a1d]",
              day && active.has(day) && day !== now.getDate() && "text-[#ff8da1]"
            )}
            key={i}
            title={day && active.has(day) ? "You talked with her this day" : undefined}
          >
            {day || ""}
            {day && active.has(day) ? <span className="absolute -bottom-0.5 h-1 w-1 rounded-full bg-[#ff5c7a]" /> : null}
          </span>
        ))}
      </div>
      <div className="mx-auto mt-3 h-1 w-10 rounded-full bg-white/30" />
    </div>
  );
}

function VoiceWidget({ name, avatarRef }) {
  const [state, setState] = useState("idle");     // idle | loading | playing
  const barsRef = useRef(null);
  useEffect(() => {
    if (state !== "playing" || !barsRef.current || reduceMotion()) return undefined;
    const tween = gsap.to(barsRef.current.children, {
      scaleY: () => 0.3 + Math.random() * 0.9, duration: 0.18, ease: "sine.inOut",
      repeat: -1, yoyo: true, repeatRefresh: true, stagger: 0.05,
    });
    return () => tween.kill();
  }, [state]);

  async function play() {
    if (state !== "idle") return;
    setState("loading");
    try {
      const result = await api.post("/api/persona/voice-preview");
      const done = () => { avatarRef.current?.stopLip(); setState("idle"); };
      if (result.audio_path) {
        const audio = new Audio(`/audio/tts/${result.audio_path}`);
        audio.onended = done;
        audio.onerror = done;
        avatarRef.current?.startLip(audio);
        setState("playing");
        await audio.play();
      } else {
        const utterance = new SpeechSynthesisUtterance(result.text);
        utterance.onend = done;
        utterance.onerror = done;
        avatarRef.current?.startLip();
        setState("playing");
        window.speechSynthesis.speak(utterance);
      }
    } catch (error) {
      setState("idle");
    }
  }

  return (
    <div className={cx(GLASS, "flex items-center gap-3 rounded-2xl p-3")}>
      <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-[#2b1a1d] text-white">
        <Icon className="h-5 w-5" name="mic" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="truncate text-[0.82rem] font-black text-[#2b1a1d]">{name}'s voice</div>
        <div className="mt-1 flex h-4 items-end gap-[3px]" ref={barsRef}>
          {Array.from({ length: 16 }, (_, i) => (
            <span className="h-full w-[3px] origin-bottom rounded-full bg-yashi-brand/70" key={i} style={{ transform: "scaleY(0.3)" }} />
          ))}
        </div>
      </div>
      <button
        className="flex h-10 w-10 items-center justify-center rounded-full bg-yashi-brand text-white shadow-[0_6px_18px_rgba(200,16,46,0.4)] transition hover:scale-105 active:scale-95"
        onClick={play}
        title="Hear her voice"
        type="button"
      >
        <Icon className="h-4 w-4" name={state === "playing" ? "pause" : "play"} />
      </button>
    </div>
  );
}

function SectionCard({ id, icon, title, children }) {
  return (
    <section className={cx(GLASS, "scroll-mt-24 rounded-3xl p-5")} data-reveal id={`persona-${id}`}>
      <div className="mb-4 flex items-center gap-2">
        <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-yashi-brand text-white"><Icon className="h-4 w-4" name={icon} /></span>
        <span className="text-[1rem] font-black text-[#2b1a1d]">{title}</span>
      </div>
      {children}
    </section>
  );
}

export default function PersonaPage() {
  const [persona, setPersona] = useState(null);
  const [options, setOptions] = useState(null);
  const [userName, setUserName] = useState("");
  const [activeDays, setActiveDays] = useState([]);
  const [prompt, setPrompt] = useState("");
  const [saveState, setSaveState] = useState("Saved");
  const personaRef = useRef(null);
  const saveTimer = useRef(0);
  const avatarRef = useRef(null);
  const rootRef = useRef(null);
  const blobsRef = useRef(null);

  const refreshPrompt = () => api.get("/api/persona/prompt").then((r) => setPrompt(r.prompt));

  useEffect(() => {
    Promise.all([api.get("/api/persona"), api.get("/api/persona/options"), api.get("/api/profile"), api.get("/api/profile/stats")])
      .then(([p, o, profile, stats]) => {
        personaRef.current = p;
        setPersona(p);
        setOptions(o);
        setUserName(profile.display_name || "there");
        setActiveDays(stats.active_days_this_month || []);
      });
    refreshPrompt();
  }, []);

  // Entrance + drifting bokeh behind the glass.
  useEffect(() => {
    if (!persona || !rootRef.current || reduceMotion()) return undefined;
    const ctx = gsap.context(() => {
      gsap.from("[data-hero]", { opacity: 0, scale: 0.96, filter: "blur(12px)", duration: 0.9, ease: "power3.out", clearProps: "all" });
      gsap.from("[data-widget]", { opacity: 0, y: 18, duration: 0.6, stagger: 0.07, delay: 0.25, ease: "power3.out", clearProps: "all" });
      gsap.utils.toArray(blobsRef.current.children).forEach((blob, i) => {
        gsap.to(blob, { x: `random(-80, 80)`, y: `random(-60, 60)`, duration: 9 + i * 2, repeat: -1, yoyo: true, ease: "sine.inOut" });
      });
    }, rootRef);
    return () => ctx.revert();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [Boolean(persona)]);

  function update(patch, reaction) {
    const next = { ...personaRef.current, ...patch };
    personaRef.current = next;
    setPersona(next);
    if (reaction) avatarRef.current?.react(reaction);
    clearTimeout(saveTimer.current);
    setSaveState("Saving...");
    saveTimer.current = window.setTimeout(async () => {
      try {
        const saved = await api.put("/api/persona", personaRef.current);
        personaRef.current = { ...saved };
        setSaveState("Saved");
        refreshPrompt();
      } catch (error) {
        setSaveState(`Couldn't save: ${error.message}`);
      }
    }, 600);
  }

  async function applyPreset(id) {
    const saved = await api.post(`/api/persona/preset/${id}`);
    personaRef.current = saved;
    setPersona(saved);
    avatarRef.current?.react(id === "tsundere" ? "tease" : id === "healer" || id === "senpai" ? "headpat" : "cheer");
    refreshPrompt();
  }

  async function resetAll() {
    const saved = await api.post("/api/persona/reset");
    personaRef.current = saved;
    setPersona(saved);
    refreshPrompt();
  }

  if (!persona || !options) {
    return <div className="flex h-full items-center justify-center text-sm font-bold tracking-[0.2em] text-[#8e1b2e]">LOADING...</div>;
  }

  const presetMatch = Object.entries(options.presets).find(([, preset]) =>
    Object.entries(preset.patch.traits).every(([k, v]) => persona.traits[k] === v))?.[0];

  return (
    <div className="relative min-h-full overflow-hidden bg-[linear-gradient(160deg,#fff7f8_0%,#fbe1e6_45%,#f4c3cd_100%)]" ref={rootRef}>
      <div aria-hidden="true" className="pointer-events-none absolute inset-0" ref={blobsRef}>
        <span className="absolute left-[8%] top-[10%] h-72 w-72 rounded-full bg-[#ff5c7a]/30 blur-3xl" />
        <span className="absolute right-[6%] top-[24%] h-80 w-80 rounded-full bg-[#c8102e]/20 blur-3xl" />
        <span className="absolute bottom-[8%] left-[38%] h-64 w-64 rounded-full bg-white/70 blur-3xl" />
      </div>

      <div className="relative mx-auto max-w-[1300px] px-4 pb-16 pt-4">
        {/* ── Hero: glass home screen ─────────────────────────────────── */}
        <div className="flex gap-3">
          <nav className={cx(GLASS, "sticky top-4 hidden h-fit flex-col gap-2 rounded-full p-2 md:flex")} data-widget>
            {SECTIONS.map((section) => (
              <a
                className="group relative flex h-11 w-11 items-center justify-center rounded-full bg-white/60 text-[#2b1a1d] transition hover:bg-yashi-brand hover:text-white"
                href={`#persona-${section.id}`}
                key={section.id}
                onClick={(event) => {
                  event.preventDefault();
                  document.getElementById(`persona-${section.id}`)?.scrollIntoView({ behavior: "smooth" });
                }}
                title={section.label}
              >
                <Icon className="h-5 w-5" name={section.icon} />
              </a>
            ))}
          </nav>

          <div className={cx(GLASS, "relative grid min-h-[560px] flex-1 gap-5 overflow-hidden rounded-[32px] p-6 lg:grid-cols-[250px_minmax(0,1fr)_290px]")} data-hero>
            <div className="flex flex-col gap-5">
              <div data-widget><Clock /></div>
              <div data-widget><Calendar activeDays={activeDays} /></div>
              <div className="text-[0.72rem] font-semibold leading-relaxed text-[#6b4a51]" data-widget>
                <span className="font-black text-yashi-brand">●</span> marks the days you talked with {persona.name}.
              </div>
            </div>

            <div className="relative min-h-[420px]">
              <div className="absolute inset-0">
                <Suspense fallback={null}>
                  <VrmAvatar ref={avatarRef} />
                </Suspense>
              </div>
              <div className="pointer-events-none absolute right-1 top-4 text-[1.1rem] font-black tracking-[0.3em] text-[#2b1a1d] [writing-mode:vertical-rl]">
                {persona.name}
              </div>
              <div className="pointer-events-none absolute bottom-2 left-0 right-0 text-center">
                <div className="inline-block rounded-full bg-white/70 px-4 py-1.5 text-[0.75rem] font-bold text-[#6b4a51] backdrop-blur">
                  {persona.tagline || "Edit her below - she reacts as you go"}
                </div>
              </div>
            </div>

            <div className="flex flex-col gap-4">
              <div className="flex items-center justify-between gap-2" data-widget>
                <span className="text-[1.5rem] font-black text-[#2b1a1d]">Hi {userName}!!</span>
                <span className="rounded-full bg-white/70 px-3 py-1.5 text-[0.75rem] font-black text-yashi-brand">{persona.name}</span>
              </div>
              <div className="text-[0.66rem] font-extrabold uppercase tracking-[0.2em] text-[#6b4a51]" data-widget>
                Personality presets
              </div>
              <div className="grid grid-cols-2 gap-3">
                {Object.entries(options.presets).map(([id, preset]) => (
                  <button
                    className={cx(
                      "group relative overflow-hidden rounded-2xl bg-gradient-to-br p-3 text-left shadow-[0_10px_24px_rgba(142,14,36,0.15)] transition hover:-translate-y-1 hover:shadow-[0_16px_30px_rgba(142,14,36,0.25)]",
                      PRESET_TINTS[id],
                      presetMatch === id && "ring-2 ring-yashi-brand ring-offset-2 ring-offset-white/40"
                    )}
                    data-widget
                    key={id}
                    onClick={() => applyPreset(id)}
                    type="button"
                  >
                    <div className={cx("text-[0.82rem] font-black", id === "gremlin" ? "text-white" : "text-[#2b1a1d]")}>{preset.label}</div>
                    <div className={cx("text-[0.66rem] font-bold", id === "gremlin" ? "text-white/80" : "text-yashi-brand")}>{preset.tag}</div>
                    <div className={cx("mt-1 text-[0.64rem] leading-snug", id === "gremlin" ? "text-white/85" : "text-[#6b4a51]")}>{preset.blurb}</div>
                  </button>
                ))}
              </div>
              <div className="mt-auto" data-widget>
                <VoiceWidget avatarRef={avatarRef} name={persona.name} />
              </div>
            </div>
          </div>
        </div>

        {/* bottom dock */}
        <div className="sticky bottom-3 z-10 mt-4 flex justify-center">
          <div className={cx(GLASS, "flex items-center gap-2 rounded-full px-3 py-2")}>
            <span className={cx("flex items-center gap-1.5 px-2 text-[0.75rem] font-bold", saveState === "Saved" ? "text-[#2e9e6b]" : "text-[#6b4a51]")}>
              {saveState === "Saved" ? <Icon className="h-4 w-4" name="check" /> : null}{saveState}
            </span>
            {SECTIONS.map((section) => (
              <button
                className="flex h-9 w-9 items-center justify-center rounded-full bg-white/70 text-[#2b1a1d] transition hover:bg-yashi-brand hover:text-white md:hidden"
                key={section.id}
                onClick={() => document.getElementById(`persona-${section.id}`)?.scrollIntoView({ behavior: "smooth" })}
                title={section.label}
                type="button"
              >
                <Icon className="h-4 w-4" name={section.icon} />
              </button>
            ))}
            <button
              className="flex items-center gap-1.5 rounded-full bg-white/70 px-3 py-2 text-[0.75rem] font-extrabold text-[#2b1a1d] transition hover:bg-[#2b1a1d] hover:text-white"
              onClick={resetAll}
              type="button"
            >
              <Icon className="h-4 w-4" name="reset" /> Reset
            </button>
          </div>
        </div>

        {/* ── Editors ─────────────────────────────────────────────────── */}
        <div className="mt-6 grid gap-5 lg:grid-cols-2">
          <SectionCard icon="user" id="identity" title="Identity">
            <Field label="Name" maxLength={24} onChange={(v) => update({ name: v })} tone="light" value={persona.name} />
            <div className="mt-3">
              <Field label="Tagline" maxLength={80} onChange={(v) => update({ tagline: v })} tone="light" value={persona.tagline} />
            </div>
            <div className="mt-3">
              <div className="mb-1 text-[0.66rem] font-extrabold uppercase tracking-[0.18em] text-[#6b4a51]">She is your...</div>
              <Segmented
                onChange={(role) => update({ role }, "cheer")}
                options={options.roles.map((id) => ({ id, label: ROLE_LABELS[id] || id }))}
                tone="light"
                value={persona.role}
              />
            </div>
          </SectionCard>

          <SectionCard icon="sliders" id="traits" title="Personality">
            <div className="flex flex-col gap-4">
              {TRAITS.map((trait) => (
                <Slider
                  key={trait.key}
                  label={trait.label}
                  onChange={(value) => update({ traits: { ...personaRef.current.traits, [trait.key]: value } })}
                  onCommit={() => avatarRef.current?.react(trait.reaction)}
                  tone="light"
                  value={persona.traits[trait.key]}
                />
              ))}
            </div>
          </SectionCard>

          <SectionCard icon="chat" id="style" title="Talking style">
            <div className="flex flex-col gap-4">
              <div>
                <div className="mb-1 text-[0.66rem] font-extrabold uppercase tracking-[0.18em] text-[#6b4a51]">Reply length</div>
                <Segmented onChange={(v) => update({ reply_length: v })} options={[
                  { id: "short", label: "Short" }, { id: "medium", label: "Medium" }, { id: "long", label: "Longer" },
                ]} tone="light" value={persona.reply_length} />
              </div>
              <div>
                <div className="mb-1 text-[0.66rem] font-extrabold uppercase tracking-[0.18em] text-[#6b4a51]">Asks questions</div>
                <Segmented onChange={(v) => update({ questions: v })} options={[
                  { id: "rarely", label: "Rarely" }, { id: "sometimes", label: "Sometimes" }, { id: "often", label: "Often" },
                ]} tone="light" value={persona.questions} />
              </div>
              <div>
                <div className="mb-1 text-[0.66rem] font-extrabold uppercase tracking-[0.18em] text-[#6b4a51]">Anime-style Japanese words (romaji)</div>
                <Segmented onChange={(v) => update({ japanese: v }, v === "off" ? null : "cheer")} options={[
                  { id: "off", label: "Off" }, { id: "light", label: "A little" }, { id: "more", label: "Lots" },
                ]} tone="light" value={persona.japanese} />
              </div>
            </div>
          </SectionCard>

          <SectionCard icon="heart" id="likes" title="Likes & story">
            <div className="flex flex-col gap-3">
              <TagInput label="Things she loves" onChange={(v) => update({ likes: v })} tone="light" values={persona.likes} />
              <Field label="Backstory" maxLength={600} multiline onChange={(v) => update({ backstory: v })}
                placeholder="Where she's from, what she does, little quirks..." tone="light" value={persona.backstory} />
            </div>
          </SectionCard>

          <div className="lg:col-span-2">
            <SectionCard icon="note" id="instructions" title="Custom instructions">
              <div className="grid gap-4 lg:grid-cols-2">
                <Field label="Anything else she should know or do" maxLength={1200} multiline
                  onChange={(v) => update({ custom_instructions: v })}
                  placeholder="e.g. Call me 'captain'. Remind me to drink water in the evening."
                  tone="light" value={persona.custom_instructions} />
                <div>
                  <div className="mb-1 text-[0.66rem] font-extrabold uppercase tracking-[0.18em] text-[#6b4a51]">What she receives (live)</div>
                  <pre className="max-h-[260px] overflow-auto whitespace-pre-wrap rounded-lg bg-[#2b1a1d] p-3 font-mono text-[0.7rem] leading-relaxed text-[#ffd9e0]">
                    {prompt}
                  </pre>
                </div>
              </div>
            </SectionCard>
          </div>
        </div>
      </div>
    </div>
  );
}
