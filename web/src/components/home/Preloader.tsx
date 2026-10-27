"use client";

import { useEffect, useRef } from "react";
import { runPreloader } from "@/motion/preloader.js";
import { startScroll, stopScroll } from "@/motion/scroll.js";
import { loadHopper } from "@/scenes/load";
import styles from "./Preloader.module.css";

const LINES = 10;

// Counts real work (fonts, the three.js chunk with the Hopper game) and tells the
// page it may start with a "noether:ready" event. Capped at 4 s by runPreloader.
export function Preloader() {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    stopScroll();
    runPreloader(ref.current, { tasks: [loadHopper()] }).then(() => {
      startScroll();
      window.dispatchEvent(new Event("noether:ready"));
    });
  }, []);

  return (
    <div
      ref={ref}
      className={styles.loader}
      data-preloader
      data-words="CALIBRATING PLATES|ALIGNING LINES|MEASURING SYMMETRY"
      role="status"
      aria-label="Loading"
    >
      <div className={styles.inner} data-preload-inner>
        <div className={styles.lines} aria-hidden="true">
          {Array.from({ length: LINES }, (_, i) => (
            <span key={i} style={{ "--i": i, "--h": `${28 + ((i * 17) % 40)}px` } as React.CSSProperties} />
          ))}
        </div>
        <p className={styles.count}>
          <span data-preload-pct className="tabular">000</span>
        </p>
        <p className={styles.word} data-preload-word>CALIBRATING PLATES</p>
        <div className={styles.bar}>
          <span data-preload-bar />
        </div>
      </div>
    </div>
  );
}
