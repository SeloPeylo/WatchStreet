// Charts beyond one line: yardstick matrix, lever chain, lenses (formulas) and the regime map.
import { useEffect, useMemo, useState } from "react";
import type { Json } from "./api";
import { day, del, get, num, post } from "./api";
import { Chart, Spark } from "./Macro";

const TABS: [string, string][] = [["ladder", "Treiberleiter"], ["matrix", "Massstab-Matrix"], ["chain", "Hebelkette"], ["lens", "Linse"], ["regime", "Regimekarte"]];
const YEARS: [string, number][] = [["1 J", 1], ["3 J", 3], ["5 J", 5], ["10 J", 10]];
const LINK_COLORS = ["var(--warn)", "var(--accent)", "var(--ok)", "var(--demo)", "var(--bad)"];
const signed = (value: number | null | undefined, unit = " %") => (value == null ? "–" : `${value >= 0 ? "+" : ""}${num(value)}${unit}`);

function Years({ value, set, options = YEARS }: { value: number; set: (v: number) => void; options?: [string, number][] }) {
  return <>{options.map(([label, v]) => <button key={label} className={value === v ? "on" : ""} onClick={() => set(v)}>{label}</button>)}</>;
}

function SeriesSelect({ series, value, set, filter, testid }: { series: Json[]; value: string; set: (v: string) => void; filter?: (s: Json) => boolean; testid: string }) {
  const shown = filter ? series.filter(filter) : series;
  return (
    <select data-testid={testid} value={value} onChange={(e) => set(e.target.value)}>
      <optgroup label="Aktien">{shown.filter((s) => s.share).map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}</optgroup>
      <optgroup label="Reihen">{shown.filter((s) => !s.share).map((s) => <option key={s.key} value={s.key}>{s.label} [{s.key}]</option>)}</optgroup>
    </select>
  );
}

// ---------------------------------------------------------------- yardstick matrix
function Matrix({ openChain }: { openChain: (key: string) => void }) {
  const [data, setData] = useState<Json | null>(null);
  const [open, setOpen] = useState<[string, string] | null>(null);
  useEffect(() => { get("/charts/matrix").then(setData); }, []);
  if (!data) return <div className="muted">Lade …</div>;
  const row = open && data.rows.find((r: Json) => r.key === open[0]);
  const cell = row && row.cells[open![1]];
  const yardstick = open && data.yardsticks.find((y: Json) => y.key === open[1]);
  return (
    <div data-testid="matrix">
      <p className="small muted">Zeilen: was du hältst oder beobachtest. Spalten: der Massstab. Jede Zelle zeigt den Verlauf über bis zu {data.years} Jahre, die Änderung über ein Jahr und – als Strich – wo der heutige Wert in der eigenen Spanne liegt (links tief, rechts hoch).</p>
      <div className="box" style={{ overflowX: "auto" }}>
        <table className="matrix">
          <thead><tr><th></th>{data.yardsticks.map((y: Json) => <th key={y.key} title={y.rule}>in {y.label}</th>)}</tr></thead>
          <tbody>{data.rows.map((r: Json) => (
            <tr key={r.key}>
              <th><button className="link" title="Hebelkette öffnen" onClick={() => openChain(r.key)}>{r.label}</button>{r.held && <span className="pill small"> im Depot</span>}</th>
              {data.yardsticks.map((y: Json) => {
                const c = r.cells[y.key];
                if (c.state === "identity") return <td key={y.key} className="muted small">= 1 (der Massstab selbst)</td>;
                if (c.state !== "ok") return <td key={y.key} className="muted small">zu wenige gemeinsame Werte ({c.n})</td>;
                return (
                  <td key={y.key}>
                    <button className={`cell ${open && open[0] === r.key && open[1] === y.key ? "on" : ""}`} data-testid={`cell-${r.key}-${y.key}`} onClick={() => setOpen([r.key, y.key])}>
                      <Spark values={c.points.map((p: Json) => p.value)} />
                      <span className={c.change_1y_pct == null ? "muted" : c.change_1y_pct >= 0 ? "up" : "down"}>{signed(c.change_1y_pct)}</span>
                      <span className="range" title="Lage des heutigen Werts in der eigenen Spanne">{c.position != null && <i style={{ left: `${c.position * 100}%` }} />}</span>
                    </button>
                  </td>
                );
              })}
            </tr>
          ))}</tbody>
        </table>
      </div>
      <p className="small muted">{data.note}</p>
      {cell?.state === "ok" && (
        <div className="box" data-testid="matrix-detail">
          <div className="row"><h2 style={{ margin: 0 }}>{row.label} in {yardstick.label}</h2><span className="muted small">{yardstick.rule} · {day(cell.from)} bis {day(cell.to)} · {cell.n} Werte</span></div>
          <Chart points={cell.points} log={false} years={0} />
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- lever chain
function Chain({ series, subject, setSubject }: { series: Json[]; subject: string; setSubject: (v: string) => void }) {
  const [years, setYears] = useState(1);
  const [data, setData] = useState<Json | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!subject) return;
    get("/charts/chain", { key: subject, years: String(years) }).then((d) => { setData(d); setError(""); }).catch((e) => { setData(null); setError(e.message); });
  }, [subject, years]);
  const bars = useMemo(() => {
    if (!data) return null;
    let at = 0;
    const steps = data.links.map((l: Json) => { const from = at; at += l.log; return { ...l, from, to: at }; });
    const lo = Math.min(0, ...steps.map((s: Json) => Math.min(s.from, s.to)));
    const hi = Math.max(0, ...steps.map((s: Json) => Math.max(s.from, s.to)));
    return { steps, lo, hi, x: (v: number) => ((v - lo) / (hi - lo || 1)) * 100 };
  }, [data]);
  return (
    <div data-testid="chain">
      <div className="row small" style={{ marginBottom: 8 }}>
        <SeriesSelect testid="chain-subject" series={series} value={subject} set={setSubject} filter={(s) => s.money && s.key !== "gold"} />
        <Years value={years} set={setYears} options={YEARS.slice(0, 3)} />
      </div>
      {error && <div className="note" data-testid="chain-error">{error}</div>}
      {data && bars && (
        <>
          <div className="box">
            <h2>{data.label}: {signed(data.total_pct)} in {data.currency}</h2>
            <p className="small muted">{day(data.from)} bis {day(data.to)} · entspricht {signed(data.total_log, "")} Logarithmus-Punkten. Die Balken hängen aneinander und enden bei der Gesamtänderung.</p>
            <div className="waterfall">
              {bars.steps.map((s: Json, i: number) => (
                <div key={s.label} className="wrow" data-testid="chain-link">
                  <span className="wlabel"><i style={{ background: LINK_COLORS[i % LINK_COLORS.length] }} />{s.label}</span>
                  <span className="wbar"><i className="zero" style={{ left: `${bars.x(0)}%` }} /><b style={{ left: `${bars.x(Math.min(s.from, s.to))}%`, width: `${Math.abs(bars.x(s.to) - bars.x(s.from))}%`, background: LINK_COLORS[i % LINK_COLORS.length] }} /></span>
                  <span className="wvalue">{signed(s.log, "")} <span className="muted small">({signed(s.pct)})</span></span>
                </div>
              ))}
              <div className="wrow total">
                <span className="wlabel">= Kurs in {data.currency}</span>
                <span className="wbar"><i className="zero" style={{ left: `${bars.x(0)}%` }} /><b style={{ left: `${bars.x(Math.min(0, data.total_log))}%`, width: `${Math.abs(bars.x(data.total_log) - bars.x(0))}%`, background: "var(--text)" }} /></span>
                <span className="wvalue" data-testid="chain-total">{signed(data.total_log, "")} <span className="muted small">({signed(data.total_pct)})</span></span>
              </div>
            </div>
            <p className="small muted">{data.note}</p>
          </div>
          <div className="box">
            <h3>Wann kam welcher Beitrag?</h3>
            <Lines path={data.path} labels={data.links.map((l: Json) => l.label)} />
          </div>
        </>
      )}
    </div>
  );
}

/** Cumulative contribution of every link over time (log points), one line per link. */
function Lines({ path, labels }: { path: Json[]; labels: string[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const W = 1000, H = 260, R = 60;
  const all = path.flatMap((p) => p.values as number[]);
  const lo = Math.min(0, ...all), hi = Math.max(0, ...all);
  const x = (i: number) => (i / (path.length - 1 || 1)) * (W - R);
  const y = (v: number) => 8 + (1 - (v - lo) / (hi - lo || 1)) * (H - 16);
  const at = path[hover ?? path.length - 1];
  return (
    <>
      <div className="small chartread"><b>{day(at.day)}</b>{labels.map((label, i) => <span key={label} style={{ marginLeft: 10 }}><i className="dot" style={{ background: LINK_COLORS[i % LINK_COLORS.length] }} />{label}: {signed(at.values[i], "")}</span>)}</div>
      <svg className="lines" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" onMouseLeave={() => setHover(null)}
        onMouseMove={(e) => { const box = e.currentTarget.getBoundingClientRect(); setHover(Math.max(0, Math.min(path.length - 1, Math.round((((e.clientX - box.left) / box.width) * W) / (W - R) * (path.length - 1))))); }}>
        <line x1={0} x2={W - R} y1={y(0)} y2={y(0)} stroke="var(--muted)" vectorEffect="non-scaling-stroke" />
        {labels.map((label, i) => <path key={label} fill="none" stroke={LINK_COLORS[i % LINK_COLORS.length]} strokeWidth="1.8" vectorEffect="non-scaling-stroke" d={path.map((p, j) => `${j ? "L" : "M"}${x(j).toFixed(1)},${y(p.values[i]).toFixed(1)}`).join(" ")} />)}
        {hover !== null && <line x1={x(hover)} x2={x(hover)} y1={0} y2={H} stroke="var(--muted)" vectorEffect="non-scaling-stroke" />}
      </svg>
      <div className="small muted">{day(path[0].day)} bis {day(path[path.length - 1].day)} · Logarithmus-Punkte seit Beginn; die Linien addieren sich an jedem Tag zur Kursänderung.</div>
    </>
  );
}

// ---------------------------------------------------------------- lens
const EXAMPLES: [string, string][] = [["in Gold", "$objekt / gold"], ["in Kupfer, geglättet", "ma($objekt / copper, 4)"], ["Jahresrate", "yoy($objekt)"], ["Kupfer ÷ Gold", "copper / gold"], ["Zinskurve", "DGS10 - DGS2"]];

function Lens({ series, subject, setSubject }: { series: Json[]; subject: string; setSubject: (v: string) => void }) {
  const [text, setText] = useState("$objekt / gold");
  const [run, setRun] = useState("$objekt / gold");
  const [data, setData] = useState<Json | null>(null);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState<Json[]>([]);
  const [name, setName] = useState("");
  const [years, setYears] = useState(3);
  const [log, setLog] = useState(false);
  const loadSaved = () => get("/charts/lenses").then(setSaved);
  useEffect(() => { loadSaved(); }, []);
  useEffect(() => {
    post("/charts/lens", { expression: run, subject }).then((d) => { setData(d); setError(""); }).catch((e) => { setData(null); setError(e.message); });
  }, [run, subject]);
  const apply = (expression: string) => { setText(expression); setRun(expression); };
  const save = () => post("/charts/lenses", { name, expression: text }).then(() => { setName(""); loadSaved(); }).catch((e) => setError(e.message));
  return (
    <div data-testid="lens">
      <p className="small muted">Eine Linse ist eine gespeicherte Formel. <code>$objekt</code> steht für das gewählte Objekt, sodass dieselbe Linse auf jede Aktie und jeden Preis passt. Erlaubt: <code>+ − * /</code>, Klammern, Reihenschlüssel (in eckigen Klammern in der Auswahl) und <code>ma(x, n)</code> Mittel über n Werte, <code>lag(x, n)</code>, <code>chg(x, n)</code> Änderung in % gegen n Werte zuvor, <code>yoy(x)</code>, <code>log(x)</code>.</p>
      <form className="row" onSubmit={(e) => { e.preventDefault(); setRun(text); }}>
        <label className="small">Objekt <SeriesSelect testid="lens-subject" series={series} value={subject} set={setSubject} filter={(s) => s.money} /></label>
        <input data-testid="lens-input" className="grow" style={{ fontFamily: "ui-monospace, monospace" }} value={text} onChange={(e) => setText(e.target.value)} spellCheck={false} />
        <button className="primary" type="submit" data-testid="lens-run">Anwenden</button>
      </form>
      <div className="row small" style={{ margin: "8px 0" }}>
        <span className="muted">Beispiele:</span>
        {EXAMPLES.map(([label, expression]) => <button key={label} onClick={() => apply(expression)}>{label}</button>)}
        {saved.length > 0 && <span className="muted">Gespeichert:</span>}
        {saved.map((l) => (
          <span key={l.id} className="row" style={{ gap: 0 }}>
            <button className={l.expression === run ? "on" : ""} title={l.expression} data-testid={`saved-${l.name}`} onClick={() => apply(l.expression)}>{l.name}</button>
            <button title="Linse löschen" onClick={() => del(`/charts/lenses/${l.id}`).then(loadSaved)}>×</button>
          </span>
        ))}
      </div>
      {error && <div className="note" data-testid="lens-error">{error}</div>}
      {data && (
        <div className="box">
          <div className="row">
            <h2 style={{ margin: 0 }}><code>{data.expression}</code></h2>
            <span className="muted small" data-testid="lens-unit">Einheit: {data.unit}</span>
            <span className="right row small"><Years value={years} set={setYears} options={[...YEARS, ["Max", 0]]} /><label><input type="checkbox" checked={log} onChange={() => setLog(!log)} /> Log</label></span>
          </div>
          <Chart points={data.points} log={log} years={years} />
          <div className="row small" data-testid="lens-terms">
            {data.terms.map((t: Json) => <span key={t.name} className="pill" title={`letzter Wert ${day(t.last_day)}`}><b>{t.name}</b> = {t.label} · {t.unit} · {{ daily: "täglich", weekly: "wöchentlich", monthly: "monatlich" }[t.frequency as string] ?? t.frequency}</span>)}
          </div>
          <p className="small muted">{data.dropped > 0 && <>{data.dropped} Beobachtungen der längsten Reihe haben keinen gemeinsamen Tag und fehlen im Ergebnis. </>}{data.note}</p>
          <div className="row small">
            <input placeholder="Name der Linse" data-testid="lens-name" value={name} onChange={(e) => setName(e.target.value)} />
            <button disabled={!name.trim()} data-testid="lens-save" onClick={save}>Als Linse speichern</button>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- regime map
const DECISION: Record<string, string> = { buy: "Kauf", sell: "Verkauf", adjust: "Anpassung" };

function Regime({ series }: { series: Json[] }) {
  const [xKey, setX] = useState("DFII10");
  const [yKey, setY] = useState("DTWEXBGS");
  const [years, setYears] = useState(5);
  const [data, setData] = useState<Json | null>(null);
  const [error, setError] = useState("");
  const [hover, setHover] = useState<Json | null>(null);
  useEffect(() => {
    get("/charts/regime", { x: xKey, y: yKey, years: String(years) }).then((d) => { setData(d); setError(""); }).catch((e) => { setData(null); setError(e.message); });
  }, [xKey, yKey, years]);
  const W = 1000, H = 520, P = 44;
  const geo = useMemo(() => {
    if (!data) return null;
    const marks = data.decisions.filter((d: Json) => d.in_window);
    const xs = [...data.path, ...marks].map((p: Json) => p.x), ys = [...data.path, ...marks].map((p: Json) => p.y);
    const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
    const x = (v: number) => P + ((v - x0) / (x1 - x0 || 1)) * (W - 2 * P);
    const y = (v: number) => H - P - ((v - y0) / (y1 - y0 || 1)) * (H - 2 * P);
    const years: Json[] = [];
    data.path.forEach((p: Json, i: number) => { if (i === 0 || p.day.slice(0, 4) !== data.path[i - 1].day.slice(0, 4)) years.push(p); });
    return { x, y, x0, x1, y0, y1, marks, years };
  }, [data]);
  const noMoney = (s: Json) => !s.share;
  return (
    <div data-testid="regime">
      <div className="row small" style={{ marginBottom: 8 }}>
        <label>waagrecht <SeriesSelect testid="regime-x" series={series} value={xKey} set={setX} filter={noMoney} /></label>
        <label>senkrecht <SeriesSelect testid="regime-y" series={series} value={yKey} set={setY} filter={noMoney} /></label>
        <Years value={years} set={setYears} />
      </div>
      {error && <div className="note">{error}</div>}
      {data && geo && (
        <div className="box">
          <div className="small chartread" data-testid="regime-read">
            {hover ? <><b>{day(hover.day)}</b>{hover.kind ? ` · ${DECISION[hover.kind] ?? hover.kind} ${hover.symbol}${hover.reason ? ` – ${hover.reason}` : ""}` : ""} · {data.x.label}: {num(hover.x)} · {data.y.label}: {num(hover.y)}</>
              : <>Heute ({day(data.to)}): {data.x.label} {num(data.path[data.path.length - 1].x)} {data.x.unit} · {data.y.label} {num(data.path[data.path.length - 1].y)} {data.y.unit}</>}
          </div>
          <svg className="regime" viewBox={`0 0 ${W} ${H}`} onMouseLeave={() => setHover(null)}>
            <rect x={P} y={P} width={W - 2 * P} height={H - 2 * P} fill="none" stroke="var(--line)" />
            {data.path.slice(1).map((p: Json, i: number) => (
              <line key={p.day} x1={geo.x(data.path[i].x)} y1={geo.y(data.path[i].y)} x2={geo.x(p.x)} y2={geo.y(p.y)} stroke="var(--accent)" strokeWidth="1.6" opacity={0.15 + 0.85 * ((i + 1) / data.path.length)} />
            ))}
            {data.path.map((p: Json) => <circle key={p.day} cx={geo.x(p.x)} cy={geo.y(p.y)} r="7" fill="transparent" onMouseEnter={() => setHover(p)} />)}
            {geo.years.map((p: Json) => <text key={p.day} x={geo.x(p.x) + 6} y={geo.y(p.y) - 6} fontSize="11" fill="var(--muted)">{p.day.slice(0, 4)}</text>)}
            {geo.marks.map((d: Json, i: number) => {
              const [cx, cy] = [geo.x(d.x), geo.y(d.y)];
              const up = d.kind !== "sell";
              const shape = up ? `${cx},${cy - 9} ${cx - 8},${cy + 6} ${cx + 8},${cy + 6}` : `${cx},${cy + 9} ${cx - 8},${cy - 6} ${cx + 8},${cy - 6}`;
              return <polygon key={i} data-testid="regime-decision" points={shape} fill={d.kind === "buy" ? "var(--ok)" : d.kind === "sell" ? "var(--panel)" : "var(--warn)"} stroke={d.kind === "sell" ? "var(--bad)" : "var(--text)"} strokeWidth="1.5" onMouseEnter={() => setHover(d)} />;
            })}
            <circle cx={geo.x(data.path[data.path.length - 1].x)} cy={geo.y(data.path[data.path.length - 1].y)} r="9" fill="none" stroke="var(--text)" strokeWidth="2" />
            <text x={W / 2} y={H - 10} textAnchor="middle" fontSize="11" fill="var(--muted)">{data.x.label} ({data.x.unit}) · {num(geo.x0)} bis {num(geo.x1)}</text>
            <text x={14} y={H / 2} textAnchor="middle" fontSize="11" fill="var(--muted)" transform={`rotate(-90 14 ${H / 2})`}>{data.y.label} ({data.y.unit}) · {num(geo.y0)} bis {num(geo.y1)}</text>
          </svg>
          <p className="small muted">Linie: Weg von {day(data.from)} (blass) bis heute (kräftig, Ring). ▲ grün = Kauf, ▽ = Verkauf, ▲ gelb = Anpassung aus dem Entscheidungsprotokoll{geo.marks.length === 0 ? " – in diesem Zeitraum gibt es keine Einträge" : ""}. {data.note}</p>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- driver ladder
const SPACE = { w: 1000, h: 560 };

/** The path through (driver, value); in space the third axis is time and the view can be turned. */
function Path3({ data, space, angle }: { data: Json; space: boolean; angle: number }) {
  const [hover, setHover] = useState<Json | null>(null);
  const geo = useMemo(() => {
    const pts: Json[] = data.path;
    const span = (get: (p: Json) => number) => { const v = pts.map(get); return [Math.min(...v), Math.max(...v)]; };
    const [x0, x1] = span((p) => p.x), [y0, y1] = span((p) => p.y);
    const t0 = Date.parse(pts[0].day), t1 = Date.parse(pts[pts.length - 1].day);
    const unit = (v: number, lo: number, hi: number) => ((v - lo) / (hi - lo || 1)) * 2 - 1;
    const rad = (angle * Math.PI) / 180;
    // orthographic view: turn around the value axis, then tilt slightly so depth is readable
    const project = (x: number, y: number, z: number): [number, number] => {
      if (!space) return [SPACE.w / 2 + x * 400, SPACE.h / 2 - y * 220];
      const rx = x * Math.cos(rad) + z * Math.sin(rad);
      const rz = -x * Math.sin(rad) + z * Math.cos(rad);
      return [SPACE.w / 2 + rx * 300, SPACE.h / 2 - y * 190 - rz * 60];
    };
    const at = (p: Json) => project(unit(p.x, x0, x1), unit(p.y, y0, y1), unit(Date.parse(p.day), t0, t1));
    const years: Json[] = [];
    pts.forEach((p, i) => { if (i === 0 || p.day.slice(0, 4) !== pts[i - 1].day.slice(0, 4)) years.push(p); });
    const corners = [-1, 1].flatMap((x) => [-1, 1].flatMap((y) => [-1, 1].map((z) => [x, y, z] as [number, number, number])));
    const edges = corners.flatMap((a, i) => corners.slice(i + 1).filter((b) => a.filter((v, k) => v !== b[k]).length === 1).map((b) => [project(...a), project(...b)]));
    return { at, years, edges, project, x0, x1, y0, y1 };
  }, [data, space, angle]);
  const pts: Json[] = data.path;
  const last = pts[pts.length - 1];
  const shown = hover ?? last;
  return (
    <>
      <div className="small chartread" data-testid="ladder-read"><b>{day(shown.day)}</b>{hover ? "" : " (letzter Wert)"} · {data.driver.label}: {num(shown.x)} {data.driver.unit} · {data.subject.label}: {num(shown.y)} {data.subject.unit}</div>
      <svg className="regime" viewBox={`0 0 ${SPACE.w} ${SPACE.h}`} onMouseLeave={() => setHover(null)} data-testid="ladder-plot">
        {space ? geo.edges.map(([a, b], i) => <line key={i} x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} stroke="var(--line)" />)
          : <rect x={SPACE.w / 2 - 400} y={SPACE.h / 2 - 220} width={800} height={440} fill="none" stroke="var(--line)" />}
        {space && pts.filter((_, i) => i % 4 === 0).map((p) => { const [x, y] = geo.at(p); const floor = geo.project(((p.x - geo.x0) / (geo.x1 - geo.x0 || 1)) * 2 - 1, -1, ((Date.parse(p.day) - Date.parse(pts[0].day)) / (Date.parse(last.day) - Date.parse(pts[0].day) || 1)) * 2 - 1); return <line key={p.day} x1={x} y1={y} x2={floor[0]} y2={floor[1]} stroke="var(--line)" strokeDasharray="2 3" />; })}
        {pts.slice(1).map((p, i) => { const [a, b] = [geo.at(pts[i]), geo.at(p)]; return <line key={p.day} x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} stroke="var(--accent)" strokeWidth="1.8" opacity={0.15 + 0.85 * ((i + 1) / pts.length)} />; })}
        {pts.map((p) => { const [x, y] = geo.at(p); return <circle key={p.day} cx={x} cy={y} r="7" fill="transparent" onMouseEnter={() => setHover(p)} />; })}
        {geo.years.map((p) => { const [x, y] = geo.at(p); return <text key={p.day} x={x + 6} y={y - 6} fontSize="11" fill="var(--muted)">{p.day.slice(0, 4)}</text>; })}
        {(() => { const [x, y] = geo.at(last); return <circle cx={x} cy={y} r="8" fill="none" stroke="var(--text)" strokeWidth="2" />; })()}
        <text x={SPACE.w / 2} y={SPACE.h - 8} textAnchor="middle" fontSize="11" fill="var(--muted)">→ {data.driver.label} ({data.driver.unit}) · {num(geo.x0)} bis {num(geo.x1)}{space ? " · Tiefe: Zeit" : ""}</text>
        <text x={12} y={SPACE.h / 2} textAnchor="middle" fontSize="11" fill="var(--muted)" transform={`rotate(-90 12 ${SPACE.h / 2})`}>↑ {data.subject.label} ({data.subject.unit}) · {num(geo.y0)} bis {num(geo.y1)}</text>
      </svg>
    </>
  );
}

function Slope({ slope }: { slope: Json | null }) {
  if (!slope) return <span className="muted">zu wenige gemeinsame Änderungen</span>;
  const stable = slope.first_half != null && slope.second_half != null && Math.sign(slope.first_half) === Math.sign(slope.second_half);
  return <span title={`Bestimmtheitsmass ${num(slope.r2)} · ${slope.n} Änderungen`}><b>{signed(slope.beta, "")}</b> {slope.unit} <span className="muted">· erklärt {num(slope.r2 * 100)} % · n = {slope.n} · Hälften {signed(slope.first_half, "")} / {signed(slope.second_half, "")}{stable ? "" : " (Vorzeichen wechselt)"}</span></span>;
}

function Ladder({ series, start }: { series: Json[]; start: string }) {
  const [trail, setTrail] = useState<string[]>([start]);
  const [driver, setDriver] = useState("");
  const [years, setYears] = useState(3);
  const [space, setSpace] = useState(false);
  const [angle, setAngle] = useState(35);
  const [data, setData] = useState<Json | null>(null);
  const [error, setError] = useState("");
  const key = trail[trail.length - 1];
  useEffect(() => {
    get("/charts/ladder", { key, driver, years: String(years) }).then((d) => { setData(d); setError(""); }).catch((e) => { setData(null); setError(e.message); });
  }, [key, driver, years]);
  const go = (next: string) => { setDriver(""); setTrail((t) => (t.includes(next) ? t.slice(0, t.indexOf(next) + 1) : [...t, next])); };
  const label = (k: string) => series.find((s) => s.key === k)?.label ?? k;
  return (
    <div data-testid="ladder">
      <p className="small muted">Jeder Wert wird gegen das gezeigt, was hinter ihm steht: die Aktie gegen ihren Rohstoff, der Rohstoff gegen Realzins und Dollar, diese gegen Inflation und Liquidität, die Inflation gegen Energie. Die Zeit ist keine Achse, sondern der Weg (blass = früher, Ring = heute). „Eine Stufe tiefer“ macht den Treiber selbst zum Gegenstand.</p>
      <div className="row small" style={{ marginBottom: 8 }}>
        <SeriesSelect testid="ladder-subject" series={series} value={key} set={(v) => { setDriver(""); setTrail([v]); }} />
        <span className="row" data-testid="ladder-trail">{trail.map((k, i) => <span key={k}>{i > 0 && " → "}<button className={i === trail.length - 1 ? "on" : ""} onClick={() => go(k)}>{label(k)}</button></span>)}</span>
        <span className="right row"><Years value={years} set={setYears} /><label><input type="checkbox" data-testid="ladder-space" checked={space} onChange={() => setSpace(!space)} /> Raum (Zeit als Tiefe)</label>{space && <input type="range" min={-80} max={80} value={angle} onChange={(e) => setAngle(Number(e.target.value))} title="drehen" />}</span>
      </div>
      {error && <div className="note">{error}</div>}
      {data && (
        <>
          <div className="box">
            <div className="row">
              <h2 style={{ margin: 0 }}>{data.subject.label}</h2>
              {data.drivers.length > 0 ? <span className="small muted">gegen</span> : <span className="small muted">Für diese Reihe ist kein Treiber hinterlegt – hier endet die Leiter.</span>}
              {data.drivers.map((d: Json) => <button key={d.key} className={data.driver?.key === d.key ? "on" : ""} data-testid={`driver-${d.key}`} onClick={() => setDriver(d.key)}>{d.label}</button>)}
              {data.driver?.has_drivers && <button className="primary right" data-testid="ladder-deeper" onClick={() => go(data.driver.key)}>Eine Stufe tiefer: {data.driver.label} →</button>}
            </div>
            {data.path.length > 1 ? <Path3 data={data} space={space} angle={angle} /> : data.driver && <div className="muted small chartempty">Keine gemeinsamen Werte in diesem Zeitraum.</div>}
            {data.driver && <p className="small" data-testid="ladder-slope">Empfindlichkeit von {data.subject.label} auf {data.driver.label}: <Slope slope={data.slope} /></p>}
            <p className="small muted">{data.note}</p>
          </div>
          <div className="box">
            <h3>Was hängt an {data.subject.label}?</h3>
            {data.dependents.length === 0 ? <p className="small muted">Nichts Hinterlegtes.</p> : (
              <table className="small" data-testid="ladder-dependents">
                <thead><tr><th>Wert</th><th>Empfindlichkeit auf {data.subject.label} (Schätzung)</th></tr></thead>
                <tbody>{data.dependents.map((d: Json) => <tr key={d.key}><td><button className="link" onClick={() => { setDriver(""); setTrail([d.key]); }}>{d.label}</button></td><td><Slope slope={d.slope} /></td></tr>)}</tbody>
              </table>
            )}
          </div>
        </>
      )}
    </div>
  );
}

export function Charts() {
  const [tab, setTab] = useState("ladder");
  const [series, setSeries] = useState<Json[]>([]);
  const [subject, setSubject] = useState("");
  useEffect(() => {
    get("/charts/series").then((list: Json[]) => {
      setSeries(list);
      setSubject((current) => current || (list.find((s) => s.share) ?? list.find((s) => s.money && s.key !== "gold"))?.key || "");
    });
  }, []);
  return (
    <div className="page charts" data-testid="charts">
      <div className="row tabs">
        {TABS.map(([key, label]) => <button key={key} data-testid={`tab-${key}`} className={tab === key ? "on" : ""} onClick={() => setTab(key)}>{label}</button>)}
        <span className="muted small">Alles hier ist Rechnung auf gespeicherten Werten – keine Prognose, kein Signal.</span>
      </div>
      {tab === "ladder" && subject && <Ladder series={series} start={subject} />}
      {tab === "matrix" && <Matrix openChain={(key) => { if (key !== "gold") { setSubject(key); setTab("chain"); } }} />}
      {tab === "chain" && <Chain series={series} subject={subject} setSubject={setSubject} />}
      {tab === "lens" && <Lens series={series} subject={subject} setSubject={setSubject} />}
      {tab === "regime" && <Regime series={series} />}
    </div>
  );
}
