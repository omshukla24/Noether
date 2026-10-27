"use client";

import { useEffect } from "react";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { prefersReducedMotion } from "@/motion/env.js";
import { initMarquees } from "@/motion/marquee.js";
import { initReveals } from "@/motion/reveal.js";

// Wires the markup-driven motion of the whole home page once, after every section has mounted:
// data-split / data-rise / data-count reveals, velocity marquees, and data-draw underlines.
// Place it last in the page so the triggers it creates come after the sections' own.
export function StoryMotion() {
  useEffect(() => {
    const root = document;
    const stop = [initReveals(root), initMarquees(root)];
    const reduced = prefersReducedMotion();
    const draws = [...root.querySelectorAll<HTMLElement>("[data-draw]")].map((el) => {
      if (reduced) {
        el.dataset.drawn = "";
        return null;
      }
      return ScrollTrigger.create({ trigger: el, start: "top 82%", once: true, onEnter: () => (el.dataset.drawn = "") });
    });
    ScrollTrigger.sort();
    ScrollTrigger.refresh();
    const refresh = () => ScrollTrigger.refresh();
    document.fonts?.ready.then(refresh);
    window.addEventListener("load", refresh);
    return () => {
      window.removeEventListener("load", refresh);
      draws.forEach((t) => t?.kill());
      stop.forEach((fn) => fn());
    };
  }, []);
  return null;
}
