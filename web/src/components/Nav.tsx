"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import styles from "./Nav.module.css";

const LINKS = [
  { href: "/#observe", label: "Observe", route: "observe" },
  { href: "/#measure", label: "Measure", route: "measure" },
  { href: "/#judge", label: "Judge", route: "judge" },
  { href: "/check", label: "Check a PR", route: "check" },
];

// Sections mark themselves with data-route + data-label; the nav follows the one in view.
export function Nav() {
  const pathname = usePathname();
  const [section, setSection] = useState({ route: "", label: "" });
  const trackRef = useRef<HTMLDivElement>(null);
  const tickRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (pathname !== "/") {
      setSection({ route: pathname.startsWith("/check") ? "check" : "", label: "" });
      return;
    }
    const sections = [...document.querySelectorAll<HTMLElement>("[data-route]")];
    if (!sections.length) return;
    const onIntersect = (entries: IntersectionObserverEntry[]) => {
      const visible = entries.filter((e) => e.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
      if (!visible) return;
      const el = visible.target as HTMLElement;
      setSection({ route: el.dataset.route ?? "", label: el.dataset.label ?? "" });
      document.documentElement.dataset.theme = el.dataset.theme ?? "light";
    };
    const io = new IntersectionObserver(onIntersect, { threshold: [0.2, 0.5, 0.8] });
    sections.forEach((s) => io.observe(s));
    return () => io.disconnect();
  }, [pathname]);

  useEffect(() => {
    const track = trackRef.current;
    const tick = tickRef.current;
    if (!track || !tick) return;
    const active = track.querySelector<HTMLElement>(`[data-nav="${section.route}"]`);
    if (!active) {
      tick.style.opacity = "0";
      return;
    }
    tick.style.opacity = "1";
    tick.style.transform = `translateX(${active.offsetLeft + active.offsetWidth / 2}px)`;
  }, [section.route]);

  return (
    <header className={styles.bar}>
      <Link href="/" className={styles.brand} aria-label="Noether, home">
        Noether
      </Link>
      <span className={styles.crumb} aria-live="polite">
        {section.label ? `/ ${section.label}` : ""}
      </span>
      <nav aria-label="Main" className={styles.track} ref={trackRef}>
        {LINKS.map((l) => (
          <Link
            key={l.href}
            href={l.href}
            data-nav={l.route}
            className={l.route === "check" ? styles.cta : styles.link}
            aria-current={section.route === l.route ? "true" : undefined}
          >
            {l.label}
          </Link>
        ))}
        <span className={styles.tick} ref={tickRef} aria-hidden="true" />
      </nav>
    </header>
  );
}
