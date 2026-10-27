import styles from "./Plain.module.css";

interface PlainPageProps {
  kicker: string;
  title: string;
  updated: string;
  lede: string;
  children: React.ReactNode;
}

export function PlainPage({ kicker, title, updated, lede, children }: PlainPageProps) {
  return (
    <article className={styles.page} data-route="plain" data-label={kicker} data-theme="light">
      <p className="label">{kicker}</p>
      <h1 className={styles.title}>{title}</h1>
      <p className={styles.updated}>Last updated {updated}</p>
      <p className={styles.lede}>{lede}</p>
      <div className={styles.body}>{children}</div>
    </article>
  );
}

export function Block({ n, title, children }: { n: number; title: string; children: React.ReactNode }) {
  return (
    <section className={styles.block} aria-labelledby={`b${n}`}>
      <span className={styles.idx}>{String(n).padStart(2, "0")}</span>
      <div>
        <h2 id={`b${n}`}>{title}</h2>
        {children}
      </div>
    </section>
  );
}

export const plain = styles;
