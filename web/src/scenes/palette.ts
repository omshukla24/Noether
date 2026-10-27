import { cssVar } from "@/motion/env.js";
import type { Palette } from "./hopper/world";

/** Scene colours read from the design tokens, so WebGL never hardcodes a hex. */
export function readPalette(): Palette {
  return {
    ground: cssVar("--ground"),
    plate: cssVar("--plate"),
    ink: cssVar("--ink"),
    muted: cssVar("--muted"),
    faint: cssVar("--faint"),
    line: cssVar("--line"),
    hairline: cssVar("--hairline"),
    accent: cssVar("--accent"),
    broken: cssVar("--broken"),
    amber: cssVar("--spec-4"),
    mono: cssVar("--font-mono") || "monospace",
  };
}
