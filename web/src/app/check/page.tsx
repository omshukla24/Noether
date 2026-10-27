import type { Metadata } from "next";
import { CheckCockpit } from "@/components/check/CheckCockpit";
import styles from "@/components/check/Check.module.css";

export const metadata: Metadata = {
  title: "Check a pull request",
  description:
    "Paste a public GitHub pull request. Noether pins how the code behaved before it, re-runs it after in a Nebius sandbox, and shows the one change nobody announced.",
  alternates: { canonical: "/check" },
};

export default function CheckPage() {
  return (
    <div className={styles.page} data-route="check" data-label="Check" data-theme="light">
      <header className={styles.head}>
        <p className="label">Check · live</p>
        <h1 className={styles.title}>
          Expose a pull request, <em>line by line.</em>
        </h1>
        <p className={styles.lede}>
          Each pinned check becomes one spectral line. It locks when it is green twice on the base, and it breaks when the head changes it.
        </p>
      </header>
      <CheckCockpit />
    </div>
  );
}
