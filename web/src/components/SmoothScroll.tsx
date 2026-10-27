"use client";

import { useEffect } from "react";

// One Lenis instance for the whole site, ticking on the GSAP clock.
export function SmoothScroll() {
  useEffect(() => {
    let cleanup: (() => void) | undefined;
    let cancelled = false;
    import("@/motion/scroll.js").then(({ initScroll }) => {
      if (!cancelled) cleanup = initScroll();
    });
    return () => {
      cancelled = true;
      cleanup?.();
    };
  }, []);
  return null;
}
