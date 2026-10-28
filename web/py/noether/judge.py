"""Judge stage: was each green-to-red flip announced by the pull request?

Fail closed: anything the judge does not clearly call "intended" stays "silent".
"""
from __future__ import annotations

from dataclasses import replace

from noether.model import Change, Flip, Intent
from noether.nemotron import Client, ModelError
from noether.prompt_util import clip

MAX_BODY_CHARS = 4000
MAX_DIFF_CHARS = 24000
MAX_TEST_CHARS = 2500
MAX_OUTPUT_CHARS = 1500
MAX_REASON_CHARS = 400

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    # worked out before the label, so the label follows from applying the rule, not from its wording
                    "rule_gives": {"type": "string"},
                    "head_gives": {"type": "string"},
                    "kind": {"type": "string", "enum": ["intended", "silent", "unsure"]},
                    "reason": {"type": "string"},
                },
                "required": ["name", "rule_gives", "head_gives", "kind", "reason"],
            },
        }
    },
    "required": ["verdicts"],
}

SYSTEM = """You review a pull request. Each flip below is a test that passed on the BASE code and fails on the HEAD code of the pull request. Decide for every flip:
- "intended": the pull request text (title, body, stated intent) or the diff itself clearly announces this exact behaviour change. A stated rule announces every input it applies to, not only its examples: when HEAD's new result is exactly what the announced rule gives for this input, the flip is intended. Read a rule the way its examples read it: when its wording could mean two things, the reading that every example fits is the rule.
- "silent": the behaviour changed but nothing announces it, or it is a side effect of some other change. A result the announced rule does not give, or an input under an exception the text states, is silent. When the text says behaviour stays the same ("no behaviour change", "same output", "results are unchanged", "nothing else changes"), every flip it does not name is silent, whatever the diff or its comments suggest.
- "unsure": you cannot tell from what you were given.

Do not call a flip intended just because the diff touches the same code. The change in behaviour itself must be announced or plainly the point of the diff. When in doubt, say "unsure".
For every flip, before you pick its kind, apply the announced changes to the flip's input step by step:
- "rule_gives": the result the announced changes give for that input, or "no announced change covers this input".
- "head_gives": the result HEAD gave for that input, read from the failure output.
A flip is intended only when both are the same result.
Return {"verdicts": [{"name": ..., "rule_gives": ..., "head_gives": ..., "kind": ..., "reason": ...}]} with one entry per flip, name copied exactly, and a one-sentence reason a reviewer can check."""


def build_judge_messages(intent: Intent, change: Change, flips: list[Flip]) -> list[dict]:
    parts = [f"Pull request title: {change.title or '(none)'}", "Body:", clip(change.body or "(empty)", MAX_BODY_CHARS),
             "", f"Stated intent: {intent.summary}", "Announced behaviour changes:"]
    parts += [f"- {c}" for c in intent.intended_changes] or ["- (none)"]
    parts += ["", "Diff:", clip(change.diff, MAX_DIFF_CHARS), "", "Flips:"]
    for f in flips:
        parts += ["", f"### {f.invariant.name}", f"Claim about BASE: {f.invariant.claim}",
                  f"Test code:\n{clip(f.invariant.test_code, MAX_TEST_CHARS)}",
                  f"Failure output on HEAD:\n{clip(f.head_output, MAX_OUTPUT_CHARS)}"]
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": "\n".join(parts)}]


def judge_flips(client: Client, intent: Intent, change: Change, flips: list[Flip]) -> list[Flip]:
    if not flips:
        return []
    try:
        data = client.chat_json("judge", build_judge_messages(intent, change, flips), JUDGE_SCHEMA)
    except ModelError as e:
        return [replace(f, kind="silent", reason=f"the judge could not be used ({str(e)[:160]}), so this counts as silent")
                for f in flips]
    verdicts = {}
    for v in data["verdicts"]:
        verdicts.setdefault(v["name"], v)  # first answer wins
    out = []
    for f in flips:
        v = verdicts.get(f.invariant.name)
        reason = (v["reason"].strip() if v else "")[:MAX_REASON_CHARS]
        if v is None:
            out.append(replace(f, kind="silent", reason="the judge gave no verdict for this flip, so it counts as silent"))
        elif v["kind"] == "intended":
            out.append(replace(f, kind="intended", reason=reason))
        elif v["kind"] == "unsure":
            out.append(replace(f, kind="silent",
                               reason=f"the judge was unsure ({reason or 'no reason given'}), so it counts as silent"))
        else:
            out.append(replace(f, kind="silent", reason=reason))
    return out
