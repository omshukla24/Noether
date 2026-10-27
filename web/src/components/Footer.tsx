"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import styles from "./Footer.module.css";

const REPO_URL = "https://github.com/omshukla24/Noether";

function istNow(): string {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Kolkata",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(new Date());
}

export function Footer() {
  const [clock, setClock] = useState("");
  useEffect(() => {
    setClock(istNow());
    const id = window.setInterval(() => setClock(istNow()), 1000);
    return () => window.clearInterval(id);
  }, []);

  return (
    <footer className={styles.foot} data-theme="dark">
      <p className={styles.pun}>All rights conserved.</p>
      <div className={styles.row}>
        <span>Noether · built on NVIDIA Nemotron and Nebius Token Factory</span>
        <span className={styles.clock} aria-label="Time in India">
          IST {clock || "--:--:--"}
        </span>
        <nav aria-label="Footer" className={styles.links}>
          <Link href="/check">Check a PR</Link>
          <Link href="/privacy">Privacy</Link>
          <Link href="/terms">Terms</Link>
          <a href={REPO_URL} rel="noopener">Source</a>
        </nav>
      </div>
    </footer>
  );
}
