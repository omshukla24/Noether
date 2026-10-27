"use client";

import Link from "next/link";
import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import type { Bundle } from "@/lib/bundle";
import { describeError, initialState, reduce, replaySteps, type Action } from "@/lib/cockpit";
import { parsePullUrl } from "@/lib/prUrl";
import { streamLiveRun } from "@/lib/runClient";
import { prefersReducedMotion } from "@/motion/env.js";
import { SpectralPlate } from "./SpectralPlate";
import { StageRail } from "./StageRail";
import { VerdictPanel } from "./VerdictPanel";
import styles from "./Check.module.css";

const URL_HINT = "Use the form https://github.com/owner/repo/pull/12 (public repositories only).";

export function CheckCockpit() {
  const [state, dispatch] = useReducer(reduce, initialState);
  const input = useRef<HTMLInputElement>(null);
  const [urlError, setUrlError] = useState("");
  const abort = useRef<AbortController | null>(null);
  const timer = useRef(0);
  const queue = useRef<{ delayMs: number; action: Action }[]>([]);

  const halt = useCallback(() => {
    abort.current?.abort();
    abort.current = null;
    window.clearTimeout(timer.current);
    queue.current = [];
  }, []);

  useEffect(() => {
    const pr = new URLSearchParams(window.location.search).get("pr");
    if (pr && input.current) input.current.value = pr.slice(0, 200);
    return halt;
  }, [halt]);

  const running = state.phase === "running";

  function runLive(event: React.FormEvent) {
    event.preventDefault();
    if (running) return;
    const url = input.current?.value ?? "";
    if (!parsePullUrl(url)) {
      setUrlError(URL_HINT);
      return;
    }
    setUrlError("");
    halt();
    const controller = new AbortController();
    abort.current = controller;
    dispatch({ type: "begin", source: "live" });
    void streamLiveRun(url.trim(), dispatch, controller.signal);
  }

  function pump() {
    const next = queue.current.shift();
    if (!next) return;
    timer.current = window.setTimeout(() => {
      dispatch(next.action);
      pump();
    }, next.delayMs);
  }

  async function replay() {
    halt();
    setUrlError("");
    let bundle: Bundle;
    try {
      const response = await fetch("/runs/hopper.json");
      if (!response.ok) throw new Error(String(response.status));
      bundle = (await response.json()) as Bundle;
    } catch {
      dispatch({ type: "begin", source: "replay" });
      dispatch({ type: "fail", error: describeError("api_unreachable", "") });
      return;
    }
    dispatch({ type: "begin", source: "replay" });
    const steps = replaySteps(bundle);
    if (prefersReducedMotion()) {
      steps.forEach((s) => dispatch(s.action));
      return;
    }
    queue.current = steps;
    pump();
  }

  function skip() {
    window.clearTimeout(timer.current);
    queue.current.splice(0).forEach((s) => dispatch(s.action));
  }

  function stop() {
    halt();
    dispatch({ type: "reset" });
  }

  const replaying = running && state.source === "replay";
  const status = state.phase === "failed" ? state.error?.message : state.verdict ? `Verdict ${state.verdict}` : state.phase === "running" ? "Run in progress" : "";

  return (
    <div className={styles.cockpit}>
      <form className={styles.form} onSubmit={runLive} noValidate>
        <label className={styles.field} htmlFor="pr-url">
          <span className="label">Pull request</span>
          <input
            id="pr-url"
            name="pr"
            type="url"
            inputMode="url"
            autoComplete="off"
            spellCheck={false}
            placeholder="https://github.com/owner/repo/pull/12"
            ref={input}
            disabled={running}
            aria-invalid={urlError ? true : undefined}
            aria-describedby="pr-hint"
            className={styles.input}
          />
        </label>
        {running && state.source === "live" ? (
          <button type="button" className={styles.ghost} onClick={stop}>
            Stop
          </button>
        ) : (
          <button type="submit" className={styles.run} disabled={running}>
            Run
          </button>
        )}
        {replaying ? (
          <button type="button" className={styles.ghost} onClick={skip}>
            Skip to the seal
          </button>
        ) : (
          <button type="button" className={styles.ghost} onClick={() => void replay()} disabled={running}>
            Replay the sealed Hopper run
          </button>
        )}
        <p id="pr-hint" className={urlError ? styles.hintError : styles.hint} role={urlError ? "alert" : undefined}>
          {urlError || "Public repositories only. A live run takes about a minute and is limited per address; the replay is a real run and costs nothing."}
        </p>
      </form>

      {state.phase === "failed" && state.error ? (
        <div className={styles.alert} role="alert">
          <span className="label">Run stopped</span>
          <p>{state.error.message}</p>
        </div>
      ) : null}

      <div className="sr-only" role="status" aria-live="polite">
        {status}
      </div>

      {state.phase === "idle" ? (
        <div className={`${styles.empty} notebook`}>
          <p className={styles.emptyLine}>Nothing exposed yet. Paste a pull request.</p>
          <p className="label">Observe · Pin · Expose · Measure · Judge · Re-prove · Seal</p>
        </div>
      ) : (
        <div className={styles.board}>
          <StageRail rail={state.rail} lastMs={state.lastMs} running={running} />
          <div className={styles.main}>
            <SpectralPlate lines={state.lines} intent={state.intent} />
            <VerdictPanel state={state} />
            {state.phase === "done" && state.runId && state.stored ? (
              <Link
                className={styles.runLink}
                href={state.source === "replay" ? "/runs/hopper" : `/runs/${state.runId}`}
              >
                Open the sealed run
              </Link>
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
}
