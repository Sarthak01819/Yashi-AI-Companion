// Yashi's wardrobe.
//
// Built-in looks recolour the clothes of the default model: VRoid bakes every
// garment into materials named "..._CLOTH", so a tint changes the whole outfit
// while skin, hair and eyes stay as they are.
//
// Whole new outfits are VRM files, e.g. made in VRoid Studio from the same
// avatar with different clothes. Put the .vrm in frontend/public/models/ and list
// it in frontend/public/models/outfits.json:
//   [{ "label": "School uniform", "file": "Yashi_school.vrm", "swatch": "#1f2a44" }]
import { useEffect, useState } from "react";

export const DEFAULT_MODEL = "/models/AvatarSample_A.vrm";

export const BUILT_IN_OUTFITS = [
  { id: "classic", label: "Classic", swatch: "#f3efe8", tint: null },
  { id: "crimson", label: "Crimson", swatch: "#c8102e", tint: "#d8344c" },
  { id: "midnight", label: "Midnight", swatch: "#2e3140", tint: "#454a5e" },
  { id: "sakura", label: "Sakura", swatch: "#f7b9c9", tint: "#ffc3d2" },
  { id: "lavender", label: "Lavender", swatch: "#bba8ea", tint: "#c8b8f2" },
  { id: "mint", label: "Mint", swatch: "#a3dcc6", tint: "#b8ecd8" },
  { id: "sky", label: "Sky", swatch: "#a9cdf2", tint: "#bfdcf8" },
];

const STORAGE_KEY = "yashi.outfit";

function readSaved() {
  try {
    return localStorage.getItem(STORAGE_KEY) || "classic";
  } catch {
    return "classic";
  }
}

// Entries from outfits.json; anything malformed is skipped.
function toOutfit(entry) {
  const file = typeof entry?.file === "string" ? entry.file.trim() : "";
  if (!/^[\w .()-]+\.vrm$/i.test(file)) return null;
  return {
    id: `vrm:${file}`,
    label: String(entry.label || file.replace(/\.vrm$/i, "")).slice(0, 24),
    swatch: /^#[0-9a-f]{3,8}$/i.test(entry.swatch || "") ? entry.swatch : "#8a8a8a",
    model: `/models/${encodeURIComponent(file)}`,
    tint: null,
  };
}

export function useWardrobe() {
  const [chosen, setChosen] = useState(readSaved);
  const [custom, setCustom] = useState([]);

  useEffect(() => {
    let cancelled = false;
    fetch("/models/outfits.json", { cache: "no-store" })
      .then((response) => (response.ok ? response.json() : []))
      .then((list) => {
        if (!cancelled && Array.isArray(list)) setCustom(list.map(toOutfit).filter(Boolean));
      })
      .catch(() => {});                  // no list (or the dev server's HTML fallback): built-ins only
    return () => { cancelled = true; };
  }, []);

  const outfits = [...BUILT_IN_OUTFITS, ...custom];
  const outfit = outfits.find((item) => item.id === chosen) || BUILT_IN_OUTFITS[0];

  function choose(id) {
    setChosen(id);
    try {
      localStorage.setItem(STORAGE_KEY, id);
    } catch {
      // private mode: the choice just isn't remembered
    }
  }

  return { outfits, outfit: { ...outfit, model: outfit.model || DEFAULT_MODEL }, choose };
}
