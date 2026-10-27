import type { Metadata } from "next";
import { Block, PlainPage, plain } from "@/components/plain/PlainPage";
import { EVAL, caseResult, percent, stampDate, wrongRuns, type Outcome } from "@/lib/evals";
import { REPO_URL } from "@/lib/site";
import styles from "./Evals.module.css";

export const metadata: Metadata = {
  title: "Benchmark",
  description:
    "How often Noether catches a silent break and how often it raises a false alarm, measured on known pull requests, three runs each, with every miss listed.",
  alternates: { canonical: "/evals" },
};

const s = EVAL.summary;
const notes = Object.fromEntries(EVAL.cases.map((c) => [c.case, c.note]));
const wrong = wrongRuns(EVAL);
const RIGHT: Outcome[] = ["caught", "ok"];

function tone(outcome: Outcome) {
  if (RIGHT.includes(outcome)) return styles.right;
  return outcome === "inconclusive" ? styles.unsure : styles.wrong;
}

// "sindresorhus/slugify#79 (https://github.com/...)" in a case note becomes one link named by the short form
function linkSources(note: string) {
  return note.split(/(\S+ \(https:\/\/github\.com\/[^)\s]+\))/).map((part, i) => {
    const m = /^(\S+) \((https:\/\/github\.com\/[^)\s]+)\)$/.exec(part);
    return m ? (
      <a key={i} href={m[2]} rel="noopener">
        {m[1]}
      </a>
    ) : (
      part
    );
  });
}

const minutes = (sec: number) => `${Math.floor(sec / 60)} min ${Math.round(sec % 60)} s`;

export default function EvalsPage() {
  const report = `${REPO_URL}/blob/main/evals/results/${EVAL.stamp}.md`;
  return (
    <PlainPage
      kicker="Benchmark"
      title={`${s.cases.length} pull requests, ${EVAL.runs_per_case} runs each.`}
      updated={stampDate(EVAL.stamp)}
      lede="Small repositories with a known base and head. Some hide a silent break; the rest change only what their pull request says. Each went through the real pipeline, Nemotron on Token Factory and every check in Nebius Sandboxes, several times over, because each run pins its own checks."
    >
      <Block n={1} title="The numbers">
        <dl className={styles.figures}>
          <div>
            <dt>Hit rate on silent breaks</dt>
            <dd>{percent(s.silent_break_caught, s.silent_break_runs)}</dd>
            <p>{s.silent_break_caught} of {s.silent_break_runs} runs ended BROKEN</p>
          </div>
          <div>
            <dt>False alarms on announced changes</dt>
            <dd>{percent(s.announced_false_alarms, s.announced_runs)}</dd>
            <p>{s.announced_false_alarms} of {s.announced_runs} runs ended BROKEN</p>
          </div>
          <div>
            <dt>Inconclusive</dt>
            <dd>{s.inconclusive}</dd>
            <p>of {s.runs} runs, counted against both rates</p>
          </div>
          <div>
            <dt>Model cost, all runs</dt>
            <dd>${s.cost_usd.toFixed(2)}</dd>
            <p>{minutes(EVAL.wall_seconds)} on the clock, {EVAL.workers} runs at a time</p>
          </div>
        </dl>
        <p>
          A hit is a run on a silent-break case that ends BROKEN. A false alarm is a BROKEN verdict on a case where every
          change is announced. Cost is the estimate from model tokens; sandbox time is free while Sandboxes is in beta.
        </p>
      </Block>

      <Block n={2} title="Case by case">
        <table className={`${plain.table} ${styles.cases}`}>
          <thead>
            <tr>
              <th scope="col">Case</th>
              <th scope="col">Expected</th>
              <th scope="col">Verdicts</th>
              <th scope="col">Result</th>
            </tr>
          </thead>
          <tbody>
            {s.cases.map((c) => (
              <tr key={c.case}>
                <td>
                  {c.case}
                  <span className={styles.note}>{linkSources(notes[c.case] ?? "")}</span>
                </td>
                <td className={styles.expected}>{c.expected.toLowerCase()}</td>
                <td className={styles.verdicts}>
                  {c.verdicts.map((v, i) => (
                    <span key={i}>
                      {i > 0 && " · "}
                      <span className={tone(c.outcomes[i])}>{v.toLowerCase()}</span>
                    </span>
                  ))}
                </td>
                <td>{caseResult(c)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Block>

      <Block n={3} title="Where it falls short">
        <p>
          In every miss, each pinned check either still held on head or flipped in a way the judge read as announced: the
          proof ran, but the behaviour that slipped was never pinned, or it hid behind an announced one.
        </p>
        <ul className={styles.misses}>
          {wrong.map((r) => (
            <li key={`${r.case}-${r.run}`}>
              <code>{r.case}</code> run {r.run}, {r.verdict.toLowerCase()}: {r.reason}
            </li>
          ))}
        </ul>
      </Block>

      <Block n={4} title="Run it yourself">
        <p>
          The cases live in <code>evals/cases</code> with their base, head and pull request text. One command runs them
          all and writes a markdown and a JSON report; this page is built from the newest JSON. The runner stops before
          it spends more than ${EVAL.budget_usd.toFixed(2)} a round.
        </p>
        <pre className={styles.cmd}>
          <code>python -m evals.run --runs {EVAL.runs_per_case} --runner {EVAL.runner}</code>
        </pre>
        <p>
          This round ran at commit <code>{EVAL.commit}</code>. Full report:{" "}
          <a href={report} rel="noopener">
            evals/results/{EVAL.stamp}.md
          </a>
          .
        </p>
      </Block>
    </PlainPage>
  );
}
