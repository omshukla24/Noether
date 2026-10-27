"use client";

import { useEffect, useRef } from "react";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { SLIT } from "@/motion/config.js";
import { prefersReducedMotion } from "@/motion/env.js";
import { smoothstep } from "@/motion/math.js";
import { Ruler } from "./Ruler";
import styles from "./Slit.module.css";

interface SlitProps {
  /** pinned invariants: one spectral line each */
  lines: number;
}

const SPECTRUM_STOPS = 5;
// The visible spectrum the ruler is graduated in.
const NM_FROM = 400;
const NM_STEP = 10;

// The way in: the page closes to a slit of light, which disperses into one line per pinned invariant.
export function Slit({ lines }: SlitProps) {
  const runway = useRef<HTMLElement>(null);
  const stage = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const root = runway.current;
    const el = stage.current;
    if (!root || !el) return;
    if (prefersReducedMotion()) {
      // a still frame from the middle of the dispersal, no runway
      root.classList.add(styles.still);
      el.style.setProperty("--close", "1");
      el.style.setProperty("--spread", "0.55");
      return;
    }
    let theme = "";
    const setTheme = (next: string) => {
      if (next === theme) return;
      theme = next;
      document.documentElement.dataset.theme = next;
    };
    const trigger = ScrollTrigger.create({
      trigger: root,
      start: "top top",
      end: "bottom bottom",
      onUpdate: ({ progress }) => {
        el.style.setProperty("--close", String(smoothstep(SLIT.close[0], SLIT.close[1], progress)));
        el.style.setProperty("--spread", String(smoothstep(SLIT.spread[0], SLIT.spread[1], progress)));
        setTheme(progress > 0.5 ? "dark" : "light");
      },
    });
    return () => trigger.kill();
  }, []);

  return (
    <section ref={runway} className={styles.runway} data-theme="dark" aria-hidden="true">
      <div ref={stage} className={styles.stage}>
        <div className={styles.dark}>
          <div className={styles.lines}>
            {Array.from({ length: lines }, (_, k) => (
              <span
                key={k}
                className={styles.line}
                style={{ "--x": (k + 0.5) / lines, "--hue": `var(--spec-${1 + Math.floor((k * SPECTRUM_STOPS) / lines)})` } as React.CSSProperties}
              />
            ))}
          </div>
          <Ruler
            className={styles.ruler}
            steps={30}
            major={5}
            numerals
            label={(i) => String(NM_FROM + i * NM_STEP)}
          />
          <p className={styles.caption}>
            <span>slit</span>
            <span>
              {lines} pinned lines · wavelength, nm
            </span>
          </p>
        </div>
        <div className={styles.page} />
      </div>
    </section>
  );
}
