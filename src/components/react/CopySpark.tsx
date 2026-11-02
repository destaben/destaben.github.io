import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import ClickSpark from "./ClickSpark";

interface Props {
  children?: ReactNode;
  className?: string;
}

const contents: CSSProperties = { display: "contents" };
const idle: CSSProperties = { width: "auto", height: "auto" };

// Original wrapper: sparks only while the slotted copy button is enabled, and never under reduced motion.
export default function CopySpark({ children, className }: Props) {
  const holder = useRef<HTMLDivElement>(null);
  const [disabled, setDisabled] = useState(true);

  useEffect(() => {
    const button = holder.current?.querySelector("button");
    const motion = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    const sync = () => setDisabled(Boolean(motion?.matches) || !button || button.disabled);
    sync();
    const observer = new MutationObserver(sync);
    if (button) observer.observe(button, { attributes: true, attributeFilter: ["disabled"] });
    motion?.addEventListener?.("change", sync);
    return () => {
      observer.disconnect();
      motion?.removeEventListener?.("change", sync);
    };
  }, []);

  return (
    <ClickSpark className={className} style={idle} disabled={disabled} sparkColor={["#d8f04b", "#ff7955"]} sparkCount={9} sparkRadius={28} duration={0.5} shape="line">
      <div ref={holder} style={contents}>{children}</div>
    </ClickSpark>
  );
}
