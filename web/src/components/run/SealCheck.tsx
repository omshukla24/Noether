"use client";

import { useEffect, useRef, useState } from "react";
import { verifySeal, type Bundle } from "@/lib/bundle";
import styles from "./Run.module.css";

type Check = "checking" | "verified" | "mismatch" | "unavailable";

const COPY: Record<Check, { head: string; body: string }> = {
  checking: { head: "Checking the seal", body: "Hashing the bundle in this tab." },
  verified: { head: "Seal verified in your browser", body: "This tab re-hashed the bundle below and got the same sha256 the run was sealed with." },
  mismatch: { head: "Seal does not match", body: "The bundle below hashes to a different sha256 than the one it carries. Do not trust it." },
  unavailable: { head: "Seal could not be checked", body: "This browser has no SubtleCrypto here, so the hash could not be recomputed." },
};

export function SealCheck({ bundle }: { bundle: Bundle }) {
  const [check, setCheck] = useState<Check>("checking");
  const link = useRef<HTMLAnchorElement>(null);

  useEffect(() => {
    let alive = true;
    verifySeal(bundle).then(
      (ok) => alive && setCheck(ok ? "verified" : "mismatch"),
      () => alive && setCheck("unavailable"),
    );
    const url = URL.createObjectURL(new Blob([JSON.stringify(bundle, null, 2)], { type: "application/json" }));
    if (link.current) link.current.href = url;
    return () => {
      alive = false;
      URL.revokeObjectURL(url);
    };
  }, [bundle]);

  return (
    <div className={styles.seal} data-check={check} role="status">
      <span className={styles.sealMark} aria-hidden="true" />
      <div>
        <p className={styles.sealHead}>{COPY[check].head}</p>
        <p className={styles.sealBody}>{COPY[check].body}</p>
        <p className={`${styles.hash} tabular`}>
          <span className="label">sha256</span> {bundle.sha256}
        </p>
        <a ref={link} className={styles.download} download={`noether-${bundle.run_id}.json`}>
          Download JSON
        </a>
      </div>
    </div>
  );
}
