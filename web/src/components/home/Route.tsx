import { RUN, formatSeconds, tokensByModel, type ModelRow } from "@/lib/run";
import { RouteCount } from "./RouteCount";
import styles from "./Route.module.css";

const JOB: Record<string, string> = {
  intent: "reads the pull request",
  pin: "pins and repairs the checks",
  judge: "judges each flip",
  fix: "locates the line and writes the fix",
};

const PRISM_X = [190, 500, 810];
const CY = 170;
const FAN = [-34, -17, 0, 17, 34];

const shortName = (model: string) => model.match(/nano|super|ultra/i)?.[0].replace(/^./, (c) => c.toUpperCase()) ?? model;
const jobs = (row: ModelRow) => row.roles.map((r) => JOB[r] ?? r).join(", ");
const totalTokens = (row: ModelRow) => row.tokensIn + row.tokensOut;

// Prism side grows with the square root of the tokens the model handled, so area follows the work.
function prismSide(row: ModelRow, max: number) {
  return 64 + 96 * Math.sqrt(totalTokens(row) / max);
}

function Prism({ row, index, side }: { row: ModelRow; index: number; side: number }) {
  const cx = PRISM_X[index];
  const h = side * 0.866;
  const top = CY - h / 2;
  const bottom = CY + h / 2;
  const right = cx + side / 4;
  const left = cx - side / 4;
  const name = shortName(row.model);
  const last = index === PRISM_X.length - 1;
  return (
    <g className={styles.prism} data-k={index} tabIndex={0} role="img" aria-label={`${name}: ${jobs(row)}. ${totalTokens(row).toLocaleString("en-US")} tokens in ${row.calls} calls.`}>
      <polygon className={styles.glass} points={`${cx - side / 2},${bottom} ${cx + side / 2},${bottom} ${cx},${top}`} />
      <g className={styles.fan} aria-hidden="true">
        {FAN.map((deg, i) => {
          const len = last ? 150 : 76;
          const rad = (deg * Math.PI) / 180;
          return <line key={deg} className={styles[`s${i + 1}` as "s1"]} x1={right} y1={CY} x2={right + Math.cos(rad) * len} y2={CY + Math.sin(rad) * len} />;
        })}
      </g>
      <line className={styles.beam} x1={left} y1={CY} x2={right} y2={CY} aria-hidden="true" />
      <g className={styles.ruler} aria-hidden="true">
        <line x1={cx - side / 2} y1={bottom + 22} x2={cx + side / 2} y2={bottom + 22} />
        <line x1={cx - side / 2} y1={bottom + 16} x2={cx - side / 2} y2={bottom + 28} />
        <line x1={cx + side / 2} y1={bottom + 16} x2={cx + side / 2} y2={bottom + 28} />
        <text x={cx} y={bottom + 48} textAnchor="middle">
          {totalTokens(row).toLocaleString("en-US")} tokens
        </text>
      </g>
      <text className={styles.name} x={cx} y={top - 38} textAnchor="middle">
        {name}
      </text>
      <text className={styles.tip} x={cx} y={top - 14} textAnchor="middle">
        {jobs(row)}
      </text>
    </g>
  );
}

export function Route() {
  const rows = tokensByModel(RUN);
  const max = Math.max(...rows.map(totalTokens));
  const sides = rows.map((r) => prismSide(r, max));
  const callsTotal = rows.reduce((n, r) => n + r.calls, 0);
  const msTotal = rows.reduce((n, r) => n + r.ms, 0);

  return (
    <section id="route" data-route="route" data-label="07 Route" data-theme="light" className={styles.route} aria-labelledby="route-h">
      <header className={styles.head}>
        <p className="label">07 · Route</p>
        <h2 id="route-h" className={styles.title}>
          Three Nemotron models, <em>three jobs.</em>
        </h2>
        <p className={styles.lede}>
          The smallest reads, the middle one writes the checks, the largest only judges what flipped. Each prism is drawn to the number of tokens that model handled in this run.
        </p>
      </header>

      <svg className={styles.svg} viewBox="0 0 1000 340" role="group" aria-label="One beam passing through three prisms: Nano, Super, Ultra">
        <line className={styles.beam} x1={24} y1={CY} x2={PRISM_X[0] - sides[0] / 4} y2={CY} aria-hidden="true" />
        {rows.slice(0, -1).map((_, i) => (
          <line key={i} className={styles.beam} x1={PRISM_X[i] + sides[i] / 4} y1={CY} x2={PRISM_X[i + 1] - sides[i + 1] / 4} y2={CY} aria-hidden="true" />
        ))}
        {rows.slice(0, 3).map((row, i) => (
          <Prism key={row.model} row={row} index={i} side={sides[i]} />
        ))}
      </svg>

      <table className={styles.table}>
        <caption className="sr-only">Models used in the sealed Hopper run</caption>
        <thead>
          <tr>
            <th scope="col">Model</th>
            <th scope="col">Job</th>
            <th scope="col" className={styles.num}>Calls</th>
            <th scope="col" className={styles.num}>Tokens in</th>
            <th scope="col" className={styles.num}>Tokens out</th>
            <th scope="col" className={styles.num}>Time</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={row.model} className={styles.row} data-k={i}>
              <th scope="row" className={styles.model}>
                <span className={styles.short}>{shortName(row.model)}</span>
                <span className={styles.id}>{row.model}</span>
              </th>
              <td>{jobs(row)}</td>
              <td className={styles.num} data-l="Calls "><RouteCount value={row.calls} /></td>
              <td className={styles.num} data-l="In "><RouteCount value={row.tokensIn} /></td>
              <td className={styles.num} data-l="Out "><RouteCount value={row.tokensOut} /></td>
              <td className={styles.num} data-l="Time ">{formatSeconds(row.ms)}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <th scope="row" colSpan={2}>This run</th>
            <td className={styles.num}>{callsTotal}</td>
            <td className={styles.num} colSpan={2}>
              <span className={styles.est}>Cost estimate</span> <RouteCount value={RUN.cost_est_usd} decimals={3} prefix="$" />
            </td>
            <td className={styles.num}>{formatSeconds(msTotal)}</td>
          </tr>
        </tfoot>
      </table>
      <p className={styles.note}>The cost is an estimate from list prices, not an invoice. Token counts and times are from the sealed run.</p>
    </section>
  );
}
