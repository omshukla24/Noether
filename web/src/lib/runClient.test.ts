import { afterEach, describe, expect, it, vi } from "vitest";
import type { Action } from "./cockpit";
import { streamLiveRun } from "./runClient";

const stage = { t_ms: 5, stage: "ingest", type: "start", data: {} };
const frame = (event: string, data: unknown) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;

function bodyOf(text: string, chunk = 9): Response {
  const bytes = new TextEncoder().encode(text);
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (let i = 0; i < bytes.length; i += chunk) controller.enqueue(bytes.slice(i, i + chunk));
      controller.close();
    },
  });
  return new Response(stream, { status: 200, headers: { "content-type": "text/event-stream" } });
}

async function run(fetchImpl: () => Promise<Response>): Promise<Action[]> {
  vi.stubGlobal("fetch", fetchImpl);
  const seen: Action[] = [];
  await streamLiveRun("https://github.com/o/r/pull/1", (a) => seen.push(a), new AbortController().signal);
  return seen;
}

afterEach(() => vi.unstubAllGlobals());

describe("live run client", () => {
  it("relays stage events and the result however the bytes are split", async () => {
    const result = { run_id: "20261027-120751-aaaaaa", verdict: "CONSERVED", reason: "ok", sha256: "ab", stored: true };
    const seen = await run(async () => bodyOf(frame("stage", stage) + ": keepalive\n\n" + frame("result", result)));
    expect(seen.map((a) => a.type)).toEqual(["stage", "result"]);
  });

  it("turns an API refusal into a message with the wait", async () => {
    const seen = await run(async () => new Response(JSON.stringify({ error: { code: "rate_limited", message: "Only 3 live runs per hour.", retry_after: 600 } }), { status: 429 }));
    expect(seen).toHaveLength(1);
    expect(seen[0]).toMatchObject({ type: "fail", error: { code: "rate_limited", message: "Only 3 live runs per hour. Try again in about 10 min." } });
  });

  it("says the API is unreachable when the request fails", async () => {
    const seen = await run(async () => {
      throw new TypeError("Failed to fetch");
    });
    expect(seen[0]).toMatchObject({ type: "fail", error: { code: "api_unreachable" } });
  });

  it("reports a stream that ends before the seal", async () => {
    const seen = await run(async () => bodyOf(frame("stage", stage)));
    expect(seen.at(-1)).toMatchObject({ type: "fail", error: { code: "bad_stream" } });
  });

  it("passes on a fail event from the run, such as the time limit", async () => {
    const seen = await run(async () => bodyOf(frame("fail", { code: "timeout", message: "x" })));
    expect(seen).toEqual([{ type: "fail", error: expect.objectContaining({ code: "timeout", message: expect.stringContaining("270 second") }) }]);
  });
});
