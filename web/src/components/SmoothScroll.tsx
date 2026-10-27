"use client";

import { useEffect } from "react";
import { initPress } from "@/motion/press.js";

// One Lenis instance for the whole site, ticking on the GSAP clock, and the press spring on every control.
export function SmoothScroll() {
  useEffect(() => {
    let cleanup: (() => void) | undefined;
    let cancelled = false;
    import("@/motion/scroll.js").then(({ initScroll }) => {
      if (!cancelled) cleanup = initScroll();
    });
    const stopPress = initPress();
    return () => {
      cancelled = true;
      cleanup?.();
      stopPress();
    };
  }, []);
  return null;
}
