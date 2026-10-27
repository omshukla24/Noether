import { formatMs, type RailRow } from "@/lib/cockpit";
import styles from "./Check.module.css";

interface StageRailProps {
  rail: RailRow[];
  lastMs: number;
  running: boolean;
}

const STEPS = [1, 2, 5, 10, 15, 30, 60, 120];

/** Seconds between ruler ticks, so the axis never carries more than about eight of them. */
export function tickStep(totalMs: number): number {
  return STEPS.find((s) => totalMs / 1000 / s <= 8) ?? 120;
}

export function StageRail({ rail, lastMs, running }: StageRailProps) {
  const total = Math.max(lastMs, 4000);
  const step = tickStep(total);
  const ticks = Array.from({ length: Math.floor(total / 1000 / step) + 1 }, (_, i) => i * step);
  const pct = (ms: number) => `${Math.min(100, (ms / total) * 100)}%`;

  return (
    <section className={styles.rail} aria-label="Stages">
      <div className={styles.railHead}>
        <span className="label">Stage rail</span>
        <span className={`${styles.clock} tabular`} aria-label="Run time">
          {(lastMs / 1000).toFixed(1)}s
        </span>
      </div>
      <div className={styles.axis} aria-hidden="true">
        {ticks.map((s) => (
          <span key={s} className={styles.tick} style={{ left: pct(s * 1000) }}>
            {s}s
          </span>
        ))}
      </div>
      <ol className={styles.stages}>
        {rail.map((row, i) => {
          const start = row.startMs ?? 0;
          const end = row.endMs ?? (row.status === "running" ? lastMs : start);
          return (
            <li key={row.key} className={styles.stage} data-status={row.status} aria-current={row.status === "running" && running ? "step" : undefined}>
              <span className={styles.stageIdx}>{String(i + 1).padStart(2, "0")}</span>
              <span className={styles.stageName}>{row.label}</span>
              <span className={`${styles.stageTime} tabular`}>
                {row.status === "idle" ? "" : row.status === "running" ? "running" : formatMs(row.endMs !== null && row.startMs !== null ? row.endMs - row.startMs : null)}
              </span>
              <span className={styles.bar} aria-hidden="true">
                {row.startMs !== null ? <span className={styles.barFill} style={{ left: pct(start), width: pct(Math.max(end - start, 120)) }} /> : null}
              </span>
              {row.note ? <span className={styles.stageNote}>{row.note}</span> : null}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
