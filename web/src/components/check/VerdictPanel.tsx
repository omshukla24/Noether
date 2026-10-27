import type { CockpitState } from "@/lib/cockpit";
import styles from "./Check.module.css";

const TONE = { CONSERVED: styles.toneConserved, BROKEN: styles.toneBroken, INCONCLUSIVE: styles.toneUnknown } as const;

export function VerdictPanel({ state }: { state: CockpitState }) {
  const { verdict } = state;
  return (
    <section className={styles.verdict} aria-label="Verdict">
      <span className="label">Verdict</span>
      <p className={`${styles.word} ${verdict ? TONE[verdict] : styles.wordPending}`}>{verdict ?? (state.phase === "failed" ? "No verdict" : "Pending")}</p>
      {state.reason ? <p className={styles.reason}>{state.reason}</p> : null}
      {state.sha256 ? (
        <p className={`${styles.seal} tabular`}>
          sealed · sha256 {state.sha256.slice(0, 12)}…{state.sha256.slice(-6)}
        </p>
      ) : null}
    </section>
  );
}
