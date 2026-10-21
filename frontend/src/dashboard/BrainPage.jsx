import { useEffect, useRef, useState } from "react";
import gsap from "gsap";

import { api } from "../lib/api";
import { Icon, cx, reduceMotion } from "./ui";

const PROVIDERS = [
  {
    id: "ollama_cloud", kind: "brain", name: "Ollama Cloud",
    blurb: "Big open models (Kimi, Gemma, DeepSeek...). Default brain.",
    secret: "OLLAMA_API_KEY", link: "https://ollama.com/settings/keys",
    fields: [{ key: "OLLAMA_CLOUD_MODEL", label: "Model", picker: true }],
  },
  {
    id: "anthropic", kind: "brain", name: "Claude",
    blurb: "Anthropic's Claude.", secret: "ANTHROPIC_API_KEY", link: "https://console.anthropic.com/settings/keys",
    fields: [{ key: "ANTHROPIC_MODEL", label: "Model" }],
  },
  {
    id: "openai", kind: "brain", name: "OpenAI",
    blurb: "GPT models.", secret: "OPENAI_API_KEY", link: "https://platform.openai.com/api-keys",
    fields: [{ key: "OPENAI_MODEL", label: "Model" }],
  },
  {
    id: "elevenlabs", kind: "voice", name: "ElevenLabs",
    blurb: "Natural voice for Yashi. Without it she uses the browser voice.",
    secret: "ELEVENLABS_API_KEY", link: "https://elevenlabs.io/app/settings/api-keys",
    fields: [{ key: "ELEVENLABS_VOICE_ID", label: "Voice ID" }, { key: "ELEVENLABS_MODEL", label: "Voice model" }],
  },
];

const INPUT = "w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-[0.82rem] text-white outline-none transition placeholder:text-white/30 focus:border-[#ff5c7a]";

function ProviderCard({ provider, keys, current, models, onSaved, onUse }) {
  const secret = keys.secrets[provider.secret];
  const [draft, setDraft] = useState({});
  const [show, setShow] = useState(false);
  const [test, setTest] = useState(null);       // {ok, detail} | "testing"
  const [message, setMessage] = useState("");
  const active = provider.kind === "brain" ? current.llm_backend === provider.id : current.tts_backend === "elevenlabs";

  async function save(values) {
    setMessage("Saving...");
    try {
      const result = await api.put("/api/settings/keys", { values });
      onSaved(result);
      setDraft({});
      setMessage("Saved");
      runTest();
    } catch (error) {
      setMessage(error.message);
    }
  }

  async function runTest() {
    setTest("testing");
    try {
      setTest(await api.post(`/api/settings/test/${provider.id}`));
    } catch (error) {
      setTest({ ok: false, detail: error.message });
    }
  }

  const dirty = Object.values(draft).some((v) => v && v.trim());

  return (
    <div
      className={cx(
        "flex flex-col gap-3 rounded-xl border bg-[#151012]/90 p-4 transition",
        active ? "border-[#ff5c7a]/70 shadow-[0_0_0_1px_rgba(255,92,122,0.3),0_14px_40px_rgba(200,16,46,0.25)]" : "border-white/[0.07]"
      )}
      data-panel
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-baseline gap-2">
            <span className="text-[1.05rem] font-black text-white">{provider.name}</span>
          </div>
          <div className="mt-0.5 text-[0.72rem] text-white/50">{provider.blurb}</div>
        </div>
        {active ? (
          <span className="shrink-0 rounded-full bg-yashi-brand px-2.5 py-1 text-[0.62rem] font-black tracking-[0.14em] text-white">
            {provider.kind === "brain" ? "ACTIVE BRAIN" : "VOICE ON"}
          </span>
        ) : null}
      </div>

      <div>
        <div className="mb-1 flex items-center justify-between text-[0.64rem] font-extrabold uppercase tracking-[0.18em] text-white/50">
          <span>API key</span>
          <a className="normal-case tracking-normal text-[#ff8da1] hover:underline" href={provider.link} rel="noreferrer" target="_blank">Get a key ↗</a>
        </div>
        <div className="flex gap-2">
          <input
            autoComplete="off"
            className={INPUT}
            onChange={(event) => setDraft((d) => ({ ...d, [provider.secret]: event.target.value }))}
            placeholder={secret.set ? `Saved ${secret.masked} - paste to replace` : "Paste your key"}
            spellCheck={false}
            type={show ? "text" : "password"}
            value={draft[provider.secret] || ""}
          />
          <button className="shrink-0 rounded-lg border border-white/10 px-2.5 text-[0.7rem] font-bold text-white/60 hover:text-white"
            onClick={() => setShow((s) => !s)} type="button">{show ? "Hide" : "Show"}</button>
        </div>
      </div>

      {provider.fields.map((field) => (
        <label className="block" key={field.key}>
          <div className="mb-1 text-[0.64rem] font-extrabold uppercase tracking-[0.18em] text-white/50">{field.label}</div>
          {field.picker && models.length ? (
            <select
              className={INPUT}
              onChange={(event) => save({ [field.key]: event.target.value })}
              value={keys.values[field.key]}
            >
              {[...new Set([keys.values[field.key], ...models])].map((m) => (
                <option className="bg-[#151012]" key={m} value={m}>{m}</option>
              ))}
            </select>
          ) : (
            <input
              className={INPUT}
              onChange={(event) => setDraft((d) => ({ ...d, [field.key]: event.target.value }))}
              placeholder={keys.values[field.key]}
              spellCheck={false}
              value={draft[field.key] || ""}
            />
          )}
        </label>
      ))}

      <div className="mt-1 flex flex-wrap items-center gap-2">
        <button
          className="rounded-lg bg-yashi-brand px-4 py-2 text-[0.75rem] font-black tracking-wide text-white transition hover:bg-[#e01a3a] disabled:opacity-40"
          disabled={!dirty}
          onClick={() => save(Object.fromEntries(Object.entries(draft).filter(([, v]) => v && v.trim())))}
          type="button"
        >
          Save
        </button>
        <button className="rounded-lg border border-white/15 px-3 py-2 text-[0.75rem] font-bold text-white/80 transition hover:border-[#ff5c7a]"
          onClick={runTest} type="button">Test</button>
        {provider.kind === "brain" ? (
          <button
            className="rounded-lg border border-white/15 px-3 py-2 text-[0.75rem] font-bold text-white/80 transition hover:border-[#ff5c7a] disabled:opacity-40"
            disabled={active}
            onClick={() => onUse(provider.id)}
            type="button"
          >
            Use as brain
          </button>
        ) : null}
        {secret.set ? (
          <button className="ml-auto text-[0.7rem] font-bold text-white/40 hover:text-[#ff8da1]"
            onClick={() => window.confirm(`Remove the ${provider.name} key?`) && save({ [provider.secret]: "" })}
            type="button">Remove key</button>
        ) : null}
      </div>

      <div className="min-h-[18px] text-[0.72rem] font-semibold">
        {test === "testing" ? <span className="text-white/50">Testing...</span> : null}
        {test && test !== "testing" ? (
          <span className={test.ok ? "text-[#4fd18b]" : "text-[#ff8da1]"}>{test.ok ? "✓ Working" : "✕ Not working"} — {test.detail}</span>
        ) : null}
        {!test && message ? <span className="text-white/50">{message}</span> : null}
      </div>
    </div>
  );
}

export default function BrainPage() {
  const [keys, setKeys] = useState(null);
  const [current, setCurrent] = useState(null);
  const [models, setModels] = useState([]);
  const rootRef = useRef(null);

  const loadCurrent = () => api.get("/api/settings/current").then(setCurrent);

  useEffect(() => {
    api.get("/api/settings/keys").then(setKeys);
    loadCurrent();
    api.get("/api/settings/ollama-models").then((r) => setModels(r.models || []));
  }, []);

  useEffect(() => {
    if (!keys || !current || !rootRef.current || reduceMotion()) return;
    gsap.from(rootRef.current.querySelectorAll("[data-panel]"), {
      opacity: 0, y: 22, duration: 0.6, stagger: 0.07, ease: "power3.out", clearProps: "all",
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [Boolean(keys && current)]);

  if (!keys || !current) {
    return <div className="flex h-full items-center justify-center text-sm font-bold tracking-[0.2em] text-white/50">LOADING...</div>;
  }

  return (
    <div className="mx-auto max-w-[1100px] p-4" ref={rootRef}>
      <div className="mb-4 rounded-xl border border-white/[0.07] bg-[#151012]/90 p-4" data-panel>
        <div className="text-[0.78rem] font-black uppercase tracking-[0.16em] text-white">
          Brain & keys
        </div>
        <div className="mt-1 text-[0.75rem] leading-relaxed text-white/55">
          Keys are saved to <code className="text-[#ff8da1]">.env</code> on this PC and only ever shown masked. If the active
          brain fails, Yashi automatically tries the others you have keys for.
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <span className="text-[0.66rem] font-extrabold uppercase tracking-[0.18em] text-white/50">Voice</span>
          {[["elevenlabs", "ElevenLabs"], ["browser", "Browser"]].map(([id, label]) => (
            <button
              className={cx("rounded-md px-3 py-1.5 text-[0.74rem] font-extrabold transition",
                current.tts_backend === id ? "bg-yashi-brand text-white" : "bg-black/30 text-white/60 hover:text-white")}
              key={id}
              onClick={async () => { await api.post(`/api/settings/tts/${id}`); loadCurrent(); }}
              type="button"
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        {PROVIDERS.map((provider) => (
          <ProviderCard
            current={current}
            key={provider.id}
            keys={keys}
            models={models}
            onSaved={(next) => {
              setKeys(next);
              if (provider.id === "ollama_cloud") api.get("/api/settings/ollama-models").then((r) => setModels(r.models || []));
            }}
            onUse={async (id) => { await api.post(`/api/settings/llm/${id}`); loadCurrent(); }}
            provider={provider}
          />
        ))}
      </div>
    </div>
  );
}
