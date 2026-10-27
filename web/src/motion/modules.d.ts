// The motion modules are plain JS; these are their typed entry points.
declare module "@/motion/scroll.js" {
  export function initScroll(): () => void;
  export function scrollToTarget(target: number | Element, options?: Record<string, unknown>): void;
  export function stopScroll(): void;
  export function startScroll(): void;
  export const scrollVelocity: () => number;
}
declare module "@/motion/*";
