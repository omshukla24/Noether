// Starts a live run on the API and relays its Server-Sent Events as cockpit actions.
import type { StageEvent } from "./bundle";
import { describeError, type Action, type ResultPayload } from "./cockpit";
import { createSseParser } from "./sse";

export const API_BASE = (process.env.NEXT_PUBLIC_API_BASE ?? "").replace(/\/$/, "");

type Dispatch = (action: Action) => void;

function parse<T>(text: string): T | null {
  try {
    return JSON.parse(text) as T;
  } catch {
    return null;
  }
}

/** Resolves when the stream ends. Every outcome, including failure, arrives as an action. */
export async function streamLiveRun(pr: string, dispatch: Dispatch, signal: AbortSignal): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api/runs`, {
      method: "POST",
      headers: { "content-type": "application/json", accept: "text/event-stream" },
      body: JSON.stringify({ pr }),
      signal,
    });
  } catch (error) {
    if (signal.aborted) return;
    dispatch({ type: "fail", error: describeError("api_unreachable", String(error)) });
    return;
  }

  if (!response.ok || !response.body) {
    const body = parse<{ error?: { code?: string; message?: string; retry_after?: number } }>(await response.text().catch(() => ""));
    const e = body?.error;
    dispatch({
      type: "fail",
      error: e?.code ? describeError(e.code, e.message ?? "", e.retry_after) : describeError("api_unreachable", `HTTP ${response.status}`),
    });
    return;
  }

  const parser = createSseParser();
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let finished = false;
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      for (const message of parser.push(value)) {
        if (message.event === "stage") {
          const event = parse<StageEvent>(message.data);
          if (event) dispatch({ type: "stage", event });
        } else if (message.event === "result") {
          const payload = parse<ResultPayload>(message.data);
          if (payload) {
            finished = true;
            dispatch({ type: "result", result: payload });
          }
        } else if (message.event === "fail") {
          const e = parse<{ code: string; message: string }>(message.data);
          finished = true;
          dispatch({ type: "fail", error: describeError(e?.code ?? "internal", e?.message ?? "The run failed.") });
        }
      }
    }
  } catch (error) {
    if (signal.aborted) return;
    dispatch({ type: "fail", error: describeError("bad_stream", String(error)) });
    return;
  }
  if (!finished && !signal.aborted) dispatch({ type: "fail", error: describeError("bad_stream", "") });
}

/** The stored copy of a sealed run, for /runs/<id> pages of runs that were not built into the site. */
export async function fetchStoredRun(id: string, signal?: AbortSignal): Promise<unknown | null> {
  const response = await fetch(`${API_BASE}/api/runs/${encodeURIComponent(id)}`, { signal });
  if (response.status === 404 || response.status === 400) return null;
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}
