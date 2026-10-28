// The pull request comment the Action posts, worked out from a sealed bundle the way noether/comment.py does
// it. The page draws the parts; commentMarkdown() puts them back together, and its test checks that text
// against comment.py itself, so the drawing cannot drift from what lands on a pull request.
import type { Bundle, Verdict } from "./bundle";

export const MARK = "<!-- noether-verdict -->";

export const HEADLINE: Record<Verdict, string> = {
  CONSERVED: "Conserved: no behaviour changed that the PR did not announce.",
  BROKEN: "Broken: this PR changes behaviour it does not announce.",
  INCONCLUSIVE: "Inconclusive: Noether could not finish the proof.",
};

export type FixState = "re-proved" | "proposed, not proved" | "none";

export interface CommentBreak {
  invariant: string;
  /** `file:line`, or null when the break was not located. */
  where: string | null;
  why: string;
  fix: FixState;
  /** The fix diff, only when it was re-proved. */
  diff: string | null;
}

export interface Comment {
  verdict: Verdict;
  headline: string;
  reason: string;
  pinned: number;
  held: number;
  silent: number;
  breaks: CommentBreak[];
  intended: string[];
  suite: "passed" | "failed" | null;
  seal: string;
  cost: string;
}

const flat = (text: unknown) => String(text ?? "").split(/\s+/).filter(Boolean).join(" ");

export function commentOf(bundle: Bundle): Comment {
  const invariants = bundle.invariants.filter((i) => i.kind !== "dropped");
  const suite = bundle.own_suite?.head;
  return {
    verdict: bundle.verdict,
    headline: HEADLINE[bundle.verdict] ?? bundle.verdict,
    reason: flat(bundle.reason),
    pinned: invariants.length,
    held: invariants.filter((i) => i.kind === "held").length,
    silent: bundle.breaks.length,
    breaks: bundle.breaks.map((b) => ({
      invariant: flat(b.invariant),
      where: b.line ? `${b.file ?? "?"}:${b.line}` : null,
      why: flat(b.why),
      fix: b.fix?.proved ? "re-proved" : b.fix ? "proposed, not proved" : "none",
      diff: b.fix?.proved && b.fix.diff ? b.fix.diff.trimEnd() : null,
    })),
    intended: invariants.filter((i) => i.kind === "intended").map((i) => flat(i.claim)),
    suite: suite?.ran ? (suite.exit_code === 0 ? "passed" : "failed") : null,
    seal: bundle.sha256.slice(0, 16),
    cost: (bundle.cost_est_usd ?? 0).toFixed(4),
  };
}

const cell = (text: string) => text.replace(/\|/g, "\\|");

export function commentMarkdown(c: Comment, bundleUrl = ""): string {
  const lines = [MARK, `### Noether: ${c.headline}`, ""];
  if (c.reason) lines.push(`> ${cell(c.reason)}`, "");
  lines.push(
    `Pinned ${c.pinned} invariants on base: ${c.held} held on head, ${c.intended.length} changed as announced, ` +
      `${c.silent} broke silently.`,
    "",
  );
  if (c.breaks.length) {
    lines.push("| Silent break | Changed line | Why | Fix |", "|---|---|---|---|");
    for (const b of c.breaks) {
      lines.push(`| ${cell(b.invariant)} | ${b.where ? `\`${b.where}\`` : "unlocated"} | ${cell(b.why)} | ${b.fix} |`);
    }
    lines.push("");
    for (const b of c.breaks.filter((x) => x.diff)) {
      lines.push(`<details><summary>Re-proved fix for ${cell(b.invariant)}</summary>`, "", "```diff", b.diff!, "```", "</details>", "");
    }
  }
  if (c.intended.length) lines.push(`Announced changes Noether saw happen: ${c.intended.map(cell).join("; ")}.`, "");
  if (c.suite) lines.push(`The repo's own suite ${c.suite} on head.`, "");
  lines.push(`Seal \`${c.seal}\`${bundleUrl ? ` · [proof bundle](${bundleUrl})` : ""} · est. $${c.cost}`);
  return lines.join("\n") + "\n";
}
