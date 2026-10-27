import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import type { Bundle } from "./bundle";
import { describeError, initialState, lineCounts, reduce, replaySteps, type Action, type CockpitState } from "./cockpit";
import { parsePullUrl } from "./prUrl";
import { createSseParser } from "./sse";

const hopper = JSON.parse(readFileSync(join(__dirname, "../../public/runs/hopper.json"), "utf8")) as Bundle;

function play(actions: Action[], from: CockpitState = reduce(initialState, { type: "begin", source: "replay" })) {
  return actions.reduce(reduce, from);
}

describe("sse parser", () => {
  it("returns whole messages however the text is chunked", () => {
    const text = 'event: stage\ndata: {"a":1}\n\n: keepalive\n\nevent: result\ndata: {"b":2}\n\n';
    for (const size of [1, 3, 7, text.length]) {
      const parser = createSseParser();
      const got = [];
      for (let i = 0; i < text.length; i += size) got.push(...parser.push(text.slice(i, i + size)));
      expect(got).toEqual([
        { event: "stage", data: '{"a":1}' },
        { event: "result", data: '{"b":2}' },
      ]);
    }
  });

  it("handles CRLF, multi-line data and a default event name", () => {
    const got = createSseParser().push("data: one\r\ndata: two\r\n\r\n");
    expect(got).toEqual([{ event: "message", data: "one\ntwo" }]);
  });

  it("holds an incomplete message back", () => {
    const parser = createSseParser();
    expect(parser.push("event: stage\ndata: {")).toEqual([]);
    expect(parser.push('}\n\n')).toHaveLength(1);
  });
});

describe("pull request url", () => {
  it("accepts a plain pull request and nothing else", () => {
    expect(parsePullUrl(" https://github.com/omshukla24/hopper/pull/7/ ")).toEqual({ owner: "omshukla24", repo: "hopper", number: 7 });
    for (const bad of [
      "http://github.com/o/r/pull/7",
      "https://github.com.evil.io/o/r/pull/7",
      "https://github.com/o/r/pull/7?x=1",
      "https://github.com/o/r/pull/7#files",
      "https://github.com/o/r/pull/0",
      "https://github.com/o/../pull/7",
      "https://user@github.com/o/r/pull/7",
      "",
    ]) {
      expect(parsePullUrl(bad)).toBeNull();
    }
  });
});

describe("cockpit reducer on the sealed Hopper run", () => {
  const all = replaySteps(hopper).map((s) => s.action);
  const stages = all.filter((a) => a.type === "stage");

  it("replays the timeline with its real delays", () => {
    const steps = replaySteps(hopper);
    expect(steps).toHaveLength(hopper.timeline.length + 1);
    expect(steps.reduce((sum, s) => sum + s.delayMs, 0)).toBe(hopper.timeline.at(-1)!.t_ms);
  });

  it("adds one line per pinned check as pin events arrive", () => {
    const pins = hopper.timeline.filter((e) => e.stage === "pin" && e.type === "progress").length;
    expect(play([]).lines).toHaveLength(0);
    const afterPin = play(stages.filter((a) => a.type === "stage" && ["ingest", "intent", "pin"].includes(a.event.stage)));
    expect(afterPin.lines).toHaveLength(pins);
    expect(afterPin.lines.every((l) => l.base === "pending" || l.base === "dropped")).toBe(true);
    expect(afterPin.rail.find((r) => r.key === "pin")?.status).toBe("done");
  });

  it("locks the lines green twice on base, then flips exactly the broken one on head", () => {
    const end = play(all);
    const counts = lineCounts(end.lines);
    const pinned = hopper.invariants.filter((i) => i.base === "pass").length;
    expect(counts.locked).toBe(pinned);
    expect(counts.flips).toBe(hopper.breaks.length);
    const flip = end.lines.find((l) => l.head === "flip")!;
    expect(flip.name).toBe(hopper.breaks[0].invariant);
    expect(flip.kind).toBe("silent");
    expect(flip.location).toEqual({ file: hopper.breaks[0].file, line: hopper.breaks[0].line });
    expect(flip.proved).toBe(true);
    expect(end.lines.filter((l) => l.base === "dropped").length).toBe(hopper.dropped.length);
  });

  it("ends done with the sealed verdict and every rail row done", () => {
    const end = play(all);
    expect(end.phase).toBe("done");
    expect(end.verdict).toBe("BROKEN");
    expect(end.sha256).toBe(hopper.sha256);
    expect(end.rail.map((r) => r.status)).toEqual(Array(7).fill("done"));
    expect(end.intent).toBe(hopper.intent!.summary);
  });

  it("measures each rail row from the events' own times", () => {
    const end = play(all);
    const pin = end.rail.find((r) => r.key === "pin")!;
    const start = hopper.timeline.find((e) => e.stage === "pin" && e.type === "start")!.t_ms;
    const done = hopper.timeline.find((e) => e.stage === "pin" && e.type === "done")!.t_ms;
    expect([pin.startMs, pin.endMs]).toEqual([start, done]);
  });
});

describe("failures", () => {
  it("keeps what was learned and marks the running row as an error", () => {
    const begun = play([
      { type: "stage", event: { t_ms: 10, stage: "ingest", type: "start", data: {} } },
      { type: "stage", event: { t_ms: 30, stage: "ingest", type: "done", data: {} } },
      { type: "stage", event: { t_ms: 40, stage: "intent", type: "start", data: {} } },
    ]);
    const failed = reduce(begun, { type: "fail", error: describeError("timeout", "x") });
    expect(failed.phase).toBe("failed");
    expect(failed.rail[0].status).toBe("error");
    expect(failed.error?.message).toMatch(/270 second/);
  });

  it("explains rate limits with a wait", () => {
    expect(describeError("rate_limited", "Only 3 live runs per hour.", 1500).message).toBe("Only 3 live runs per hour. Try again in about 25 min.");
    expect(describeError("api_unreachable", "").message).toMatch(/could not be reached/);
  });
});
