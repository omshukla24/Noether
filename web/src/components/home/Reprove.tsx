"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { GAP, formatChange, ghostRun, type Build } from "@/hopper/sim";
import { prefersReducedMotion } from "@/motion/env.js";
import { smoothstep } from "@/motion/math.js";
import type { DiffLine } from "@/lib/story";
import { loadHopper } from "@/scenes/load";
import { readPalette } from "@/scenes/palette";
import type { HopperScene, Hud } from "@/scenes/hopper/scene";
import { useHopperControls } from "@/scenes/hopper/useHopperControls";
import hero from "./Hero.module.css";
import styles from "./Reprove.module.css";

interface ReproveProps {
  diff: DiffLine[];
  file: string;
  line: number;
  invariant: string;
  greenOthers: number;
  suitePassed: number;
  kept: { coyote: number; terminal: number };
}

// the gap sits lower in the frame than in the hero, under the heading
const DIVE_SHIFT = 2.6;
const n2 = (v: number) => v.toFixed(2);
const signed = (v: number) => (v >= 0 ? "+" : "−") + Math.abs(v).toFixed(3);
const ROWS: { build: Build; name: string }[] = [
  { build: "base", name: "Base" },
  { build: "head", name: "Head" },
  { build: "fixed", name: "Fixed" },
];

const runs = { base: ghostRun("base"), head: ghostRun("head"), fixed: ghostRun("fixed") };
const reach = Math.max(...ROWS.map((r) => Math.abs(runs[r.build].jump?.margin ?? 0))) * 1.15;

// 06 Re-prove: the same recorded run on the fixed build, which clears the gap again. The fixed build is playable.
export function Reprove({ diff, file, line, invariant, greenOthers, suitePassed, kept }: ReproveProps) {
  const section = useRef<HTMLElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const game = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<HopperScene | null>(null);
  const [playing, setPlaying] = useState(false);
  const [paused, setPaused] = useState(false);
  const [reduced, setReduced] = useState(false);
  // taking the controls always restarts a paused clock
  const play = useCallback((on: boolean) => {
    setPlaying(on);
    if (on) setPaused(false);
  }, []);
  const pad = useHopperControls(game, sceneRef, play);

  useEffect(() => {
    sceneRef.current?.setPaused(paused);
  }, [paused]);
  const jf = runs.fixed.jump!;
  const jh = runs.head.jump!;

  useEffect(() => {
    const root = section.current;
    const cv = canvas.current;
    if (!root || !cv) return;
    const still = prefersReducedMotion();
    const phone = window.matchMedia("(max-width: 760px)").matches;
    setReduced(still);
    let disposed = false;
    let scene: HopperScene | null = null;
    let io: IntersectionObserver | null = null;
    let trigger: ScrollTrigger | null = null;
    const write = (key: string, text: string) => {
      const el = root.querySelector<HTMLElement>(`[data-hud="${key}"]`);
      if (el && el.textContent !== text) el.textContent = text;
    };
    const tag = (key: string) => root.querySelector<HTMLElement>(`[data-tag="${key}"]`)!;
    const onHud = (h: Hud) => {
      write("x", n2(h.player.x));
      write("p", n2(h.player.p));
      write("tries", `${h.player.tries.fixed} tries · ${h.player.cleared.fixed} cleared the gap`);
    };

    loadHopper().then(({ createHopperScene }) => {
      if (disposed) return;
      scene = createHopperScene(cv, {
        palette: readPalette(),
        reduced: still,
        ghosts: ["head", "fixed"],
        build: "fixed",
        diveShift: DIVE_SHIFT,
        labels: { base: tag("head"), head: tag("fixed"), you: tag("you"), gap: tag("gap"), baseMark: tag("headMark"), headMark: tag("fixedMark") },
        onHud,
      });
      sceneRef.current = scene;
      io = new IntersectionObserver(([entry]) => scene?.setActive(entry.isIntersecting), { threshold: 0.01 });
      io.observe(root);
      if (still) return;
      if (phone) {
        scene.setDive(1);
        return;
      }
      trigger = ScrollTrigger.create({
        trigger: root,
        start: "top top",
        end: "bottom bottom",
        onUpdate: ({ progress: p }) => {
          scene?.setDive(smoothstep(0.1, 0.55, p));
          root.style.setProperty("--note", String(smoothstep(0.45, 0.7, p)));
          if (p > 0.08) game.current?.blur();
        },
      });
    });

    return () => {
      disposed = true;
      trigger?.kill();
      io?.disconnect();
      scene?.dispose();
      sceneRef.current = null;
    };
  }, []);

  return (
    <section
      ref={section}
      id="reprove"
      data-route="reprove"
      data-label="06 Re-prove"
      data-theme="light"
      className={`${styles.runway} ${reduced ? styles.still : ""}`}
    >
      <div className={styles.stage}>
        <div
          ref={game}
          className={styles.game}
          tabIndex={0}
          role="application"
          aria-roledescription="playable level"
          aria-label="Hopper level, fixed build. D or right arrow runs, Space jumps, W and S move in depth, Escape stops."
          onPointerDown={() => game.current?.focus()}
        >
          <canvas ref={canvas} className={hero.canvas} aria-hidden="true" />
        </div>

        <div className={hero.tags} aria-hidden="true">
          <span data-tag="head" className={`${hero.tag} ${hero.tagHead}`}>HEAD</span>
          <span data-tag="fixed" className={`${hero.tag} ${hero.tagBase}`}>FIXED</span>
          <span data-tag="you" className={hero.tag}>YOU · FIXED</span>
          <span data-tag="gap" className={hero.measure}>gap {GAP.width.toFixed(2)}</span>
          <span data-tag="headMark" className={`${hero.measure} ${hero.mHead}`}>head {signed(jh.margin)}</span>
          <span data-tag="fixedMark" className={`${hero.measure} ${hero.mBase}`}>fixed {signed(jf.margin)}</span>
        </div>

        <div className={styles.copy}>
          <p className="label">06 · Re-prove</p>
          <h2 className={styles.title} data-split>Same run, fixed build.</h2>
          <p className={styles.deck}>
            The slipped line goes back. The recorded run now comes down {Math.abs(jf.margin).toFixed(2)} units past the lip
            of the far platform, and sideways momentum is {formatChange(jf.pChange)} again.
          </p>
          <div className={styles.controls}>
            <button type="button" className={hero.play} onClick={() => game.current?.focus()}>
              {playing ? "Playing: Escape to stop" : "Play the fixed build"}
            </button>
            <button
              type="button"
              className={hero.ghostBtn}
              onClick={() => {
                setPaused(false);
                sceneRef.current?.replay();
              }}
            >
              Replay the run
            </button>
            <button type="button" className={hero.ghostBtn} onClick={() => setPaused((p) => !p)}>
              {paused ? "Resume" : "Pause"}
            </button>
          </div>
          <p className={styles.keys} aria-hidden="true">
            <kbd>A</kbd><kbd>D</kbd> run · <kbd>W</kbd><kbd>S</kbd> depth · <kbd>Space</kbd> jump
          </p>
        </div>

        <div className={styles.proof}>
          <figure className={styles.diff}>
            <figcaption className={styles.cap}>
              <code>{file}</code>
              <span>line {line}</span>
            </figcaption>
            <pre tabIndex={0} aria-label="The fix, as a diff">
              <code>
                {diff
                  .filter((l) => l.kind !== "hunk")
                  .map((l, i) => (
                    <span key={i} className={`${styles.row} ${styles[l.kind]}`}>
                      <i aria-hidden="true">{l.newNo ?? l.oldNo}</i>
                      <b aria-hidden="true">{l.kind === "add" ? "+" : l.kind === "del" ? "−" : " "}</b>
                      {l.text || " "}
                    </span>
                  ))}
              </code>
            </pre>
          </figure>

          <div className={styles.ledger}>
            <p className="label">Proved on the fix branch</p>
            <ul>
              <li><code>{invariant}</code> passes again</li>
              <li><b className="tabular">{greenOthers}</b> other pinned checks that were green on head are still green</li>
              <li>
                The announced changes stay: <code>COYOTE_FRAMES</code> <b className="tabular">{kept.coyote}</b>,{" "}
                <code>TERMINAL_SPEED</code> <b className="tabular">{kept.terminal}</b>
              </li>
              <li>The repo&apos;s own suite is no worse than head&apos;s <b className="tabular">{suitePassed}</b> passed</li>
            </ul>
          </div>
        </div>

        <aside className={styles.margins} aria-label="Landing margin at the far platform's lip, from the recorded run">
          <p className="label">Margin at the lip</p>
          <ul>
            {ROWS.map(({ build, name }) => {
              const j = runs[build].jump!;
              const w = (Math.abs(j.margin) / reach) * 50;
              return (
                <li key={build} data-build={build} data-short={j.margin < 0 ? "" : undefined}>
                  <span className={styles.rowName}>{name}</span>
                  <span className={styles.track} aria-hidden="true">
                    <span className={styles.lip} />
                    <span
                      className={styles.fill}
                      style={{ width: `${w}%`, [j.margin < 0 ? "right" : "left"]: "50%" }}
                    />
                  </span>
                  <span className={`${styles.val} tabular`}>{signed(j.margin)}</span>
                  <span className={styles.pc}>p {formatChange(j.pChange)}</span>
                </li>
              );
            })}
          </ul>
        </aside>

        <p className={styles.you} aria-live="off">
          x <b data-hud="x" className="tabular">0.00</b> · p <b data-hud="p" className="tabular">0.00</b> ·{" "}
          <span data-hud="tries">0 tries · 0 cleared the gap</span>
        </p>

        <div className={`${hero.pad} ${styles.pad}`} aria-hidden="true">
          <button type="button" tabIndex={-1} {...pad("x", -1, () => play(true))}>Left</button>
          <button type="button" tabIndex={-1} {...pad("z", -1, () => play(true))}>Back</button>
          <button type="button" tabIndex={-1} {...pad("z", 1, () => play(true))}>Front</button>
          <button type="button" tabIndex={-1} {...pad("x", 1, () => play(true))}>Right</button>
          <button type="button" tabIndex={-1} className={hero.jump} {...pad("jump", 1, () => play(true))}>Jump</button>
        </div>
      </div>
    </section>
  );
}
