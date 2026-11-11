import { useEffect, useRef, useState } from "react";

// Outfit picker on the stage. Built-in looks recolour her clothes; outfits listed
// in public/models/outfits.json swap in another VRM (see outfits.js).
export default function Wardrobe({ outfits, current, onChoose }) {
  const [open, setOpen] = useState(false);
  const boxRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    function onPointerDown(event) {
      if (!boxRef.current?.contains(event.target)) setOpen(false);
    }
    function onKey(event) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className="relative" ref={boxRef}>
      <button
        aria-expanded={open}
        aria-haspopup="true"
        className="rounded-md border border-white/25 bg-black/50 px-3 py-1.5 text-[0.72rem] font-extrabold tracking-wide text-white transition hover:border-white"
        onClick={() => setOpen(!open)}
        type="button"
      >
        Wardrobe
      </button>
      {open ? (
        <div
          className="absolute right-0 top-[calc(100%+8px)] z-20 w-60 border border-white/15 bg-black/85 p-2.5 shadow-[0_12px_32px_rgba(0,0,0,0.5)] backdrop-blur"
          role="menu"
        >
          <div className="px-0.5 pb-2 text-[0.6rem] font-bold uppercase tracking-[0.28em] text-white/45">Outfit</div>
          <div className="grid grid-cols-2 gap-1.5">
            {outfits.map((outfit) => {
              const active = outfit.id === current;
              return (
                <button
                  aria-checked={active}
                  className={[
                    "flex items-center gap-2 border px-2.5 py-1.5 text-left text-[0.72rem] font-extrabold text-white transition",
                    "[clip-path:polygon(5px_0,100%_0,calc(100%-5px)_100%,0_100%)]",
                    active
                      ? "border-[#ff5c7a] bg-yashi-brand/45"
                      : "border-white/15 bg-white/[0.06] hover:border-[#ff5c7a] hover:bg-yashi-brand/25",
                  ].join(" ")}
                  key={outfit.id}
                  onClick={() => onChoose(outfit.id)}
                  role="menuitemradio"
                  type="button"
                >
                  <span
                    className="h-3.5 w-3.5 shrink-0 rounded-full border border-white/40"
                    style={{ background: outfit.swatch }}
                  />
                  <span className="truncate">{outfit.label}</span>
                </button>
              );
            })}
          </div>
          <p className="px-0.5 pt-2.5 text-[0.62rem] font-semibold leading-snug text-white/50">
            New clothes: dress her in VRoid Studio, export a .vrm into models/ and list it in
            models/outfits.json.
          </p>
        </div>
      ) : null}
    </div>
  );
}
