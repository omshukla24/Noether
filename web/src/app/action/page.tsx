import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { Metadata } from "next";
import Link from "next/link";
import { CopyButton } from "@/components/home/SealClient";
import seal from "@/components/home/Seal.module.css";
import { Block, PlainPage, plain } from "@/components/plain/PlainPage";
import { parseAction, parseCaps, parseExitCodes, pyString, workflowSecrets } from "@/lib/action";
import { commentOf } from "@/lib/comment";
import { RUN } from "@/lib/run";
import { REPO_URL } from "@/lib/site";
import styles from "./Action.module.css";

export const metadata: Metadata = {
  title: "GitHub Action",
  description:
    "Put Noether on your own repository: one workflow file, two Nebius secrets, every input and output of the Action, the comment it posts and when it fails a job.",
  alternates: { canonical: "/action" },
};

// Everything below is read at build time from the files the Action runs (see lib/action.ts). Literal paths, so
// the build traces only these files.
const WORKFLOW = readFileSync(join(process.cwd(), "src", "content", "noether.yml"), "utf8").trimEnd();
const SPEC = parseAction(readFileSync(join(process.cwd(), "src", "content", "action.yml"), "utf8"));
const CAPS = parseCaps(readFileSync(join(process.cwd(), "py", "noether", "pipeline.py"), "utf8"));
const EXIT = parseExitCodes(readFileSync(join(process.cwd(), "py", "noether", "cli.py"), "utf8"));
const IMAGE = pyString(readFileSync(join(process.cwd(), "py", "noether", "runner.py"), "utf8"), "NODE_IMAGE").replace(
  /^docker\.io\/library\//,
  "",
);
const SECRETS = workflowSecrets(WORKFLOW);
const COMMENT = commentOf(RUN);

const input = (name: string) => {
  const found = SPEC.inputs.find((i) => i.name === name);
  if (!found) throw new Error(`action.yml has no input ${name}`);
  return found;
};
const cap = (name: string) => {
  const value = CAPS[name];
  if (typeof value !== "number") throw new Error(`Caps has no number ${name}`);
  return value.toLocaleString("en-US");
};
const CHECK_STEP = SPEC.steps.find((s) => s.startsWith("Check")) ?? SPEC.steps[2];
const GATE_STEP = SPEC.steps.at(-1);
const RUN_TOKENS = RUN.models.reduce((n, m) => n + m.tokens_in + m.tokens_out, 0);

const JOB: Record<string, string> = {
  CONSERVED: "passes",
  BROKEN: `fails at "${GATE_STEP}" while fail-on-broken is "true"`,
  INCONCLUSIVE: "passes; the comment says why the proof did not finish",
};

export default function ActionPage() {
  const lines = WORKFLOW.split("\n");
  return (
    <PlainPage
      kicker="GitHub Action"
      title="Put it on your pull requests."
      updated="28 October 2026"
      lede="One workflow file and two repository secrets. On every pull request Noether pins checks that hold on base, runs them on head in Nebius Sandboxes, and comments the verdict with its proof bundle."
    >
      <Block n={1} title="Add the workflow">
        <p>
          Save this as <code>.github/workflows/noether.yml</code> on your default branch. It runs when a pull request is
          opened, reopened or gets a new push. <code>pull-requests: write</code> lets the job post its comment.
        </p>
        <figure className={`${seal.code} ${styles.file}`}>
          <figcaption className={seal.codeHead}>
            <span className="label">.github/workflows/noether.yml</span>
            <CopyButton text={`${WORKFLOW}\n`} />
          </figcaption>
          <pre tabIndex={0} aria-label="GitHub workflow">
            {lines.map((line, i) => (
              <span key={i} className={seal.codeLine}>
                <span className={seal.ln} aria-hidden="true">
                  {String(i + 1).padStart(2, "0")}
                </span>
                {line || " "}
                {"\n"}
              </span>
            ))}
          </pre>
        </figure>
        <ul>
          <li>
            The repository must be public: the sandbox downloads base and head from <code>codeload.github.com</code>{" "}
            without a token.
          </li>
          <li>
            Pinned checks are written for Node and run in a <code>{IMAGE}</code> microVM, so Noether fits JavaScript
            repositories. When <code>package.json</code> declares the repo&apos;s own suite, that runs as well.
          </li>
          <li>
            GitHub passes no secrets to pull requests opened from forks, so on those the job stops before any run. Branches
            of the repository itself get the full check.
          </li>
        </ul>
      </Block>

      <Block n={2} title="Add the two secrets">
        <p>
          In the repository, open Settings, then Secrets and variables, then Actions, and add each as a repository secret
          with exactly this name. Only the names live in the workflow; the values stay in GitHub.
        </p>
        <table className={plain.table}>
          <thead>
            <tr>
              <th scope="col">Secret</th>
              <th scope="col">Input</th>
              <th scope="col">What it is</th>
            </tr>
          </thead>
          <tbody>
            {SECRETS.map((s) => (
              <tr key={s.secret}>
                <td>{s.secret}</td>
                <td className={styles.mono}>{s.input}</td>
                <td>{input(s.input).description}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p>
          Both come from your Nebius account: the API key from{" "}
          <a href="https://tokenfactory.nebius.com" rel="noopener">
            Token Factory
          </a>
          , and the id of the project the sandboxes run in. Model calls are billed to that key.
        </p>
      </Block>

      <Block n={3} title="Inputs and outputs">
        <table className={plain.table}>
          <thead>
            <tr>
              <th scope="col">Input</th>
              <th scope="col">Required</th>
              <th scope="col">Default</th>
              <th scope="col">What it does</th>
            </tr>
          </thead>
          <tbody>
            {SPEC.inputs.map((i) => (
              <tr key={i.name}>
                <td>{i.name}</td>
                <td>{i.required ? "yes" : "no"}</td>
                <td className={styles.mono}>{i.default === null ? "none" : `"${i.default}"`}</td>
                <td>{i.description}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <table className={plain.table}>
          <thead>
            <tr>
              <th scope="col">Output</th>
              <th scope="col">What it holds</th>
            </tr>
          </thead>
          <tbody>
            {SPEC.outputs.map((o) => (
              <tr key={o.name}>
                <td>{o.name}</td>
                <td>{o.description}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p>
          Inputs are strings, so write <code>fail-on-broken: &quot;false&quot;</code> to comment without failing the job.
          Give the step an <code>id</code> to read the verdict in a later step as{" "}
          <code>steps.&lt;id&gt;.outputs.{SPEC.outputs[0].name}</code>.
        </p>
      </Block>

      <Block n={4} title="What the job runs">
        <ol className={styles.steps}>
          {SPEC.steps.map((s) => (
            <li key={s}>{s.includes("@") ? <code>{s}</code> : s}</li>
          ))}
        </ol>
        <p>
          &quot;{CHECK_STEP}&quot; runs this, with <code>--no-fix</code> in <code>$flags</code> when <code>fix</code> is
          not &quot;true&quot;:
        </p>
        <pre className={styles.cmd}>
          <code>{SPEC.command}</code>
        </pre>
        <p>
          The sealed bundle is uploaded as the run artifact <code>{SPEC.artifact}</code>, next to the job&apos;s logs.
        </p>
      </Block>

      <Block n={5} title="The comment it posts">
        <p>
          This is the comment for the sealed Hopper run, worked out from its bundle the same way{" "}
          <code>noether/comment.py</code> writes it. On each new push the job edits its last comment instead of adding
          another. A live one sits on{" "}
          <a href="https://github.com/omshukla24/hopper/pull/2" rel="noopener">
            omshukla24/hopper#2
          </a>
          .
        </p>
        <Comment />
      </Block>

      <Block n={6} title="When the job fails">
        <table className={plain.table}>
          <thead>
            <tr>
              <th scope="col">Verdict</th>
              <th scope="col">Exit code</th>
              <th scope="col">The job</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(EXIT).map(([verdict, code]) => (
              <tr key={verdict}>
                <td>{verdict}</td>
                <td className={styles.mono}>{code}</td>
                <td>{JOB[verdict] ?? "passes"}</td>
              </tr>
            ))}
            <tr>
              <td>none, no bundle</td>
              <td className={styles.mono}>{EXIT.INCONCLUSIVE}</td>
              <td>
                fails at &quot;{CHECK_STEP}&quot;, because Noether could not read the pull request or could not start (a
                missing key, for one)
              </td>
            </tr>
          </tbody>
        </table>
        <p>
          Only a BROKEN verdict gates the pull request. To block merging on it, make the <code>check</code> job a required
          status check in the branch protection rules.
        </p>
      </Block>

      <Block n={7} title="What one run may spend">
        <ul>
          <li>At most {cap("max_invariants")} pinned checks in the first round; any more are dropped as they are pinned.</li>
          <li>
            When that round finds no silent break, a second round aimed at the changed lines pins at most{" "}
            {cap("max_probes")} more.
          </li>
          <li>{cap("max_run_tokens")} model tokens.</li>
          <li>{cap("max_sandbox_seconds")} seconds of sandbox time.</li>
          <li>A fix for each of the first {cap("max_fixes")} silent breaks.</li>
        </ul>
        <p>
          A run that reaches the token or sandbox cap ends INCONCLUSIVE with the reason, and its bundle is still sealed.
          The sealed Hopper run used {RUN_TOKENS.toLocaleString("en-US")} tokens and {Math.round(RUN.sandbox.seconds)}{" "}
          seconds of sandbox time, an estimated ${RUN.cost_est_usd.toFixed(4)}. Every comment prints its own estimate.
        </p>
      </Block>

      <Block n={8} title="From a terminal">
        <p>
          The same check without CI. Install the package from{" "}
          <a href={REPO_URL} rel="noopener">
            the repository
          </a>
          , put <code>NEBIUS_API_KEY</code> and <code>NEBIUS_PROJECT_ID</code> in the environment or in a{" "}
          <code>.env.local</code> (found upwards from the current folder), and pass a pull request URL. Set{" "}
          <code>GITHUB_TOKEN</code> as well for higher GitHub rate limits.
        </p>
        <pre className={styles.cmd}>
          <code>
            pip install git+{REPO_URL}
            {"\n"}python -m noether check --pr https://github.com/owner/repo/pull/12
          </code>
        </pre>
        <p>
          It prints each stage as it runs, then the verdict, the reason, the bundle path and its sha256, and exits with the
          code in the table above. <code>--json</code> prints the bundle instead, and <code>--no-fix</code> skips the fix
          stage. Or paste a pull request into <Link href="/check">the cockpit</Link>.
        </p>
      </Block>
    </PlainPage>
  );
}

function Comment() {
  const c = COMMENT;
  return (
    <article className={styles.comment} aria-label="Noether comment on a pull request">
      <header className={styles.commentHead}>
        <span className="label">github-actions commented</span>
        <span className={styles[c.verdict.toLowerCase()]}>{c.verdict}</span>
      </header>
      <div className={styles.commentBody}>
        <h3>Noether: {c.headline}</h3>
        {c.reason && <blockquote>{c.reason}</blockquote>}
        <p>
          Pinned {c.pinned} invariants on base: {c.held} held on head, {c.intended.length} changed as announced, {c.silent}{" "}
          broke silently.
        </p>
        {c.breaks.length > 0 && (
          <table className={styles.breaks}>
            <thead>
              <tr>
                <th scope="col">Silent break</th>
                <th scope="col">Changed line</th>
                <th scope="col">Why</th>
                <th scope="col">Fix</th>
              </tr>
            </thead>
            <tbody>
              {c.breaks.map((b) => (
                <tr key={b.invariant}>
                  <td>{b.invariant}</td>
                  <td>{b.where ? <code>{b.where}</code> : "unlocated"}</td>
                  <td>{b.why}</td>
                  <td>{b.fix}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {c.breaks
          .filter((b) => b.diff)
          .map((b) => (
            <details key={b.invariant} className={styles.fix}>
              <summary>Re-proved fix for {b.invariant}</summary>
              <pre tabIndex={0} aria-label={`Fix diff for ${b.invariant}`}>
                {b.diff!.split("\n").map((line, i) => (
                  <span key={i} className={line.startsWith("+") ? styles.add : line.startsWith("-") ? styles.del : undefined}>
                    {line || " "}
                    {"\n"}
                  </span>
                ))}
              </pre>
            </details>
          ))}
        {c.intended.length > 0 && <p>Announced changes Noether saw happen: {c.intended.join("; ")}.</p>}
        {c.suite && <p>The repo&apos;s own suite {c.suite} on head.</p>}
        <p className={styles.tail}>
          Seal <code>{c.seal}</code> · <Link href="/runs/hopper">proof bundle</Link> · est. ${c.cost}
        </p>
      </div>
    </article>
  );
}
