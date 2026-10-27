"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import styles from "./Emmy.module.css";

const WORD = "emmy";

/** True when the key press belongs to something the visitor is typing into. */
function isTyping(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  return !!el && (el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName));
}

/** Feeds typed letters through a rolling window; true when the last letters spell the word. */
export function spells(typed: string, key: string, word = WORD): { typed: string; hit: boolean } {
  const next = (typed + key.toLowerCase()).slice(-word.length);
  return { typed: next, hit: next === word };
}

export function TheoremPlate({ onClose, heading = false }: { onClose: () => void; heading?: boolean }) {
  const Line = heading ? "h1" : "p";
  const close = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    close.current?.focus();
    return () => previous?.focus?.();
  }, []);
  return (
    <div className={`${styles.plate} notebook`} role="dialog" aria-modal="true" aria-label="Noether's theorem" onClick={onClose}>
      <div className={styles.dim} aria-hidden="true" />
      <figure className={styles.figure}>
        <Line className={styles.theorem}>To every differentiable symmetry, a conserved quantity.</Line>
        <figcaption className={styles.cap}>
          <span className={styles.rule} aria-hidden="true" />
          Proof controls everything.
        </figcaption>
      </figure>
      <button ref={close} type="button" className={styles.close} onClick={onClose}>
        Close <kbd>Esc</kbd>
      </button>
    </div>
  );
}

// Type "emmy" anywhere outside a field and the theorem is set in the page.
export function Emmy() {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    let typed = "";
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") return setOpen(false);
      if (e.ctrlKey || e.metaKey || e.altKey || e.key.length !== 1 || isTyping(e.target)) return;
      const step = spells(typed, e.key);
      typed = step.typed;
      if (step.hit) {
        typed = "";
        setOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  return open ? <TheoremPlate onClose={() => setOpen(false)} /> : null;
}

// The same plate as a page at /1915, the year Noether proved it.
export function EmmyRoute() {
  const router = useRouter();
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && router.push("/");
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [router]);
  return <TheoremPlate heading onClose={() => router.push("/")} />;
}
