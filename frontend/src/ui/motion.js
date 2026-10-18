// Small, purposeful UI motion (GSAP). Rules of thumb used here:
//  - motion explains a change (something arrived, mood shifted, mic hears you)
//  - short (<0.45 s), ease-out, small distances; nothing loops for decoration
//  - everything respects "prefers-reduced-motion"
import gsap from "gsap";

const reduceMotion = () =>
  typeof window !== "undefined" &&
  window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

gsap.defaults({ ease: "power3.out", duration: 0.4 });


/**
 * Returns a ref callback that animates an element in the first time it mounts.
 * Keyed by id so re-renders (streaming text) never replay the entrance.
 */
export function createEnterAnimator() {
  const seen = new Set();
  return (id, from = {}) => (element) => {
    if (!element || seen.has(id)) return;
    seen.add(id);
    if (reduceMotion()) return;
    gsap.from(element, { opacity: 0, y: 10, scale: 0.98, duration: 0.35, clearProps: "transform,opacity", ...from });
  };
}

export const messageEntrance = (role) =>
  role === "user"
    ? { x: 14, y: 4, transformOrigin: "100% 100%" }
    : role === "note"
    ? { y: 6, scale: 1 }
    : { x: -14, y: 4, transformOrigin: "0% 100%" };

/** Staggered first-paint entrance for a container's direct children. */
export function introStagger(container) {
  if (!container || reduceMotion()) return;
  gsap.from(container.children, {
    opacity: 0,
    y: 12,
    duration: 0.5,
    stagger: 0.045,
    clearProps: "transform,opacity",
  });
}


/** Little "settle" when a value badge changes (mood / mode). */
export function popBadge(element) {
  if (!element || element.dataset.popped || reduceMotion()) return;
  element.dataset.popped = "1";
  gsap.fromTo(element, { y: -5, opacity: 0 }, { y: 0, opacity: 1, duration: 0.3, clearProps: "transform,opacity" });
}


/** Mic level ring: returns a setter (0..100) that follows the voice smoothly. */
export function createLevelRing(element) {
  if (!element) return () => {};
  const scale = gsap.quickTo(element, "scale", { duration: 0.12, ease: "power2.out" });
  const opacity = gsap.quickTo(element, "opacity", { duration: 0.2 });
  return (percent) => {
    const level = Math.min(1, Math.max(0, percent / 100));
    scale(1 + level * 0.35);
    opacity(level > 0.02 ? 0.25 + level * 0.55 : 0);
  };
}


/** Tactile press on buttons that trigger an action. */
export function pressFeedback(element) {
  if (!element || reduceMotion()) return;
  gsap.fromTo(element, { scale: 0.92 }, { scale: 1, duration: 0.35, ease: "back.out(3)", clearProps: "scale" });
}

/** Little hearts float up from a point (headpat). Pure text glyphs, no emoji. */
export function floatHearts(container, x, y, count = 5) {
  if (!container || reduceMotion()) return;
  for (let i = 0; i < count; i += 1) {
    const heart = document.createElement("span");
    heart.textContent = "♡";
    heart.setAttribute("aria-hidden", "true");
    heart.className = "pointer-events-none absolute select-none font-bold text-[#ff5c7a]";
    heart.style.left = `${x}px`;
    heart.style.top = `${y}px`;
    heart.style.fontSize = `${14 + Math.random() * 12}px`;
    container.appendChild(heart);
    gsap.fromTo(
      heart,
      { opacity: 0, scale: 0.4, x: 0, y: 0 },
      {
        opacity: 1,
        scale: 1,
        x: (Math.random() - 0.5) * 90,
        y: -70 - Math.random() * 70,
        duration: 1.1 + Math.random() * 0.5,
        delay: i * 0.06,
        ease: "power2.out",
        onComplete: () => heart.remove(),
      }
    );
    gsap.to(heart, { opacity: 0, duration: 0.5, delay: 0.75 + i * 0.06 });
  }
}

/** Slide the settings sheet in from the right. */
export function slideSheet(element) {
  if (!element || element.dataset.slid || reduceMotion()) return;
  element.dataset.slid = "1";   // ref callbacks can fire more than once
  gsap.fromTo(
    element,
    { xPercent: 104 },
    { xPercent: 0, duration: 0.45, ease: "power3.out", clearProps: "transform" }
  );
}

/** Animate the mood meter fill to 0..100 %. */
export function setMeter(element, percent) {
  if (!element) return;
  const width = `${Math.max(4, Math.min(100, percent))}%`;
  if (reduceMotion()) {
    element.style.width = width;
    return;
  }
  gsap.to(element, { width, duration: 0.9, ease: "power2.inOut", overwrite: "auto" });
}
