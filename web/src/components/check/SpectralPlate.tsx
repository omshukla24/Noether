import { lineCounts, type SpectralLine } from "@/lib/cockpit";
import styles from "./Check.module.css";

interface SpectralPlateProps {
  lines: SpectralLine[];
  intent: string;
}

function stateText(l: SpectralLine): string {
  if (l.base === "dropped") return "dropped";
  if (l.base === "red") return "red on base";
  if (l.base === "pending") return "pinned";
  if (l.base === "green1") return "green once";
  if (l.head === "pending") return "locked on base";
  if (l.head === "pass") return "locked, held";
  return l.kind === "intended" ? "flipped, intended" : l.kind === "silent" ? "flipped, silent" : "flipped";
}

export function SpectralPlate({ lines, intent }: SpectralPlateProps) {
  const counts = lineCounts(lines);
  return (
    <section className={styles.plate} aria-label="Pinned checks">
      <header className={styles.plateHead}>
        <span className="label">Spectral plate</span>
        <dl className={`${styles.counts} tabular`}>
          <div><dt>Pinned</dt><dd>{counts.total}</dd></div>
          <div><dt>Locked</dt><dd>{counts.locked}</dd></div>
          <div className={counts.flips ? styles.countBroken : undefined}><dt>Flipped</dt><dd>{counts.flips}</dd></div>
          <div><dt>Dropped</dt><dd>{counts.dropped}</dd></div>
        </dl>
      </header>
      {intent ? <p className={styles.intent}>{intent}</p> : null}
      <div className={styles.legend} aria-hidden="true">
        <span><i className={styles.keyBase} /> Base</span>
        <span><i className={styles.keyHead} /> Head</span>
      </div>
      {lines.length ? (
        <ol className={styles.lines}>
          {lines.map((l, i) => {
            const found = l.head === "flip" && l.location;
            return (
              <li key={l.name} className={styles.line} data-base={l.base} data-head={l.head} data-kind={l.kind ?? undefined}>
                <span className={styles.idx}>{String(i + 1).padStart(2, "0")}</span>
                <span className={styles.lineText}>
                  <span className={styles.name}>{l.name}</span>
                  <span className={styles.claim}>{l.claim}</span>
                  {found ? (
                    <span className={styles.found}>
                      {l.kind ?? "flip"} · {l.location!.file}
                      {l.location!.line ? `:${l.location!.line}` : ""}
                      {l.proved ? " · fix proved" : ""}
                    </span>
                  ) : null}
                </span>
                <span className={styles.tracks} aria-hidden="true">
                  <span className={styles.baseLine} />
                  <span className={styles.headLine} />
                </span>
                <span className={styles.state}>{stateText(l)}</span>
              </li>
            );
          })}
        </ol>
      ) : (
        <p className={styles.waiting}>Waiting for the first pinned check.</p>
      )}
      <div className={styles.scale} aria-hidden="true">
        {Array.from({ length: 41 }, (_, i) => (
          <span key={i} className={i % 10 === 0 ? styles.scaleMajor : undefined} />
        ))}
      </div>
    </section>
  );
}
