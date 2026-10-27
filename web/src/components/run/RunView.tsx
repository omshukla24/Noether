import type { Bundle, BundleInvariant, StageEvent, SuiteSummary } from "@/lib/bundle";
import { formatInt, formatSeconds, shortId, tokensByModel } from "@/lib/run";
import { SealCheck } from "./SealCheck";
import styles from "./Run.module.css";

const TONE = { CONSERVED: styles.toneConserved, BROKEN: styles.toneBroken, INCONCLUSIVE: styles.toneUnknown } as const;

const INDEX = [
  ["verdict", "Verdict"],
  ["intent", "Intent"],
  ["invariants", "Pinned checks"],
  ["breaks", "Breaks and fix"],
  ["suite", "The repo's own suite"],
  ["sandbox", "Sandbox"],
  ["models", "Models"],
  ["timeline", "Timeline"],
] as const;

function Section({ id, n, title, children }: { id: string; n: number; title: string; children: React.ReactNode }) {
  return (
    <section id={id} className={styles.section} aria-labelledby={`${id}-h`}>
      <header className={styles.sectionHead}>
        <span className={styles.sectionIdx}>{String(n).padStart(2, "0")}</span>
        <h2 id={`${id}-h`}>{title}</h2>
      </header>
      {children}
    </section>
  );
}

const KIND_CLASS = { held: styles.kHeld, intended: styles.kIntended, silent: styles.kSilent, dropped: styles.kDropped } as const;

function Invariant({ inv }: { inv: BundleInvariant }) {
  return (
    <li className={styles.inv}>
      <details>
        <summary>
          <span className={`${styles.kind} ${KIND_CLASS[inv.kind]}`}>{inv.kind}</span>
          <span className={styles.invName}>{inv.name}</span>
          <span className={styles.invResult}>
            base {inv.base} · head {inv.head ?? "not run"}
          </span>
        </summary>
        <div className={styles.invBody}>
          <p className={styles.claim}>{inv.claim}</p>
          <p className={styles.where}>
            {inv.target_file} · {inv.target_symbol}
          </p>
          <pre className={styles.code} tabIndex={0}>{inv.test_code}</pre>
          {inv.output ? (
            <>
              <p className="label">Output</p>
              <pre className={styles.code} tabIndex={0}>{inv.output}</pre>
            </>
          ) : null}
        </div>
      </details>
    </li>
  );
}

function Diff({ diff }: { diff: string }) {
  return (
    <pre className={styles.diff} tabIndex={0}>
      {diff.split("\n").map((line, i) => (
        <span key={i} className={line.startsWith("+") && !line.startsWith("+++") ? styles.add : line.startsWith("-") && !line.startsWith("---") ? styles.del : undefined}>
          {line}
          {"\n"}
        </span>
      ))}
    </pre>
  );
}

function Suite({ label, s }: { label: string; s: SuiteSummary | null }) {
  return (
    <div className={styles.suiteCell}>
      <span className="label">{label}</span>
      <p className={`${styles.big} tabular`}>{s?.ran ? `${s.passed} passed` : "no suite"}</p>
      <p className={styles.where}>{s?.ran ? `${s.failed} failed · exit ${s.exit_code}` : "the repo has no test script"}</p>
    </div>
  );
}

function summarize(e: StageEvent): string {
  const d = e.data;
  const pick = (k: string) => (Array.isArray(d[k]) ? `${(d[k] as unknown[]).length} ${k}` : typeof d[k] === "string" || typeof d[k] === "number" ? `${d[k]}` : "");
  return [pick("name"), pick("kind"), pick("kept"), pick("pinned"), pick("flips"), pick("silent"), pick("proved"), pick("message"), pick("verdict")].filter(Boolean).join(" · ").slice(0, 120);
}

export function RunView({ bundle }: { bundle: Bundle }) {
  const models = tokensByModel(bundle);
  const prUrl = bundle.pr.url;
  return (
    <div className={styles.page} data-route="run" data-label="Run" data-theme="light">
      <header className={styles.top}>
        <p className="label">
          Sealed run · {bundle.repo} · {shortId(bundle.run_id)}
        </p>
        <h1 className={`${styles.verdictWord} ${TONE[bundle.verdict]}`}>{bundle.verdict}</h1>
        <p className={styles.reason}>{bundle.reason}</p>
        <p className={styles.prTitle}>
          {prUrl ? <a href={prUrl} rel="noopener noreferrer">{bundle.pr.title}</a> : bundle.pr.title}
        </p>
        <p className={`${styles.refs} tabular`}>
          base {bundle.base.ref} {bundle.base.sha.slice(0, 12)} → head {bundle.head.ref} {bundle.head.sha.slice(0, 12)}
        </p>
      </header>

      <SealCheck bundle={bundle} />

      <div className={styles.layout}>
        <nav className={styles.index} aria-label="On this page">
          <ol>
            {INDEX.map(([id, label], i) => (
              <li key={id}>
                <a href={`#${id}`}>
                  <span>{String(i + 1).padStart(2, "0")}</span> {label}
                </a>
              </li>
            ))}
          </ol>
        </nav>

        <div className={styles.content}>
          <Section id="verdict" n={1} title="Verdict">
            <p>{bundle.reason}</p>
            <dl className={styles.facts}>
              <div><dt>Pinned</dt><dd className="tabular">{bundle.invariants.length}</dd></div>
              <div><dt>Held</dt><dd className="tabular">{bundle.invariants.filter((i) => i.kind === "held").length}</dd></div>
              <div><dt>Intended</dt><dd className="tabular">{bundle.invariants.filter((i) => i.kind === "intended").length}</dd></div>
              <div className={bundle.breaks.length ? styles.factBroken : undefined}><dt>Silent</dt><dd className="tabular">{bundle.breaks.length}</dd></div>
              <div><dt>Dropped</dt><dd className="tabular">{bundle.dropped.length}</dd></div>
            </dl>
          </Section>

          <Section id="intent" n={2} title="Intent">
            {bundle.intent ? (
              <>
                <p>{bundle.intent.summary}</p>
                {bundle.intent.intended_changes.length ? (
                  <ul className={styles.list}>
                    {bundle.intent.intended_changes.map((c) => <li key={c}>{c}</li>)}
                  </ul>
                ) : null}
                {bundle.intent.dependency_bumps.map((b) => (
                  <p key={b.name} className={styles.where}>{b.name} {b.old} → {b.new}{b.notes.length ? ` · ${b.notes.join(" ")}` : ""}</p>
                ))}
              </>
            ) : (
              <p className={styles.muted}>The change could not be read, so no intent was recorded.</p>
            )}
          </Section>

          <Section id="invariants" n={3} title="Pinned checks">
            {bundle.invariants.length ? (
              <ul className={styles.invList}>{bundle.invariants.map((inv) => <Invariant key={inv.name} inv={inv} />)}</ul>
            ) : (
              <p className={styles.muted}>No check survived being green twice on the base.</p>
            )}
            {bundle.dropped.length ? (
              <>
                <h3 className={styles.sub}>Dropped checks</h3>
                <ul className={styles.dropped}>
                  {bundle.dropped.map((d) => (
                    <li key={d.name + d.reason}>
                      <span className={styles.invName}>{d.name}</span>
                      <span className={styles.muted}>{d.reason}</span>
                    </li>
                  ))}
                </ul>
              </>
            ) : null}
          </Section>

          <Section id="breaks" n={4} title="Breaks and fix">
            {bundle.breaks.length ? (
              bundle.breaks.map((b) => (
                <article key={b.invariant} className={styles.brk}>
                  <p className={styles.brkWhere}>{b.file}{b.line ? `:${b.line}` : ""}</p>
                  {b.code ? <pre className={styles.code} tabIndex={0}>{b.code}</pre> : null}
                  <p>{b.why}</p>
                  {b.fix ? (
                    <>
                      <p className="label">Proposed fix · {b.fix.proved ? "proved: the broken check is green again and nothing else broke" : "not proved"}</p>
                      <Diff diff={b.fix.diff} />
                    </>
                  ) : (
                    <p className={styles.muted}>No fix was proved for this break.</p>
                  )}
                </article>
              ))
            ) : (
              <p className={styles.muted}>No silent break. Every flip, if any, was something the pull request announced.</p>
            )}
          </Section>

          <Section id="suite" n={5} title="The repo's own suite">
            <div className={styles.suite}>
              <Suite label="Base" s={bundle.own_suite.base} />
              <Suite label="Head" s={bundle.own_suite.head} />
            </div>
            <p className={styles.muted}>The suite passing says nothing about the behaviour nobody tested. That gap is what the pinned checks cover.</p>
          </Section>

          <Section id="sandbox" n={6} title="Sandbox">
            <table className={styles.table}>
              <thead><tr><th scope="col">Snapshot</th><th scope="col">Image id</th></tr></thead>
              <tbody>
                {bundle.sandbox.snapshots.map((s) => (
                  <tr key={s.image}><td>{s.label}</td><td className={styles.mono}>{s.image}</td></tr>
                ))}
              </tbody>
            </table>
            <p className={`${styles.where} tabular`}>{bundle.sandbox.seconds.toFixed(1)} s of sandbox time</p>
          </Section>

          <Section id="models" n={7} title="Models">
            <table className={styles.table}>
              <thead>
                <tr><th scope="col">Model</th><th scope="col">Role</th><th scope="col" className={styles.num}>Calls</th><th scope="col" className={styles.num}>In</th><th scope="col" className={styles.num}>Out</th><th scope="col" className={styles.num}>Time</th></tr>
              </thead>
              <tbody>
                {models.map((m) => (
                  <tr key={m.model}>
                    <td className={styles.mono}>{m.model}</td>
                    <td>{m.roles.join(", ")}</td>
                    <td className={`${styles.num} tabular`}>{m.calls}</td>
                    <td className={`${styles.num} tabular`}>{formatInt(m.tokensIn)}</td>
                    <td className={`${styles.num} tabular`}>{formatInt(m.tokensOut)}</td>
                    <td className={`${styles.num} tabular`}>{formatSeconds(m.ms)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className={`${styles.where} tabular`}>Cost estimate ${bundle.cost_est_usd.toFixed(3)} at list prices; an estimate, not an invoice.</p>
          </Section>

          <Section id="timeline" n={8} title="Timeline">
            <details className={styles.timeline}>
              <summary>{bundle.timeline.length} events · {formatSeconds(bundle.timeline.at(-1)?.t_ms ?? 0)}</summary>
              <ol>
                {bundle.timeline.map((e, i) => (
                  <li key={i} data-type={e.type}>
                    <span className="tabular">{(e.t_ms / 1000).toFixed(1).padStart(5, " ")}s</span>
                    <span>{e.stage}</span>
                    <span>{e.type}</span>
                    <span className={styles.muted}>{summarize(e)}</span>
                  </li>
                ))}
              </ol>
            </details>
          </Section>
        </div>
      </div>
    </div>
  );
}
