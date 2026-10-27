import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import hopper from "../../public/runs/hopper.json";
import { announcedLines, failureLine, parseDiff, prCounts, prDiff, prFile, sliceAround } from "./story";

describe("parseDiff", () => {
  it("numbers old and new lines from the hunk headers", () => {
    const lines = parseDiff("@@ -3,2 +3,2 @@ ctx\n keep\n-old\n+new\n");
    expect(lines.map((l) => [l.kind, l.oldNo, l.newNo])).toEqual([
      ["hunk", null, null],
      ["ctx", 3, 3],
      ["del", 4, null],
      ["add", null, 4],
    ]);
  });

  it("skips the file header of a fix diff", () => {
    const fix = hopper.breaks[0].fix!.diff;
    const lines = parseDiff(fix);
    expect(lines.filter((l) => l.kind === "add")).toHaveLength(1);
    expect(lines.filter((l) => l.kind === "del")).toHaveLength(1);
  });

  it("counts the pull request's real added and removed lines", () => {
    expect(prCounts).toEqual({ added: prFile.added, removed: prFile.removed });
  });
});

describe("announcedLines", () => {
  const intended = hopper.intent!.intended_changes;
  const marks = announcedLines(prDiff, intended);

  it("marks the two announced constants with their old and new value", () => {
    const notes = [...marks.values()].filter((m) => m).map((m) => m!.change);
    expect(notes).toEqual(["4 → 6", "18 → 22"]);
  });

  it("leaves the friction line that slipped through unmarked", () => {
    const friction = prDiff.findIndex((l) => l.kind === "add" && l.text.includes("const friction"));
    expect(prDiff[friction].newNo).toBe(hopper.breaks[0].line);
    expect(marks.has(friction)).toBe(false);
  });
});

describe("sliceAround and failureLine", () => {
  it("clamps to the file", () => {
    expect(sliceAround("a\nb\nc", 1, 2).map((l) => l.no)).toEqual([1, 2, 3]);
  });

  it("keeps the assertion and drops the stack", () => {
    const silent = hopper.invariants.find((i) => i.kind === "silent")!;
    expect(failureLine(silent.output)).toBe("Expected values to be strictly equal: 0.0985 !== 0.1");
  });
});

describe("the source panel", () => {
  it("shows the head line the judge located, as written in the head build", () => {
    const head = readFileSync("src/hopper/head/physics.js", "utf8");
    const found = hopper.breaks[0];
    const rows = sliceAround(head, found.line, 6);
    expect(rows.find((r) => r.no === found.line)?.text.trim()).toBe(found.code);
    expect(rows).toHaveLength(13);
  });
});
