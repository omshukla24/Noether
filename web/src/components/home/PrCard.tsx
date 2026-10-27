import pr from "@/hopper/pr.json";
import { RUN } from "@/lib/run";
import { announcedLines, prDiff, prFile } from "@/lib/story";
import { Ruler } from "./Ruler";
import styles from "./PrCard.module.css";

const intended = RUN.intent?.intended_changes ?? [];
const marks = announcedLines(prDiff, intended);
const candidates = RUN.invariants.length + RUN.dropped.length;
const bodyParagraphs = pr.body.split("\n\n");

// 02 Pin: the pull request as a reviewer sees it, and what Nano and Super made of it.
export function PrCard() {
  return (
    <section id="pin" data-route="pin" data-label="02 Pin" data-theme="light" className={styles.section}>
      <div className={styles.lead}>
        <p className="label">02 · Pin</p>
        <h2 className={styles.title} data-split>
          It says it changed two things.
        </h2>
        <p className={styles.deck} data-rise>
          Noether reads the pull request the way a reviewer would, then pins what the code did before it as checks that
          have to pass on base before they count.
        </p>

        <div className={styles.read} data-rise>
          <p className="label">Nano read the intent</p>
          <p className={styles.summary}>{RUN.intent?.summary}</p>
          <ul className={styles.said}>
            {intended.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </div>

        <div className={styles.pinned} data-rise>
          <p className="label">Super pinned</p>
          <div className={styles.counts}>
            <p>
              <b className="tabular" data-count={RUN.invariants.length}>{RUN.invariants.length}</b>
              <span>held on base, twice</span>
            </p>
            <p className={styles.dropped}>
              <b className="tabular" data-count={RUN.dropped.length}>{RUN.dropped.length}</b>
              <span>of {candidates} written were red on base</span>
            </p>
          </div>
          <details className={styles.why}>
            <summary>Why a red check is dropped</summary>
            <p>A check that fails before the change proves nothing about the change.</p>
            <ul>
              {RUN.dropped.map((d) => (
                <li key={d.name}>
                  <code>{d.name}</code>
                </li>
              ))}
            </ul>
          </details>
        </div>
      </div>

      <article className={styles.card} aria-label="The pull request" data-rise>
        <Ruler steps={40} major={5} className={styles.cardRuler} />
        <header className={styles.head}>
          <p className="label">
            Pull request · {RUN.base.sha.slice(0, 7)} → {RUN.head.sha.slice(0, 7)}
          </p>
          <h3 className={styles.prTitle}>{pr.title}</h3>
        </header>
        <div className={styles.body}>
          {bodyParagraphs.map((paragraph) => (
            <p key={paragraph} className={styles.para}>
              {paragraph}
            </p>
          ))}
        </div>

        <div className={styles.fileBar}>
          <code>{prFile.path}</code>
          <span className={`${styles.delta} tabular`}>
            <span className={styles.plus}>+<b data-count={prFile.added}>{prFile.added}</b></span>
            <span className={styles.minus}>−<b data-count={prFile.removed}>{prFile.removed}</b></span>
          </span>
        </div>
        <div className={styles.code} tabIndex={0} role="region" aria-label={`Diff of ${prFile.path}`}>
          {prDiff.map((line, i) => {
            const mark = marks.get(i);
            const announced = mark !== undefined;
            return (
              <div key={i} className={`${styles.row} ${styles[line.kind]}`}>
                <span className={styles.no} aria-hidden="true">{line.oldNo ?? ""}</span>
                <span className={styles.no} aria-hidden="true">{line.newNo ?? ""}</span>
                <span className={styles.sign} aria-hidden="true">
                  {line.kind === "add" ? "+" : line.kind === "del" ? "−" : ""}
                </span>
                <code className={styles.text}>
                  {line.kind === "hunk" ? (
                    <span className={styles.hunkText}>{line.text || "···"}</span>
                  ) : announced ? (
                    <span className={styles.announced} data-draw>{line.text}</span>
                  ) : (
                    line.text
                  )}
                </code>
                {mark && (
                  <span className={styles.margin}>
                    announced{mark.change ? ` · ${mark.change}` : ""}
                  </span>
                )}
              </div>
            );
          })}
        </div>
      </article>
    </section>
  );
}
