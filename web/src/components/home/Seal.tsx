import { readFileSync } from "node:fs";
import { join } from "node:path";
import Link from "next/link";
import { RUN } from "@/lib/run";
import { CopyButton, OpenSlot } from "./SealClient";
import styles from "./Seal.module.css";

// The real example workflow, copied from examples/noether.yml by `npm run sync:noether`.
const WORKFLOW = readFileSync(join(process.cwd(), "src", "content", "noether.yml"), "utf8").trimEnd();

export function Seal() {
  const lines = WORKFLOW.split("\n");
  return (
    <section id="seal" data-route="seal" data-label="08 Seal" data-theme="light" className={styles.seal} aria-labelledby="seal-h">
      <div className={styles.inner}>
        <header className={styles.head}>
          <p className="label">08 · Seal</p>
          <h2 id="seal-h" className={styles.title}>
            The slot is <em>open.</em>
          </h2>
          <p className={styles.lede}>Paste a public pull request, or let your repository do it on every pull request with the workflow on the right.</p>
        </header>

        <div className={styles.grid}>
          <div className={styles.left}>
            <OpenSlot />
            <div className={styles.proof}>
              <span className="label">Seal of the Hopper run</span>
              <p className={`${styles.hash} tabular`}>{RUN.sha256}</p>
              <Link href="/runs/hopper" className={styles.verify}>
                Verify this seal in your browser
              </Link>
            </div>
          </div>

          <figure className={styles.code}>
            <figcaption className={styles.codeHead}>
              <span className="label">.github/workflows/noether.yml</span>
              <CopyButton text={`${WORKFLOW}\n`} />
            </figcaption>
            <pre tabIndex={0} aria-label="GitHub workflow">
              {lines.map((line, i) => (
                <span key={i} className={styles.codeLine}>
                  <span className={styles.ln} aria-hidden="true">{String(i + 1).padStart(2, "0")}</span>
                  {line || " "}
                  {"\n"}
                </span>
              ))}
            </pre>
          </figure>
        </div>
      </div>
    </section>
  );
}
