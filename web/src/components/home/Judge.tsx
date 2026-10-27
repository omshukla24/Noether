"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { gsap } from "gsap";
import { JUDGE } from "@/motion/config.js";
import { prefersReducedMotion } from "@/motion/env.js";
import type { JudgeCase, Truth } from "@/lib/judge";
import { Ruler } from "./Ruler";
import styles from "./Judge.module.css";

interface JudgeProps {
  cases: JudgeCase[];
  /** what Nano read the pull request as announcing */
  announced: string[];
}

// Meta's published result for just-in-time catching, cited as the reason a judge is needed.
const META = { catches: 41, real: 8, paper: "arXiv 2601.22832" };

const LABEL: Record<Truth, string> = { intended: "Intended", silent: "Silent" };

// Dragging needs a fine pointer and motion; touch and reduced motion get the buttons and arrow keys.
const noSubscription = () => () => {};
const dragAllowed = () => !prefersReducedMotion() && !window.matchMedia("(pointer: coarse)").matches;

// 05 Judge: the visitor rules on two real flips before Nemotron Ultra's recorded ruling is shown.
export function Judge({ cases, announced }: JudgeProps) {
  const card = useRef<HTMLElement>(null);
  const arena = useRef<HTMLDivElement>(null);
  const zones = useRef<Record<Truth, HTMLDivElement | null>>({ intended: null, silent: null });
  const drag = useRef<{ x: number; y: number; id: number } | null>(null);
  const [index, setIndex] = useState(0);
  const [answers, setAnswers] = useState<(Truth | null)[]>(() => cases.map(() => null));
  const [over, setOver] = useState<Truth | null>(null);
  const canDrag = useSyncExternalStore(noSubscription, dragAllowed, () => false);

  const current = cases[index];
  const answer = answers[index];
  const done = answers.every(Boolean);
  const matched = answers.filter((a, i) => a === cases[i].truth).length;

  useEffect(() => {
    const el = card.current;
    return () => {
      if (el) gsap.killTweensOf(el);
    };
  }, []);

  const choose = (side: Truth) => {
    if (answer) return;
    setAnswers((prev) => prev.map((a, i) => (i === index ? side : a)));
    setOver(null);
    const el = card.current;
    const zone = zones.current[side];
    if (!el || !zone || !canDrag) return;
    const a = el.getBoundingClientRect();
    const z = zone.getBoundingClientRect();
    gsap.to(el, {
      x: `+=${z.left + z.width / 2 - (a.left + a.width / 2)}`,
      y: `+=${z.top + z.height / 2 - (a.top + a.height / 2)}`,
      rotation: 0,
      scale: 0.82,
      duration: 0.7,
      ease: "power3.out",
    });
  };

  const release = (e: React.PointerEvent) => {
    const el = card.current;
    if (!drag.current || !el) return;
    el.releasePointerCapture?.(drag.current.id);
    const dx = gsap.getProperty(el, "x") as number;
    drag.current = null;
    if (Math.abs(dx) >= JUDGE.dropDistance) {
      choose(dx < 0 ? "intended" : "silent");
      return;
    }
    setOver(null);
    gsap.to(el, { x: 0, y: 0, rotation: 0, duration: JUDGE.springDuration, ease: "elastic.out(1, 0.5)" });
    e.preventDefault();
  };

  const next = () => {
    const el = card.current;
    if (el) gsap.fromTo(el, { x: 0, y: 24, scale: 1, rotation: 0, opacity: 0 }, { y: 0, opacity: 1, duration: 0.7, ease: "power3.out" });
    setIndex((i) => Math.min(i + 1, cases.length - 1));
  };

  const again = () => {
    setAnswers(cases.map(() => null));
    setIndex(0);
    const el = card.current;
    if (el) gsap.set(el, { clearProps: "all" });
  };

  const [lead, ...cmp] = current.failure.split(": ");

  return (
    <section id="judge" data-route="judge" data-label="05 Judge" data-theme="light" className={styles.section}>
      <header className={styles.intro}>
        <p className="label">05 · Judge</p>
        <h2 className={styles.title} data-split>You be the judge.</h2>
        <p className={styles.deck} data-rise>
          A flip is a pinned check that passed on base and fails on head. Some flips are the change the author meant. A
          silent one is behaviour nobody announced. These are two real runs of the same pull request, and the judge has
          already ruled on both.
        </p>
        <div className={styles.said} data-rise>
          <p className="label">The pull request announced</p>
          <ul>
            {announced.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </div>
      </header>

      <div className={styles.arena} ref={arena}>
        {(["intended", "silent"] as Truth[]).map((side) => (
          <div
            key={side}
            ref={(n) => { zones.current[side] = n; }}
            className={`${styles.zone} ${side === "intended" ? styles.left : styles.right}`}
            data-over={over === side ? "" : undefined}
            data-chosen={answer === side ? "" : undefined}
          >
            <span className={styles.zoneName}>{LABEL[side]}</span>
            <span className={styles.zoneHint}>{side === "intended" ? "the pull request said so" : "nobody said so"}</span>
          </div>
        ))}

        <article
          ref={card}
          className={styles.flip}
          data-drag={canDrag && !answer ? "" : undefined}
          tabIndex={0}
          aria-label={`Flip ${index + 1} of ${cases.length}: ${current.name}. Press left arrow for intended, right arrow for silent.`}
          onKeyDown={(e) => {
            if (e.key === "ArrowLeft") choose("intended");
            if (e.key === "ArrowRight") choose("silent");
          }}
          onPointerDown={(e) => {
            const el = card.current;
            if (!canDrag || answer || !el || e.button !== 0) return;
            el.setPointerCapture(e.pointerId);
            drag.current = { x: e.clientX - (gsap.getProperty(el, "x") as number), y: e.clientY - (gsap.getProperty(el, "y") as number), id: e.pointerId };
            gsap.killTweensOf(el);
          }}
          onPointerMove={(e) => {
            const el = card.current;
            if (!drag.current || !el) return;
            const x = e.clientX - drag.current.x;
            const y = e.clientY - drag.current.y;
            gsap.set(el, { x, y, rotation: x * JUDGE.tilt });
            setOver(Math.abs(x) >= JUDGE.dropDistance ? (x < 0 ? "intended" : "silent") : null);
          }}
          onPointerUp={release}
          onPointerCancel={release}
        >
          <p className="label">
            Flip {index + 1} of {cases.length} · run {current.runId}
          </p>
          <h3 className={styles.name}><code>{current.name}</code></h3>
          <p className={styles.claim}>{current.claim}</p>
          <div className={styles.output}>
            <span className={styles.outLead}>{lead}</span>
            <code className={styles.outCmp}>{cmp.join(": ")}</code>
          </div>
          <p className={styles.passfail}>
            base <b className={styles.ok}>pass</b> → head <b className={styles.bad}>fail</b>
          </p>
          <Ruler steps={24} major={4} className={styles.cardRuler} />
        </article>
      </div>

      <div className={styles.controls}>
        <button type="button" className={styles.choice} data-side="intended" disabled={Boolean(answer)} onClick={() => choose("intended")}>
          Intended
        </button>
        <p className={styles.hint}>
          {canDrag ? "Drag the card to a side, or use the buttons." : "Choose a side."} Left and right arrow keys work when the card has focus.
        </p>
        <button type="button" className={styles.choice} data-side="silent" disabled={Boolean(answer)} onClick={() => choose("silent")}>
          Silent
        </button>
      </div>

      <div className={styles.reveal} aria-live="polite">
        {answer && (
          <div className={styles.ruling} data-truth={current.truth}>
            <p className="label">Nemotron Ultra ruled</p>
            <p className={styles.rulingWord}>{LABEL[current.truth]}</p>
            <p className={styles.reason}>{current.reason}</p>
            <p className={styles.agree} data-agree={answer === current.truth ? "" : undefined}>
              You said {LABEL[answer].toLowerCase()}: {answer === current.truth ? "you agreed with the judge." : "you differed from the judge."}
            </p>
            <p className={styles.cite}>
              <code>{current.model}</code> · run <a href={`/runs/${current.bundleFile}`}>{current.runId}</a>, sealed
            </p>
            {index < cases.length - 1 ? (
              <button type="button" className={styles.next} onClick={next}>Next flip</button>
            ) : (
              <button type="button" className={styles.next} onClick={again}>Judge them again</button>
            )}
          </div>
        )}
        {done && (
          <p className={`${styles.score} tabular`}>
            You matched the judge on <b>{matched}</b> of {cases.length}.
          </p>
        )}
      </div>

      <p className={styles.why}>
        Why a judge at all: Meta&apos;s just-in-time catching checks reported <b className="tabular">{META.catches}</b> catches, only{" "}
        <b className="tabular">{META.real}</b> of them real ({META.paper}). A failing check is not yet a bug. Someone has to say
        whether the change was meant.
      </p>
    </section>
  );
}
