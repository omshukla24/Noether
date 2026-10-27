"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { prefersReducedMotion } from "@/motion/env.js";
import { smoothstep } from "@/motion/math.js";
import { headLineState, sealProgress, tally, threadProgress, type CollapseLine, type DroppedLine } from "@/lib/collapse";
import type { SourceLine } from "@/lib/story";
import { Ruler } from "./Ruler";
import styles from "./Collapse.module.css";

interface CollapseProps {
  lines: CollapseLine[];
  dropped: DroppedLine[];
  source: SourceLine[];
  file: string;
  breakLine: number;
  why: string;
  baseSha: string;
  headSha: string;
  verdict: string;
}

const KIND_LABEL = { held: "conserved", intended: "announced change", silent: "silent break" } as const;
const SPECTRUM_STOPS = 5;
const hue = (pos: number) => `var(--spec-${1 + Math.min(SPECTRUM_STOPS - 1, Math.floor(pos * SPECTRUM_STOPS))})`;
const num = (i: number) => String(i + 1).padStart(2, "0");

// 04 Measure: The Collapse. Two plates, one line per pinned check. Scrolling lets the head lines
// drift onto their base twins; the silent one tears, and a thread whips to the source line that did it.
export function Collapse({ lines, dropped, source, file, breakLine, why, baseSha, headSha, verdict }: CollapseProps) {
  const runway = useRef<HTMLElement>(null);
  const stage = useRef<HTMLDivElement>(null);
  const headFace = useRef<HTMLDivElement>(null);
  const code = useRef<HTMLElement>(null);
  const thread = useRef<SVGPathElement>(null);
  const tip = useRef<SVGCircleElement>(null);
  const headEls = useRef<(HTMLButtonElement | null)[]>([]);
  const counts = useRef<Record<string, HTMLElement | null>>({});
  const silent = lines.findIndex((l) => l.kind === "silent");
  const [picked, setPicked] = useState<number | null>(null);
  const [ended, setEnded] = useState(false);
  const shown = picked ?? (ended && silent >= 0 ? silent : null);
  const line = shown === null ? null : lines[shown];

  // The thread runs from the bottom of the torn line to the left edge of the highlighted source row.
  const aim = useCallback(() => {
    const el = stage.current;
    const from = headEls.current[silent];
    const to = code.current?.querySelector<HTMLElement>("[data-hit]");
    if (!el || !from || !to || !thread.current || !tip.current) return;
    const s = el.getBoundingClientRect();
    const a = from.getBoundingClientRect();
    const b = to.getBoundingClientRect();
    if (!b.width) return;
    const x1 = a.left + a.width / 2 - s.left;
    const y1 = a.bottom - s.top - a.height * 0.1;
    const x2 = b.left - s.left;
    const y2 = b.top + b.height / 2 - s.top;
    thread.current.setAttribute("d", `M${x1} ${y1} C${x1 + 30} ${y1 + 110} ${x2 - 150} ${y2 + 130} ${x2} ${y2}`);
    tip.current.setAttribute("cx", String(x2));
    tip.current.setAttribute("cy", String(y2));
  }, [silent]);

  const render = useCallback(
    (p: number) => {
      const el = stage.current;
      const face = headFace.current;
      if (!el || !face) return;
      const w = face.clientWidth;
      const h = face.clientHeight;
      el.style.setProperty("--tilt", String(smoothstep(0, 0.12, p)));
      lines.forEach((l, i) => {
        const node = headEls.current[i];
        if (!node) return;
        const s = headLineState(l, p, lines.length);
        node.style.transform = `translate(${s.dx * w}px, ${s.dy * h}px)`;
        node.style.setProperty("--lock", String(s.lock));
        node.style.setProperty("--tear", String(s.tear));
      });
      if (p > 0.7) aim();
      const t = threadProgress(p);
      thread.current?.style.setProperty("stroke-dashoffset", String(1 - t));
      tip.current?.style.setProperty("opacity", String(t >= 1 ? 1 : 0));
      el.style.setProperty("--hit", String(t >= 1 ? 1 : 0));
      el.style.setProperty("--seal", String(sealProgress(p)));
      const { locked, torn } = tally(lines, p);
      if (counts.current.locked) counts.current.locked.textContent = String(locked);
      if (counts.current.torn) counts.current.torn.textContent = String(torn);
      setEnded(p > 0.88);
    },
    [lines, aim],
  );

  useEffect(() => {
    const root = runway.current;
    if (!root) return;
    const still = prefersReducedMotion() || window.matchMedia("(max-width: 900px)").matches;
    const onResize = () => render(still ? 1 : trigger?.progress ?? 0);
    let trigger: ScrollTrigger | null = null;
    if (still) {
      root.classList.add(styles.still);
      render(1);
    } else {
      render(0);
      trigger = ScrollTrigger.create({
        trigger: root,
        start: "top top",
        end: "bottom bottom",
        onUpdate: ({ progress }) => render(progress),
      });
    }
    const ro = new ResizeObserver(onResize);
    ro.observe(stage.current!);
    document.fonts?.ready.then(onResize);
    return () => {
      ro.disconnect();
      trigger?.kill();
    };
  }, [render]);

  const move = (from: number, step: number) => {
    const next = (from + step + lines.length) % lines.length;
    setPicked(next);
    headEls.current[next]?.focus();
  };
  const onKey = (e: React.KeyboardEvent, i: number) => {
    const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
    if (step) {
      e.preventDefault();
      move(i, step);
    } else if (e.key === "Home" || e.key === "End") {
      e.preventDefault();
      move(e.key === "Home" ? -1 : 0, e.key === "Home" ? 1 : -1);
    } else if (e.key === "Escape") setPicked(null);
  };

  return (
    <section ref={runway} id="measure" data-route="measure" data-label="04 Measure" data-theme="light" className={styles.runway}>
      <div ref={stage} className={styles.stage}>
        <div className={styles.left}>
          <header className={styles.intro}>
            <p className="label">04 · Measure</p>
            <h2 className={styles.title} data-split>The Collapse</h2>
            <p className={styles.deck}>
              One line for each check pinned on base. Where the head plate keeps a line in place, behaviour was conserved.
              Where it will not sit still, something moved.
            </p>
            <p className={styles.tally} aria-live="off">
              <span><b className="tabular" ref={(n) => { counts.current.locked = n; }}>0</b> / {lines.length} conserved</span>
              <span className={styles.tornCount}><b className="tabular" ref={(n) => { counts.current.torn = n; }}>0</b> torn</span>
            </p>
          </header>

          <div className={styles.plates}>
            <figure className={`${styles.plate} ${styles.basePlate}`}>
              <figcaption className={styles.cap}>
                <b>Base</b> <span>before · {baseSha}</span>
              </figcaption>
              <div className={styles.face}>
                {dropped.map((d) => (
                  <span
                    key={d.name}
                    className={styles.dropped}
                    style={{ left: `${d.pos * 100}%` }}
                    role="img"
                    aria-label={`${d.name}: ${d.reason}, never pinned`}
                    title={`${d.name}: ${d.reason}, never pinned`}
                  />
                ))}
                {lines.map((l, i) => (
                  <span
                    key={l.name}
                    className={styles.baseLine}
                    data-picked={shown === i ? "" : undefined}
                    style={{ left: `${l.pos * 100}%`, "--hue": hue(l.pos) } as React.CSSProperties}
                    onPointerEnter={() => setPicked(i)}
                  >
                    <i />
                    <em>{num(i)}</em>
                  </span>
                ))}
              </div>
              <Ruler steps={20} major={5} numerals className={styles.ruler} />
            </figure>

            <figure className={`${styles.plate} ${styles.headPlate}`}>
              <figcaption className={styles.cap}>
                <b>Head</b> <span>after · {headSha}</span>
              </figcaption>
              <div ref={headFace} className={styles.face} role="group" aria-label="Pinned checks on the head plate. Arrow keys pick a line.">
                {lines.map((l) => (
                  <span key={l.name} className={styles.twin} style={{ left: `${l.pos * 100}%` }} aria-hidden="true" />
                ))}
                {lines.map((l, i) => (
                  <button
                    key={l.name}
                    ref={(n) => { headEls.current[i] = n; }}
                    type="button"
                    className={styles.line}
                    data-kind={l.kind}
                    data-picked={shown === i ? "" : undefined}
                    aria-pressed={shown === i}
                    aria-label={`Line ${num(i)}, ${l.name}. ${KIND_LABEL[l.kind]}.`}
                    tabIndex={(picked ?? shown ?? 0) === i ? 0 : -1}
                    style={{ left: `${l.pos * 100}%`, "--hue": hue(l.pos) } as React.CSSProperties}
                    onPointerEnter={() => setPicked(i)}
                    onFocus={() => setPicked(i)}
                    onKeyDown={(e) => onKey(e, i)}
                  >
                    <i className={styles.hue} />
                    <i className={styles.lock} />
                    <i className={styles.torn} />
                    <em>{num(i)}</em>
                  </button>
                ))}
              </div>
              <Ruler steps={20} major={5} numerals className={styles.ruler} />
            </figure>
          </div>

          <p className={styles.legend}>
            <span className={styles.swatch} aria-hidden="true" />
            {dropped.length} faint lines never pinned: red on base
          </p>
        </div>

        <div className={styles.right}>
          <figure ref={code} className={styles.code}>
            <figcaption className={styles.cap}>
              <b>Head</b> <span>{file} · line {breakLine}</span>
            </figcaption>
            <pre tabIndex={0} aria-label={`${file} on head around line ${breakLine}`}>
              <code>
                {source.map((row) => (
                  <span key={row.no} className={styles.ln} data-hit={row.no === breakLine ? "" : undefined}>
                    <i aria-hidden="true">{row.no}</i>
                    {row.text || " "}
                  </span>
                ))}
              </code>
            </pre>
            <p className={styles.why}>{why}</p>
            <div className={styles.seal} aria-label={`Verdict: ${verdict}`}>
              <span>{verdict}</span>
              <small>{tally(lines, 1).torn} of {lines.length}</small>
            </div>
          </figure>

          <div className={styles.detail} aria-live="polite">
            {line ? (
              <>
                <p className="label">Line {num(line.index)} · {KIND_LABEL[line.kind]}</p>
                <p className={styles.claim}>{line.claim}</p>
                <p className={styles.results}>
                  <span>base <b className={styles.ok}>{line.base}</b></span>
                  <span aria-hidden="true">→</span>
                  <span>head <b className={line.head === "pass" ? styles.ok : styles.bad}>{line.head}</b></span>
                </p>
                <pre className={styles.check} tabIndex={0} aria-label="The pinned check"><code>{line.code}</code></pre>
              </>
            ) : (
              <p className={styles.hint}>Hover or focus a line, then use the arrow keys, to read the check it stands for.</p>
            )}
          </div>
        </div>

        <svg className={styles.threadSvg} aria-hidden="true">
          <path ref={thread} className={styles.thread} pathLength="1" strokeDasharray="1" strokeDashoffset="1" />
          <circle ref={tip} className={styles.tip} r="4.5" opacity="0" />
        </svg>

        <div className={styles.rows}>
          <h3 className={styles.rowsTitle}>Pinned lines</h3>
          <ol>
            {lines.map((l) => (
              <li key={l.name} data-kind={l.kind}>
                <span className={styles.rowNo}>{num(l.index)}</span>
                <code>{l.name}</code>
                <span className={styles.rowClaim}>{l.claim}</span>
                <span className={styles.results}>
                  base <b className={styles.ok}>{l.base}</b> · head <b className={l.head === "pass" ? styles.ok : styles.bad}>{l.head}</b>
                </span>
              </li>
            ))}
          </ol>
          <p className={styles.legend}>{dropped.length} more never pinned: red on base</p>
        </div>
      </div>
    </section>
  );
}
