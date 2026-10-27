"""Render a sealed bundle as the pull request comment the GitHub Action posts."""
from __future__ import annotations

MARK = "<!-- noether-verdict -->"  # lets the Action edit its own comment instead of stacking new ones

HEADLINE = {
    "CONSERVED": "Conserved: no behaviour changed that the PR did not announce.",
    "BROKEN": "Broken: this PR changes behaviour it does not announce.",
    "INCONCLUSIVE": "Inconclusive: Noether could not finish the proof.",
}


def _cell(text: str) -> str:
    return " ".join(str(text).split()).replace("|", "\\|")


def render_markdown(bundle: dict, bundle_url: str = "") -> str:
    verdict = bundle.get("verdict", "INCONCLUSIVE")
    lines = [MARK, f"### Noether: {HEADLINE.get(verdict, verdict)}", ""]
    if bundle.get("reason"):
        lines += [f"> {_cell(bundle['reason'])}", ""]

    invariants = [i for i in bundle.get("invariants", []) if i.get("kind") != "dropped"]
    held = sum(1 for i in invariants if i.get("kind") == "held")
    intended = [i for i in invariants if i.get("kind") == "intended"]
    lines.append(f"Pinned {len(invariants)} invariants on base: {held} held on head, "
                 f"{len(intended)} changed as announced, {len(bundle.get('breaks', []))} broke silently.")
    lines.append("")

    breaks = bundle.get("breaks", [])
    if breaks:
        lines += ["| Silent break | Changed line | Why | Fix |", "|---|---|---|---|"]
        for b in breaks:
            fix = b.get("fix") or {}
            fix_cell = "re-proved" if fix.get("proved") else ("proposed, not proved" if fix else "none")
            where = f"`{b.get('file', '?')}:{b.get('line', '?')}`" if b.get("line") else "unlocated"
            lines.append(f"| {_cell(b.get('invariant', ''))} | {where} | {_cell(b.get('why', ''))} | {fix_cell} |")
        lines.append("")
        for b in breaks:
            fix = b.get("fix") or {}
            if fix.get("proved") and fix.get("diff"):
                lines += [f"<details><summary>Re-proved fix for {_cell(b.get('invariant', ''))}</summary>",
                          "", "```diff", fix["diff"].rstrip(), "```", "</details>", ""]

    if intended:
        lines.append("Announced changes Noether saw happen: " + "; ".join(_cell(i["claim"]) for i in intended) + ".")
        lines.append("")

    suite = (bundle.get("own_suite") or {}).get("head")
    if suite and suite.get("ran"):
        state = "passed" if suite.get("exit_code") == 0 else "failed"
        lines += [f"The repo's own suite {state} on head.", ""]

    tail = f"Seal `{bundle.get('sha256', '')[:16]}`"
    if bundle_url:
        tail += f" · [proof bundle]({bundle_url})"
    tail += f" · est. ${bundle.get('cost_est_usd', 0):.4f}"
    lines.append(tail)
    return "\n".join(lines) + "\n"
