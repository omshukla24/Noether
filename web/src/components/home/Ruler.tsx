import styles from "./Ruler.module.css";

interface RulerProps {
  /** number of spaces between the end ticks */
  steps: number;
  /** every nth tick is taller and, with `numerals`, labelled */
  major?: number;
  numerals?: boolean;
  /** text of the label for the tick at `index` */
  label?: (index: number) => string;
  className?: string;
}

// A measured scale: hairline ticks along a baseline, like the edge of a photographic plate.
export function Ruler({ steps, major = 5, numerals = false, label = (i) => String(i), className = "" }: RulerProps) {
  const ticks = Array.from({ length: steps + 1 }, (_, i) => i);
  return (
    <div className={`${styles.ruler} ${className}`} aria-hidden="true">
      <svg className={styles.ticks} viewBox={`0 0 ${steps} 10`} preserveAspectRatio="none">
        {ticks.map((i) => (
          <line key={i} x1={i} x2={i} y1={10} y2={i % major === 0 ? 2 : 6} vectorEffect="non-scaling-stroke" />
        ))}
      </svg>
      {numerals &&
        ticks
          .filter((i) => i % major === 0)
          .map((i) => (
            <span key={i} className={styles.numeral} style={{ left: `${(i / steps) * 100}%` }}>
              {label(i)}
            </span>
          ))}
    </div>
  );
}
