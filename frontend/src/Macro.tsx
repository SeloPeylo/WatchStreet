// The macro view: tracked series by group, one large chart, prices in other denominators.
import { useEffect, useMemo, useState } from "react";
import type { Json } from "./api";
import { day, get, num, post } from "./api";

const RANGES: [string, number][] = [["1 J", 1], ["3 J", 3], ["5 J", 5], ["10 J", 10], ["Max", 0]];
const FREQUENCY: Record<string, string> = { daily: "täglich", weekly: "wöchentlich", monthly: "monatlich" };
const W = 1000;
const H = 320;
const PAD = { left: 8, right: 70, top: 10, bottom: 22 };
const YEAR_MS = 365.25 * 24 * 3600 * 1000;

function Spark({ values }: { values: number[] }) {
  if (values.length < 2) return <svg className="spark" />;
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const path = values.map((v, i) => `${i ? "L" : "M"}${(i / (values.length - 1)) * 100},${28 - ((v - lo) / (hi - lo || 1)) * 26}`).join(" ");
  return <svg className="spark" viewBox="0 0 100 30" preserveAspectRatio="none"><path d={path} fill="none" stroke="var(--accent)" strokeWidth="1.5" vectorEffect="non-scaling-stroke" /></svg>;
}

/** Line chart with value axis, year marks and a crosshair that names day and value. */
function Chart({ points, log, years }: { points: { day: string; value: number }[]; log: boolean; years: number }) {
  const [hover, setHover] = useState<number | null>(null);
  const shown = useMemo(() => {
    if (points.length === 0 || years === 0) return points;
    const from = Date.parse(points[points.length - 1].day) - years * YEAR_MS;
    return points.filter((p) => Date.parse(p.day) >= from);
  }, [points, years]);
  if (shown.length < 2) return <div className="muted small chartempty">Für diesen Zeitraum liegen keine Werte vor.</div>;
  const useLog = log && shown.every((p) => p.value > 0);
  const f = (v: number) => (useLog ? Math.log(v) : v);
  const times = shown.map((p) => Date.parse(p.day));
  const [t0, t1] = [times[0], times[times.length - 1]];
  const lo = Math.min(...shown.map((p) => f(p.value)));
  const hi = Math.max(...shown.map((p) => f(p.value)));
  const x = (t: number) => PAD.left + ((t - t0) / (t1 - t0 || 1)) * (W - PAD.left - PAD.right);
  const y = (v: number) => PAD.top + (1 - (f(v) - lo) / (hi - lo || 1)) * (H - PAD.top - PAD.bottom);
  const path = shown.map((p, i) => `${i ? "L" : "M"}${x(times[i]).toFixed(1)},${y(p.value).toFixed(1)}`).join(" ");
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((share) => (useLog ? Math.exp(lo + share * (hi - lo)) : lo + share * (hi - lo)));
  const firstYear = new Date(t0).getFullYear() + 1;
  const lastYear = new Date(t1).getFullYear();
  const step = Math.max(Math.ceil((lastYear - firstYear + 1) / 10), 1);
  const yearMarks = Array.from({ length: Math.max(lastYear - firstYear + 1, 0) }, (_, i) => firstYear + i).filter((year) => (year - firstYear) % step === 0);
  const move = (e: React.MouseEvent<SVGSVGElement>) => {
    const box = e.currentTarget.getBoundingClientRect();
    const t = t0 + (((e.clientX - box.left) / box.width) * W - PAD.left) / (W - PAD.left - PAD.right) * (t1 - t0);
    let best = 0;
    times.forEach((time, i) => { if (Math.abs(time - t) < Math.abs(times[best] - t)) best = i; });
    setHover(best);
  };
  const at = hover !== null && hover < shown.length ? shown[hover] : shown[shown.length - 1];
  return (
    <div className="chart">
      <div className="small chartread" data-testid="chart-read"><b>{num(at.value)}</b> am {day(at.day)}{hover === null ? " (letzter Wert)" : ""}{useLog ? " · logarithmische Skala" : ""}</div>
      <div className="plot">
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" onMouseMove={move} onMouseLeave={() => setHover(null)} data-testid="chart">
        {ticks.map((tick) => <line key={tick} x1={PAD.left} x2={W - PAD.right} y1={y(tick)} y2={y(tick)} stroke="var(--line)" vectorEffect="non-scaling-stroke" />)}
        {yearMarks.map((year) => <line key={year} x1={x(Date.UTC(year, 0, 1))} x2={x(Date.UTC(year, 0, 1))} y1={PAD.top} y2={H - PAD.bottom} stroke="var(--line)" strokeDasharray="2 4" vectorEffect="non-scaling-stroke" />)}
        <path d={path} fill="none" stroke="var(--accent)" strokeWidth="1.8" vectorEffect="non-scaling-stroke" />
        {hover !== null && <line x1={x(times[hover])} x2={x(times[hover])} y1={PAD.top} y2={H - PAD.bottom} stroke="var(--muted)" vectorEffect="non-scaling-stroke" />}
      </svg>
      <div className="chartaxis">{ticks.map((tick) => <span key={tick} style={{ top: `${(y(tick) / H) * 100}%` }}>{num(tick)}</span>)}</div>
      <div className="chartyears">{yearMarks.map((year) => <span key={year} style={{ left: `${(x(Date.UTC(year, 0, 1)) / W) * 100}%` }}>{year}</span>)}</div>
      </div>
    </div>
  );
}

export function Macro({ notify }: { notify: (text: string) => void }) {
  const [data, setData] = useState<Json | null>(null);
  const [key, setKey] = useState("NETLIQ");
  const [den, setDen] = useState("usd");
  const [years, setYears] = useState(5);
  const [log, setLog] = useState(false);
  const [series, setSeries] = useState<Json | null>(null);
  const load = () => get("/macro").then(setData);
  useEffect(() => { load(); }, []);
  useEffect(() => { get("/macro/chart", { key, den }).then(setSeries); }, [key, den]);
  if (!data) return <div className="page muted">Lade …</div>;
  const empty = data.groups.every((g: Json) => g.items.every((i: Json) => i.value === null));
  const refresh = async () => {
    await post("/macro/refresh");
    notify("Abruf angefordert – der Hintergrunddienst holt die Reihen mit dem nächsten Lauf.");
  };
  return (
    <div className="page macro" data-testid="macro">
      <div className="box">
        <div className="row">
          <h2 style={{ margin: 0 }}>{series?.label ?? "Makro"}</h2>
          <span className="muted small">{series?.unit}</span>
          <span className="right row small">
            {series?.money && (
              <label>Nenner{" "}
                <select data-testid="denominator" value={den} onChange={(e) => setDen(e.target.value)}>
                  {Object.entries(data.denominators).map(([k, label]) => <option key={k} value={k}>{label as string}</option>)}
                </select>
              </label>
            )}
            {RANGES.map(([label, value]) => <button key={label} className={years === value ? "on" : ""} onClick={() => setYears(value)}>{label}</button>)}
            <label><input type="checkbox" checked={log} onChange={() => setLog(!log)} /> Log</label>
          </span>
        </div>
        {series && <Chart points={series.points} log={log} years={years} />}
        {series && (
          <p className="small muted" data-testid="chart-note">
            {series.formula && <>Rechnung: {series.formula}. </>}{series.rule && <>{series.rule} </>}Hinweis: {series.note}. Quelle: {series.money && !series.key.match(/^[A-Z0-9]+$/) ? "Preisverlauf der Anwendung" : "FRED (Federal Reserve Bank of St. Louis)"}{series.denominator !== "usd" ? " und Preisverlauf der Anwendung" : ""}.
          </p>
        )}
        {series?.split?.length > 0 && (
          <table className="small" data-testid="split">
            <thead><tr><th>Zeitraum</th><th>Änderung in Dollar</th><th>davon Goldpreis</th><th>Änderung in Gold gemessen</th></tr></thead>
            <tbody>{series.split.map((s: Json) => (
              <tr key={s.years}><td>{s.years} {s.years === 1 ? "Jahr" : "Jahre"} bis {day(s.to)}</td><td>{num(s.total_pct)} %</td><td>{num(s.denominator_pct)} %</td><td>{num(s.in_denominator_pct)} %</td></tr>
            ))}</tbody>
          </table>
        )}
        {series?.split?.length > 0 && <p className="small muted">Die Zerlegung ist eine Rechnung, keine Aussage über Ursachen: (1 + Änderung in Dollar) = (1 + Goldpreis) × (1 + Änderung in Gold).</p>}
      </div>
      <div className="row small" style={{ margin: "12px 0" }}>
        <span className="muted">{data.synced_at ? `Zuletzt abgerufen ${day(data.synced_at)}` : "Noch nie abgerufen"} · Werte ohne Lückenfüllung; jedes Feld nennt den Tag der Beobachtung.</span>
        <button className="right" onClick={refresh}>Jetzt aktualisieren</button>
      </div>
      {empty && <div className="box muted">Noch keine Makrodaten gespeichert. „Jetzt aktualisieren“ fordert den Abruf an; der Hintergrunddienst muss laufen.</div>}
      {data.groups.map((group: Json) => (
        <div key={group.key} className="macrogroup">
          <h3>{group.label}</h3>
          <div className="tiles">
            {group.items.map((item: Json) => {
              const change = item.value !== null && item.year_ago !== null ? item.value - item.year_ago : null;
              return (
                <button key={item.key} className={`tile ${item.key === key ? "on" : ""}`} data-testid={`tile-${item.key}`} title={`${item.note}${item.formula ? ` · ${item.formula}` : ""}`} onClick={() => { setKey(item.key); if (!item.money) setDen("usd"); }}>
                  <span className="small muted">{item.label}</span>
                  <span className="tilevalue">{item.value === null ? "–" : num(item.value)} <span className="small muted">{item.unit}</span></span>
                  <Spark values={item.spark} />
                  <span className="small muted">{item.day ? `${day(item.day)} · ${FREQUENCY[item.frequency] ?? item.frequency}` : "kein Wert"}{change !== null ? ` · ${change >= 0 ? "+" : ""}${num(change)} in 1 J` : ""}</span>
                </button>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
