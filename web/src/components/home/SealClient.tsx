"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { parsePullUrl } from "@/lib/prUrl";
import styles from "./Seal.module.css";

// The open slot: a pull request URL goes to /check, which reads it and waits for Run.
export function OpenSlot() {
  const router = useRouter();
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (url.trim() && !parsePullUrl(url)) {
      setError("Use the form https://github.com/owner/repo/pull/12 (public repositories only).");
      return;
    }
    router.push(url.trim() ? `/check?pr=${encodeURIComponent(url.trim())}` : "/check");
  }

  return (
    <form className={styles.slot} onSubmit={submit} noValidate>
      <label htmlFor="slot-pr" className="label">
        Pull request
      </label>
      <div className={styles.slotRow}>
        <input
          id="slot-pr"
          type="url"
          inputMode="url"
          autoComplete="off"
          spellCheck={false}
          placeholder="https://github.com/owner/repo/pull/12"
          value={url}
          onChange={(e) => {
            setUrl(e.target.value);
            setError("");
          }}
          aria-invalid={error ? true : undefined}
          aria-describedby="slot-hint"
          className={styles.input}
        />
        <button type="submit" className={styles.go}>
          Expose it
        </button>
      </div>
      <p id="slot-hint" className={error ? styles.hintError : styles.hint} role={error ? "alert" : undefined}>
        {error || "Opens the cockpit with this pull request filled in. Nothing runs until you press Run there."}
      </p>
    </form>
  );
}

export function CopyButton({ text }: { text: string }) {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");
  const timer = useRef(0);
  useEffect(() => () => window.clearTimeout(timer.current), []);

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setState("copied");
    } catch {
      setState("failed");
    }
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setState("idle"), 2200);
  }

  return (
    <>
      <button type="button" className={styles.copy} onClick={() => void copy()}>
        {state === "copied" ? "Copied" : "Copy"}
      </button>
      <span className="sr-only" role="status">
        {state === "copied" ? "Workflow copied to the clipboard" : state === "failed" ? "Copy was blocked; select the text instead" : ""}
      </span>
    </>
  );
}
