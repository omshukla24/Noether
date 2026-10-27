import type { Metadata } from "next";
import Link from "next/link";
import styles from "@/components/plain/Plain.module.css";

export const metadata: Metadata = {
  title: "Nothing pinned here",
  description: "No line was ever pinned at this address. Return to the plate, or paste a pull request to expose one.",
  robots: { index: false },
};

export default function NotFound() {
  return (
    <div className={styles.lost} data-route="lost" data-label="404" data-theme="light">
      <p className={styles.lostCode}>404 · No spectral line</p>
      <h1 className={styles.lostLine}>
        No line was ever pinned at <em>this address.</em>
      </h1>
      <div className={styles.slit} aria-hidden="true">
        <span />
        <i />
        <span />
      </div>
      <div className={styles.row}>
        <Link className={styles.btn} href="/">
          Return to the plate
        </Link>
        <Link className={styles.btnGhost} href="/check">
          Check a pull request
        </Link>
      </div>
    </div>
  );
}
