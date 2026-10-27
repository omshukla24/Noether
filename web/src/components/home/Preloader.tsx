"use client";

import { useEffect, useRef } from "react";
import { runPreloader } from "@/motion/preloader.js";
import { loadHopper } from "@/scenes/load";
import styles from "./Preloader.module.css";

const LINES = 10;

// Counts real work (fonts, the three.js chunk with the Hopper game) in a status chip and a top rule.
// The copy underneath is server-rendered and readable from the first frame; this never covers it.
export function Preloader() {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    runPreloader(ref.current, { tasks: [loadHopper()] });
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
      <div className={styles.rule} aria-hidden="true">
        <span data-preload-bar />
      </div>
      <div className={styles.chip} data-preload-inner>
        <div className={styles.lines} aria-hidden="true">
          {Array.from({ length: LINES }, (_, i) => (
            <span key={i} style={{ "--i": i, "--h": `${8 + ((i * 17) % 16)}px` } as React.CSSProperties} />
          ))}
        </div>
        <p className={styles.count}>
          <span data-preload-pct className="tabular">000</span>
        </p>
        <p className={styles.word} data-preload-word>CALIBRATING PLATES</p>
      </div>
    </div>
  );
}
