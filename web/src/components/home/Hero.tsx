"use client";

import { useEffect, useRef, useState } from "react";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { GAP, formatChange, ghostRun, type Build, type Input } from "@/hopper/sim";
import { prefersReducedMotion } from "@/motion/env.js";
import { smoothstep } from "@/motion/math.js";
import { playHeroIntro } from "@/motion/reveal.js";
import { loadHopper } from "@/scenes/load";
import { readPalette } from "@/scenes/palette";
import type { HopperScene, Hud } from "@/scenes/hopper/scene";
import styles from "./Hero.module.css";

gsap.registerPlugin(ScrollTrigger);

interface HeroProps {
  ownSuitePassed: number;
}

const KEYS: Record<string, [keyof Input, number]> = {
  ArrowLeft: ["x", -1],
  KeyA: ["x", -1],
  ArrowRight: ["x", 1],
  KeyD: ["x", 1],
  ArrowUp: ["z", -1],
  KeyW: ["z", -1],
  ArrowDown: ["z", 1],
  KeyS: ["z", 1],
  Space: ["jump", 1],
};

const BUILD_NAME: Record<Build, string> = { base: "Base", head: "Head", fixed: "Fixed" };
const n2 = (v: number) => v.toFixed(2);
const n3 = (v: number) => (v >= 0 ? "+" : "−") + Math.abs(v).toFixed(3);

const base = ghostRun("base");
const head = ghostRun("head");

export function Hero({ ownSuitePassed }: HeroProps) {
  const section = useRef<HTMLElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const game = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<HopperScene | null>(null);
  const hud = useRef<Record<string, HTMLElement | null>>({});
  const tags = useRef<Record<string, HTMLElement | null>>({});
  const [build, setBuild] = useState<Build>("head");
  const [playing, setPlaying] = useState(false);
  const [reduced, setReduced] = useState(false);
  const [toast, setToast] = useState("");

  const bindHud = (key: string) => (el: HTMLElement | null) => {
    hud.current[key] = el;
  };
  const bindTag = (key: string) => (el: HTMLElement | null) => {
    tags.current[key] = el;
  };

  useEffect(() => {
    const root = section.current;
    const cv = canvas.current;
    if (!root || !cv) return;
    const still = prefersReducedMotion();
    setReduced(still);
    let disposed = false;
    let scene: HopperScene | null = null;
    let io: IntersectionObserver | null = null;
    let trigger: ScrollTrigger | null = null;
    const toastTimer = { id: 0 };

    const write = (key: string, text: string) => {
      const el = hud.current[key];
      if (el && el.textContent !== text) el.textContent = text;
    };
    const onHud = (h: Hud) => {
      write("frame", String(h.frame).padStart(3, "0"));
      write("baseX", n2(h.base.x));
      write("baseP", n2(h.base.p));
      write("headX", n2(h.head.x));
      write("headP", n2(h.head.p));
      write("youX", n2(h.player.x));
      write("youP", n2(h.player.p));
      write("youJump", h.player.jumpChange === null ? "no jump yet" : formatChange(h.player.jumpChange));
      write("youTries", `${h.player.tries[h.player.build]} tries · ${h.player.cleared[h.player.build]} cleared the gap`);
    };
    const onEvent = (event: string, b: Build) => {
      const text =
        event === "fell"
          ? b === "head"
            ? "Fell short. On head the air eats your speed."
            : "Fell. Base can clear it, try a longer run-up."
          : event === "cleared"
            ? `Cleared the ${GAP.width.toFixed(2)} gap on ${BUILD_NAME[b].toLowerCase()}.`
            : "Through the slit.";
      setToast(text);
      window.clearTimeout(toastTimer.id);
      toastTimer.id = window.setTimeout(() => setToast(""), 2400);
    };

    loadHopper().then(({ createHopperScene }) => {
      if (disposed) return;
      const t = tags.current;
      scene = createHopperScene(cv, {
        palette: readPalette(),
        reduced: still,
        labels: { base: t.base!, head: t.head!, you: t.you!, gap: t.gap!, baseMark: t.baseMark!, headMark: t.headMark! },
        onHud,
        onEvent,
      });
      sceneRef.current = scene;
      io = new IntersectionObserver(([entry]) => scene?.setActive(entry.isIntersecting), { threshold: 0.01 });
      io.observe(root);
      if (still) return;
      trigger = ScrollTrigger.create({
        trigger: root,
        start: "top top",
        end: "bottom bottom",
        onUpdate: (self) => {
          const p = self.progress;
          scene?.setDive(smoothstep(0.1, 0.55, p));
          root.style.setProperty("--lift", String(smoothstep(0.02, 0.3, p)));
          root.style.setProperty("--note", String(smoothstep(0.58, 0.78, p)));
          if (p > 0.08) game.current?.blur();
        },
      });
    });

    const intro = () => playHeroIntro(root);
    window.addEventListener("noether:ready", intro, { once: true });

    return () => {
      disposed = true;
      window.removeEventListener("noether:ready", intro);
      window.clearTimeout(toastTimer.id);
      trigger?.kill();
      io?.disconnect();
      scene?.dispose();
      sceneRef.current = null;
    };
  }, []);

  useEffect(() => {
    sceneRef.current?.setBuild(build);
  }, [build]);

  // keyboard only while the level has focus, so Space still scrolls the page elsewhere
  useEffect(() => {
    const el = game.current;
    if (!el) return;
    const held = new Set<string>();
    const push = () => {
      const input: Input = { x: 0, z: 0, jump: false };
      held.forEach((code) => {
        const [axis, v] = KEYS[code];
        if (axis === "jump") input.jump = true;
        else input[axis] = Math.max(-1, Math.min(1, input[axis] + v));
      });
      sceneRef.current?.setInput(input);
    };
    const onDown = (e: KeyboardEvent) => {
      if (e.code === "Escape") {
        el.blur();
        return;
      }
      if (!KEYS[e.code]) return;
      e.preventDefault();
      held.add(e.code);
      push();
    };
    const onUp = (e: KeyboardEvent) => {
      if (!KEYS[e.code]) return;
      held.delete(e.code);
      push();
    };
    const onFocus = () => {
      setPlaying(true);
      sceneRef.current?.setPlaying(true);
    };
    const onBlur = () => {
      held.clear();
      push();
      setPlaying(false);
      sceneRef.current?.setPlaying(false);
    };
    el.addEventListener("keydown", onDown);
    el.addEventListener("keyup", onUp);
    el.addEventListener("focus", onFocus);
    el.addEventListener("blur", onBlur);
    return () => {
      el.removeEventListener("keydown", onDown);
      el.removeEventListener("keyup", onUp);
      el.removeEventListener("focus", onFocus);
      el.removeEventListener("blur", onBlur);
    };
  }, []);

  const touchInput = useRef<Input>({ x: 0, z: 0, jump: false });
  const touch = (axis: keyof Input, v: number) => ({
    onPointerDown: (e: React.PointerEvent) => {
      e.preventDefault();
      sceneRef.current?.setPlaying(true);
      setPlaying(true);
      touchInput.current = { ...touchInput.current, [axis]: axis === "jump" ? true : v };
      sceneRef.current?.setInput(touchInput.current);
    },
    onPointerUp: () => {
      touchInput.current = { ...touchInput.current, [axis]: axis === "jump" ? false : 0 };
      sceneRef.current?.setInput(touchInput.current);
    },
    onPointerLeave: () => {
      touchInput.current = { ...touchInput.current, [axis]: axis === "jump" ? false : 0 };
      sceneRef.current?.setInput(touchInput.current);
    },
  });
  const jb = base.jump!;
  const jh = head.jump!;

  return (
    <section
      ref={section}
      id="observe"
      data-route="observe"
      data-label="01 Observe"
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
          aria-label={`Hopper level, ${BUILD_NAME[build]} build. D or right arrow runs, Space jumps, W and S move in depth, Escape stops.`}
          onPointerDown={() => game.current?.focus()}
        >
          <canvas ref={canvas} className={styles.canvas} aria-hidden="true" />
        </div>

        <div className={styles.tags} aria-hidden="true">
          <span ref={bindTag("base")} className={`${styles.tag} ${styles.tagBase}`}>BASE</span>
          <span ref={bindTag("head")} className={`${styles.tag} ${styles.tagHead}`}>HEAD</span>
          <span ref={bindTag("you")} className={styles.tag}>YOU · {BUILD_NAME[build].toUpperCase()}</span>
          <span ref={bindTag("gap")} className={styles.measure}>gap {GAP.width.toFixed(2)}</span>
          <span ref={bindTag("baseMark")} className={`${styles.measure} ${styles.mBase}`}>base {n3(jb.margin)}</span>
          <span ref={bindTag("headMark")} className={`${styles.measure} ${styles.mHead}`}>head {n3(jh.margin)}</span>
        </div>

        <div className={styles.copy} data-hero>
          <p className="label" data-hero-cast>01 · Observe · Hopper, a 3D platformer</p>
          <h1 className={styles.title}>
            <span className={styles.lineMask}><span data-line>CI is green.</span></span>
            <span className={styles.lineMask}><span data-line>The jump is <em>broken.</em></span></span>
          </h1>
          <p className={styles.lead} data-hero-cast>
            A refactor pull request. Its own {ownSuitePassed} tests pass before and after. The same recorded run clears the
            last gap on base and comes down {Math.abs(jh.margin).toFixed(2)} units short on head. Play both.
          </p>
          <div className={styles.controls} data-hero-cast>
            <button type="button" className={styles.play} onClick={() => game.current?.focus()}>
              {playing ? "Playing: Escape to stop" : `Play the ${BUILD_NAME[build].toLowerCase()} build`}
            </button>
            <div className={styles.switch} role="radiogroup" aria-label="Build">
              {(["base", "head"] as Build[]).map((b) => (
                <button
                  key={b}
                  type="button"
                  role="radio"
                  aria-checked={build === b}
                  className={`${styles.opt} ${b === "base" ? styles.optBase : styles.optHead}`}
                  onClick={() => setBuild(b)}
                >
                  {BUILD_NAME[b]}
                </button>
              ))}
            </div>
            <button type="button" className={styles.ghostBtn} onClick={() => sceneRef.current?.replay()}>
              Replay the run
            </button>
          </div>
          <p className={styles.keys} data-hero-cast aria-hidden="true">
            <kbd>A</kbd><kbd>D</kbd> run · <kbd>W</kbd><kbd>S</kbd> depth · <kbd>Space</kbd> jump
          </p>
        </div>

        <aside className={styles.hud} aria-label="Measurements from the recorded run">
          <p className={styles.hudHead}>
            <span>frame</span> <b ref={bindHud("frame")} className="tabular">000</b>
            <span>/ {String(Math.max(base.frames.length, head.frames.length) - 1)}</span>
          </p>
          <dl className={styles.cols}>
            <div className={styles.colBase}>
              <dt>Base</dt>
              <dd>x <b ref={bindHud("baseX")} className="tabular">0.00</b></dd>
              <dd>p <b ref={bindHud("baseP")} className="tabular">0.00</b></dd>
              <dd className={styles.fact}>long jump p {formatChange(jb.pChange)} · lands {n3(jb.margin)}</dd>
            </div>
            <div className={styles.colHead}>
              <dt>Head</dt>
              <dd>x <b ref={bindHud("headX")} className="tabular">0.00</b></dd>
              <dd>p <b ref={bindHud("headP")} className="tabular">0.00</b></dd>
              <dd className={styles.fact}>long jump p {formatChange(jh.pChange)} · short {n3(jh.margin)}</dd>
            </div>
          </dl>
        </aside>

        <aside className={styles.you} aria-label="Your run">
          <p className={styles.hudHead}>
            <span>you · {BUILD_NAME[build].toLowerCase()}</span>
          </p>
          <p>x <b ref={bindHud("youX")} className="tabular">0.00</b> · p <b ref={bindHud("youP")} className="tabular">0.00</b></p>
          <p>last jump p <b ref={bindHud("youJump")}>no jump yet</b></p>
          <p ref={bindHud("youTries")} className={styles.tries}>0 tries · 0 cleared the gap</p>
          <p className={styles.toast} role="status" aria-live="polite">{toast}</p>
        </aside>

        <div className={styles.pad} aria-hidden="true">
          <button type="button" tabIndex={-1} {...touch("x", -1)}>Left</button>
          <button type="button" tabIndex={-1} {...touch("z", -1)}>Back</button>
          <button type="button" tabIndex={-1} {...touch("z", 1)}>Front</button>
          <button type="button" tabIndex={-1} {...touch("x", 1)}>Right</button>
          <button type="button" tabIndex={-1} className={styles.jump} {...touch("jump", 1)}>Jump</button>
        </div>

        <div className={styles.note}>
          <p className="label">The conserved quantity</p>
          <p className={styles.noteText}>
            Emmy Noether, 1915: every continuous symmetry of a system has a quantity it conserves. Nothing in the air
            pushes Hopper sideways, so its sideways momentum p should stay put mid-jump. On base it does ({formatChange(jb.pChange)}).
            On head it drops {formatChange(jh.pChange).replace("−", "")}, because friction now acts in the air.
          </p>
        </div>
      </div>
    </section>
  );
}
