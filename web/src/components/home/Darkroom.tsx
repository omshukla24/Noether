"use client";

import { useEffect, useRef, useState } from "react";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { DARKROOM } from "@/motion/config.js";
import { prefersReducedMotion } from "@/motion/env.js";
import { smoothstep } from "@/motion/math.js";
import type { PlateData } from "@/lib/darkroom";
import styles from "./Darkroom.module.css";

interface DarkroomProps {
  plates: PlateData[];
  /** total sandbox seconds of the run */
  seconds: number;
}

const fmt = (v: number) => v.toFixed(1);

// 03 Expose: the sandbox snapshots as photographic plates in CSS 3D. Scroll fans the stack,
// a plate opens to show what ran inside it.
export function Darkroom({ plates, seconds }: DarkroomProps) {
  const runway = useRef<HTMLElement>(null);
  const stage = useRef<HTMLDivElement>(null);
  const counters = useRef<Record<string, HTMLElement | null>>({});
  const trayHead = useRef<HTMLHeadingElement>(null);
  const opener = useRef<HTMLElement | null>(null);
  const [open, setOpen] = useState<PlateData["key"] | null>(null);
  const longest = Math.max(...plates.map((p) => p.stageSeconds ?? 0), 1);
  const current = plates.find((p) => p.key === open) ?? null;

  useEffect(() => {
    const root = runway.current;
    const el = stage.current;
    if (!root || !el) return;
    const paint = (fan: number) => {
      el.style.setProperty("--fan", String(fan));
      if (counters.current.total) counters.current.total.textContent = fmt(seconds * fan);
      plates.forEach((p) => {
        const c = counters.current[p.key];
        if (c && p.stageSeconds !== null) c.textContent = fmt(p.stageSeconds * fan);
      });
    };
    if (prefersReducedMotion()) {
      root.classList.add(styles.still);
      paint(1);
      return;
    }
    paint(0);
    const trigger = ScrollTrigger.create({
      trigger: root,
      start: "top top",
      end: "bottom bottom",
      onUpdate: ({ progress }) => paint(smoothstep(DARKROOM.fan[0], DARKROOM.fan[1], progress)),
    });
    return () => trigger.kill();
  }, [plates, seconds]);

  useEffect(() => {
    if (open) trayHead.current?.focus({ preventScroll: true });
  }, [open]);

  const close = () => {
    setOpen(null);
    opener.current?.focus({ preventScroll: true });
  };

  return (
    <section
      ref={runway}
      id="expose"
      data-route="expose"
      data-label="03 Expose"
      data-theme="dark"
      className={styles.runway}
      onKeyDown={(e) => {
        if (e.key === "Escape" && open) close();
      }}
    >
      <div ref={stage} className={styles.stage} data-open={open ? "" : undefined}>
        <header className={styles.intro}>
          <p className="label">03 · Expose</p>
          <h2 className={styles.title} data-split>
            Every check ran in a sealed room.
          </h2>
          <p className={styles.deck}>
            Each stage ran inside a Nebius Sandbox and left a snapshot behind. A snapshot is a plate you can open: what ran
            in it, and what came out.
          </p>
          <p className={styles.total}>
            <b className="tabular" ref={(n) => { counters.current.total = n; }}>{fmt(seconds)}</b>
            <span>seconds of sandbox time</span>
          </p>
        </header>

        <div className={styles.scene}>
          <ol className={styles.rig} aria-label="Sandbox snapshots">
            {plates.map((p, i) => (
              <li key={p.key} className={`${styles.slot} ${styles[p.key]}`}>
                <button
                  type="button"
                  className={styles.plate}
                  aria-expanded={open === p.key}
                  aria-controls="tray"
                  onClick={(e) => {
                    opener.current = e.currentTarget;
                    if (open === p.key) close();
                    else setOpen(p.key);
                  }}
                >
                  <span className={styles.idx}>
                    plate {String(i + 1).padStart(2, "0")} · {p.key}
                  </span>
                  <span className={styles.plateTitle}>{p.title}</span>
                  <span className={styles.role}>{p.role}</span>
                  <span className={styles.id}>
                    <code>{p.short}</code>
                    <code className={styles.full}>{p.full}</code>
                  </span>
                  {p.stageSeconds !== null && (
                    <span className={styles.exposure}>
                      <span className={styles.bar}>
                        <span style={{ width: `${(p.stageSeconds / longest) * 100}%` }} />
                      </span>
                      <span className={`${styles.secs} tabular`}>
                        <b ref={(n) => { counters.current[p.key] = n; }}>{fmt(p.stageSeconds)}</b> s stage
                      </span>
                    </span>
                  )}
                  <span className={styles.openHint}>{open === p.key ? "Close" : "Open the plate"}</span>
                </button>
              </li>
            ))}
          </ol>
        </div>

        <aside id="tray" className={styles.tray} data-open={current ? "" : undefined} aria-label="What ran in the open plate" aria-live="polite">
          {current && (
            <>
              <button type="button" className={styles.closeBtn} onClick={close} aria-label="Close the plate (Escape)">
                Close · Esc
              </button>
              <p className="label">{current.key} · {current.short}</p>
              <h3 ref={trayHead} tabIndex={-1} className={styles.trayTitle}>{current.title}</h3>
              <p className={styles.trayRole}>{current.role}</p>
              <div className={styles.tableWrap} tabIndex={0} role="region" aria-label={`${current.title}: checks and results`}>
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th scope="col">check</th>
                      {current.columns.map((c) => (
                        <th key={c} scope="col">{c}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {current.rows.map((row) => (
                      <tr key={row.name}>
                        <th scope="row"><code>{row.name}</code></th>
                        {row.cells.map((cell, k) => (
                          <td key={k} className={styles[cell.tone]}>{cell.text}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {current.notes.map((n) => (
                <p key={n} className={styles.note}>{n}</p>
              ))}
            </>
          )}
        </aside>
      </div>
    </section>
  );
}
