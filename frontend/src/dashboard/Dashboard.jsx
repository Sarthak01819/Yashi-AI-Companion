import { useEffect, useLayoutEffect, useRef } from "react";
import gsap from "gsap";

import BrainPage from "./BrainPage";
import PersonaPage from "./PersonaPage";
import ProfilePage from "./ProfilePage";
import { Icon, cx, reduceMotion } from "./ui";

export const DASHBOARD_TABS = [
  { id: "profile", label: "My Profile", icon: "user" },
  { id: "yashi", label: "Yashi", icon: "heart" },
  { id: "brain", label: "Brain & Keys", icon: "key" },
];

export default function Dashboard({ tab = "profile" }) {
  const navRef = useRef(null);
  const underlineRef = useRef(null);
  const pageRef = useRef(null);
  const light = tab === "yashi";

  // Slide the underline to the active tab.
  useLayoutEffect(() => {
    const active = navRef.current?.querySelector(`[data-tab="${tab}"]`);
    if (!active || !underlineRef.current) return;
    const vars = { x: active.offsetLeft, width: active.offsetWidth };
    if (reduceMotion()) gsap.set(underlineRef.current, vars);
    else gsap.to(underlineRef.current, { ...vars, duration: 0.45, ease: "power3.out" });
  }, [tab]);

  // Page-to-page transition.
  useEffect(() => {
    if (!pageRef.current || reduceMotion()) return;
    gsap.fromTo(pageRef.current, { opacity: 0, y: 12 }, { opacity: 1, y: 0, duration: 0.4, ease: "power2.out", clearProps: "all" });
    pageRef.current.scrollTop = 0;
  }, [tab]);

  return (
    <div className={cx("flex h-screen flex-col", light ? "bg-[#fff7f8]" : "bg-[#0c0708]")}>
      <header
        className={cx(
          "relative z-20 flex items-center gap-3 border-b px-4 py-2.5",
          light ? "border-[#f0d2d7] bg-white/80 backdrop-blur" : "border-white/[0.07] bg-[#110b0d]"
        )}
      >
        <a
          className={cx(
            "flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-[0.74rem] font-extrabold transition",
            light ? "border-[#f0d2d7] text-[#6b4a51] hover:border-yashi-brand hover:text-yashi-brand"
                  : "border-white/10 text-white/70 hover:border-[#ff5c7a] hover:text-white"
          )}
          href="#/"
        >
          <Icon className="h-4 w-4" name="chat" /> Back to chat
        </a>

        <nav className="relative ml-2 flex items-center gap-1" ref={navRef}>
          {DASHBOARD_TABS.map((item) => (
            <a
              className={cx(
                "relative flex items-center gap-2 rounded-md px-3 py-2 text-[0.8rem] font-extrabold transition",
                tab === item.id
                  ? light ? "text-yashi-brand" : "text-white"
                  : light ? "text-[#6b4a51] hover:text-yashi-brand" : "text-white/50 hover:text-white"
              )}
              data-tab={item.id}
              href={`#/dashboard/${item.id}`}
              key={item.id}
            >
              <Icon className="h-4 w-4" name={item.icon} />
              <span className="hidden sm:inline">{item.label}</span>
            </a>
          ))}
          <span
            className="absolute -bottom-[11px] left-0 h-[3px] rounded-full bg-yashi-brand shadow-[0_0_12px_rgba(255,92,122,0.8)]"
            ref={underlineRef}
          />
        </nav>

        <div className={cx("ml-auto hidden text-[0.72rem] font-black tracking-[0.3em] md:block", light ? "text-yashi-brand" : "text-white/40")}>
          DASHBOARD
        </div>
      </header>

      <main className="min-h-0 flex-1 overflow-y-auto" ref={pageRef}>
        {tab === "yashi" ? <PersonaPage /> : tab === "brain" ? <BrainPage /> : <ProfilePage />}
      </main>
    </div>
  );
}
