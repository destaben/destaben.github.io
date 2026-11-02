import { useEffect, useState } from "react";
import LetterGlitch from "./LetterGlitch";

const motionQuery = "(prefers-reduced-motion: reduce)";
const narrowQuery = "(max-width: 820px)";

// Decorative only. Nothing renders on the server, under reduced motion, or on narrow screens, so the static section stays intact there.
export default function GlitchBackdrop() {
  const [live, setLive] = useState(false);

  useEffect(() => {
    if (!window.matchMedia) return undefined;
    const motion = window.matchMedia(motionQuery);
    const narrow = window.matchMedia(narrowQuery);
    const update = () => setLive(!motion.matches && !narrow.matches);
    update();
    motion.addEventListener?.("change", update);
    narrow.addEventListener?.("change", update);
    return () => {
      motion.removeEventListener?.("change", update);
      narrow.removeEventListener?.("change", update);
    };
  }, []);

  if (!live) return null;

  return (
    <LetterGlitch
      glitchColors={["#d8f04b", "#4b6868", "#ff7955"]}
      baseColor="#173238"
      baseOpacity={0.5}
      characters="01#/<>[]{}+="
      fontSize={14}
      glitchAmount={0.5}
      speed={0.6}
      edgeFade={0.55}
      centerFade={0.25}
      clickEffect="none"
      interactive={false}
      backgroundColor="#0b1f23"
    />
  );
}
