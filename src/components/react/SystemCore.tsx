import { useEffect, useState, type CSSProperties } from "react";
import ASCIIText from "./ASCIIText";

const motionQuery = "(prefers-reduced-motion: reduce)";
const narrowQuery = "(max-width: 520px)";

// The static "DE" is what visitors see without JavaScript, under reduced motion, on narrow screens, and without WebGL 2.
const staticStyle: CSSProperties = {
  position: "absolute",
  inset: 0,
  display: "grid",
  placeItems: "center",
  color: "var(--ink)",
  fontFamily: '"SFMono-Regular", Consolas, monospace',
  fontSize: "7cqi",
  fontWeight: 800,
  lineHeight: 1,
};

const supportsWebGL2 = () => {
  const canvas = document.createElement("canvas");
  const gl = canvas.getContext("webgl2");
  if (!gl) return false;
  gl.getExtension("WEBGL_lose_context")?.loseContext();
  return true;
};

export default function SystemCore() {
  const [live, setLive] = useState(false);

  useEffect(() => {
    const motion = window.matchMedia(motionQuery);
    const narrow = window.matchMedia(narrowQuery);
    // The first render is always static, so server and client markup match before this effect runs.
    const update = () => setLive(!motion.matches && !narrow.matches && supportsWebGL2());
    update();
    motion.addEventListener("change", update);
    narrow.addEventListener("change", update);
    return () => {
      motion.removeEventListener("change", update);
      narrow.removeEventListener("change", update);
    };
  }, []);

  if (!live) return <div style={staticStyle}>DE</div>;

  return (
    <ASCIIText
      text="DE"
      asciiFontSize={6}
      textScale={1.1}
      fontWeight={800}
      textColor="#0b1f23"
      colors={["#0b1f23", "#173238", "#0b1f23"]}
      blocks={0}
      waves={1}
      tilt={1}
      hueShift={0}
      chroma={0}
      scramble={0.3}
      clickRipple={false}
      intro={false}
      idle
      interactive
    />
  );
}
