import DecryptedText from "./DecryptedText";

// Monospace-safe, uppercase glyphs: every character has the same advance width, so the resolve step never shifts layout.
const scrambleGlyphs = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
const resolveMs = 800;

interface Props {
  text: string;
}

export default function SectionLabel({ text }: Props) {
  const letters = Array.from(text).filter((char) => !/\s/.test(char)).length;
  // One character resolves per tick, left to right, so the whole label resolves in about resolveMs.
  return (
    <DecryptedText
      text={text}
      animateOn="view"
      sequential
      revealDirection="start"
      characters={scrambleGlyphs}
      speed={Math.max(16, Math.round(resolveMs / Math.max(1, letters)))}
    />
  );
}
