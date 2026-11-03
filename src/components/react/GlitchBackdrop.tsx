import { useEffect, useRef, useState } from "react";
import LetterGlitch from "./LetterGlitch";

const motionQuery = "(prefers-reduced-motion: reduce)";
const narrowQuery = "(max-width: 820px)";

// Decorative only. Nothing renders on the server, under reduced motion, or on narrow screens, so the static section stays intact there.
export default function GlitchBackdrop() {
  const [live, setLive] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const frame = useRef<HTMLDivElement>(null);

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

  // A GPU reset loses the WebGL context and leaves the canvas blank. Remount the backdrop (twice at most), then give up quietly.
  useEffect(() => {
    const node = frame.current;
    if (!node) return undefined;
    const onLost = (event: Event) => {
      event.preventDefault();
      setAttempt((count) => count + 1);
    };
    // webglcontextlost does not bubble, so listen during the capture phase.
    node.addEventListener("webglcontextlost", onLost, true);
    return () => node.removeEventListener("webglcontextlost", onLost, true);
  }, [live, attempt]);

  if (!live || attempt > 2) return null;

  return (
    <div ref={frame} key={attempt} style={{ width: "100%", height: "100%" }}>
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
    </div>
  );
}
