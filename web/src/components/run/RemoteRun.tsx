"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { Bundle } from "@/lib/bundle";
import { fetchStoredRun } from "@/lib/runClient";
import { RunView } from "./RunView";
import styles from "./Run.module.css";

type Load = { status: "loading" } | { status: "missing" } | { status: "error" } | { status: "ready"; bundle: Bundle };

// A run the API sealed after the site was built: fetched from the API, then verified like any other.
export function RemoteRun({ id }: { id: string }) {
  const [load, setLoad] = useState<Load>({ status: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    fetchStoredRun(id, controller.signal).then(
      (data) => setLoad(data ? { status: "ready", bundle: data as Bundle } : { status: "missing" }),
      () => !controller.signal.aborted && setLoad({ status: "error" }),
    );
    return () => controller.abort();
  }, [id]);

  if (load.status === "ready") return <RunView bundle={load.bundle} />;
  return (
    <div className={styles.notice} role="status">
      <p className="label">Run · {id}</p>
      <p className={styles.noticeLine}>
        {load.status === "loading" ? "Fetching the sealed run." : load.status === "missing" ? "No run was sealed under that id." : "The stored run could not be read right now."}
      </p>
      {load.status !== "loading" ? <Link href="/check">Check a pull request</Link> : null}
    </div>
  );
}
