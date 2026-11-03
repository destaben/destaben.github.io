import { motion, MotionConfig } from "motion/react";
import type { ReactNode } from "react";

interface Props {
  children?: ReactNode;
  className?: string;
}

// Original wrapper: fades and lifts its content once when it scrolls into view. MotionConfig skips the movement for reduced-motion visitors.
export default function Reveal({ children, className }: Props) {
  return (
    <MotionConfig reducedMotion="user">
      <motion.div
        data-reveal=""
        className={className}
        initial={{ opacity: 0, y: 28 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, amount: 0.08 }}
        transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
      >
        {children}
      </motion.div>
    </MotionConfig>
  );
}
