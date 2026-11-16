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
            <p className="small muted">{day(data.from)} bis {day(data.to)} · entspricht {signed(data.total_log, "")} Punkten. Die Balken hängen aneinander und enden bei der Gesamtänderung.</p>
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
      <div className="small muted">{day(path[0].day)} bis {day(path[path.length - 1].day)} · Punkte seit Beginn (etwa Prozent); die Linien addieren sich an jedem Tag zur Kursänderung.</div>
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
          <p className="small muted">Linie: Weg von {day(data.from)} (blass) bis heute (kräftig, Ring). ▲ grün = dein Kauf, ▽ = dein Verkauf, ▲ gelb = deine Anpassung – Einträge aus deinem Entscheidungsprotokoll, keine Empfehlung{geo.marks.length === 0 ? " – in diesem Zeitraum gibt es keine Einträge" : ""}. {data.note}</p>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- driver ladder
const SPACE = { w: 1000, h: 560, pad: 56 };
const HOME = { yaw: 35, pitch: 22 };
type P3 = [number, number, number];

/** Path through (driver, value, time). Flat: time is only the path. Space: drag to turn; the cube is refitted to the frame at every angle. */
function Space({ data, space }: { data: Json; space: boolean }) {
  const [view, setView] = useState(HOME);
  const [hover, setHover] = useState<Json | null>(null);
  const [drag, setDrag] = useState<{ x: number; y: number } | null>(null);
  const pts: Json[] = data.path;
  const geo = useMemo(() => {
    const span = (get: (p: Json) => number) => { const v = pts.map(get); return [Math.min(...v), Math.max(...v)]; };
    const [x0, x1] = span((p) => p.x), [y0, y1] = span((p) => p.y);
    const t0 = Date.parse(pts[0].day), t1 = Date.parse(pts[pts.length - 1].day);
    const unit = (v: number, lo: number, hi: number) => ((v - lo) / (hi - lo || 1)) * 2 - 1;
    const yaw = space ? (view.yaw * Math.PI) / 180 : 0, pitch = space ? (view.pitch * Math.PI) / 180 : 0;
    const raw = ([x, y, z]: P3): [number, number] => {
      const rx = x * Math.cos(yaw) + z * Math.sin(yaw);
      const rz = -x * Math.sin(yaw) + z * Math.cos(yaw);
      return [rx, -(y * Math.cos(pitch) - rz * Math.sin(pitch))];
    };
    const depth = space ? [-1, 1] : [0];
    const corners: P3[] = [-1, 1].flatMap((x) => [-1, 1].flatMap((y) => depth.map((z) => [x, y, z] as P3)));
    const flat = corners.map(raw);
    const [bx0, bx1] = [Math.min(...flat.map((c) => c[0])), Math.max(...flat.map((c) => c[0]))];
    const [by0, by1] = [Math.min(...flat.map((c) => c[1])), Math.max(...flat.map((c) => c[1]))];
    const scale = Math.min((SPACE.w - 2 * SPACE.pad) / (bx1 - bx0), (SPACE.h - 2 * SPACE.pad) / (by1 - by0));
    const project = (p: P3): [number, number] => { const [x, y] = raw(p); return [SPACE.w / 2 + (x - (bx0 + bx1) / 2) * scale, SPACE.h / 2 + (y - (by0 + by1) / 2) * scale]; };
    const cube = (p: Json): P3 => [unit(p.x, x0, x1), unit(p.y, y0, y1), space ? unit(Date.parse(p.day), t0, t1) : 0];
    const edges = corners.flatMap((a, i) => corners.slice(i + 1).filter((b) => a.filter((v, k) => v !== b[k]).length === 1).map((b) => [project(a), project(b)]));
    const years: Json[] = [];
    pts.forEach((p, i) => { if (i === 0 || p.day.slice(0, 4) !== pts[i - 1].day.slice(0, 4)) years.push(p); });
    return { project, cube, edges, years, x0, x1, y0, y1, screen: pts.map((p) => project(cube(p))), floor: pts.map((p) => { const c = cube(p); return project([c[0], -1, c[2]]); }) };
  }, [pts, space, view]);
  const last = pts[pts.length - 1];
  const shown = hover ?? last;
  const local = (e: React.PointerEvent<SVGSVGElement>) => { const box = e.currentTarget.getBoundingClientRect(); return [((e.clientX - box.left) / box.width) * SPACE.w, ((e.clientY - box.top) / box.height) * SPACE.h]; };
  const move = (e: React.PointerEvent<SVGSVGElement>) => {
    if (drag && space) {
      setView((v) => ({ yaw: v.yaw + (e.clientX - drag.x) * 0.4, pitch: Math.max(-5, Math.min(85, v.pitch + (e.clientY - drag.y) * 0.3)) }));
      setDrag({ x: e.clientX, y: e.clientY });
      return;
    }
    const [mx, my] = local(e);
    let best = 0, dist = Infinity;
    geo.screen.forEach(([x, y], i) => { const d = (x - mx) ** 2 + (y - my) ** 2; if (d < dist) { dist = d; best = i; } });
    setHover(dist < 30 ** 2 ? pts[best] : null);
  };
  const label = (at: P3, text: string, anchor: "start" | "middle" | "end" = "middle", dy = 16) => { const [x, y] = geo.project(at); return <text x={x} y={y + dy} textAnchor={anchor} fontSize="11" fill="var(--muted)">{text}</text>; };
  const line = (list: [number, number][]) => list.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  return (
    <>
      <div className="small chartread" data-testid="ladder-read"><b>{day(shown.day)}</b>{hover ? "" : " (letzter Wert)"} · {data.driver.label}: {num(shown.x)} {data.driver.unit} · {data.subject.label}: {num(shown.y)} {data.subject.unit}</div>
      <svg className={`regime ${space ? "turn" : ""}`} viewBox={`0 0 ${SPACE.w} ${SPACE.h}`} data-testid="ladder-plot" data-yaw={Math.round(view.yaw)}
        onPointerDown={(e) => { if (space) { e.currentTarget.setPointerCapture(e.pointerId); setDrag({ x: e.clientX, y: e.clientY }); } }}
        onPointerUp={() => setDrag(null)} onPointerMove={move} onPointerLeave={() => { setHover(null); setDrag(null); }} onDoubleClick={() => setView(HOME)}>
        {geo.edges.map(([a, b], i) => <line key={i} x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} stroke="var(--line)" />)}
        {space && <path d={line(geo.floor)} fill="none" stroke="var(--muted)" strokeWidth="1" opacity="0.45" />}
        {space && pts.map((p, i) => (i % 6 === 0 ? <line key={p.day} x1={geo.screen[i][0]} y1={geo.screen[i][1]} x2={geo.floor[i][0]} y2={geo.floor[i][1]} stroke="var(--line)" strokeDasharray="2 3" /> : null))}
        {pts.slice(1).map((p, i) => <line key={p.day} x1={geo.screen[i][0]} y1={geo.screen[i][1]} x2={geo.screen[i + 1][0]} y2={geo.screen[i + 1][1]} stroke="var(--accent)" strokeWidth="1.8" strokeLinecap="round" opacity={0.15 + 0.85 * ((i + 1) / pts.length)} />)}
        {geo.years.map((p) => { const [x, y] = geo.project(geo.cube(p)); return <text key={p.day} x={x + 6} y={y - 6} fontSize="11" fill="var(--muted)">{p.day.slice(0, 4)}</text>; })}
        {hover && (() => { const [x, y] = geo.project(geo.cube(hover)); return <circle cx={x} cy={y} r="4" fill="var(--accent)" />; })()}
        {(() => { const [x, y] = geo.screen[geo.screen.length - 1]; return <circle cx={x} cy={y} r="8" fill="none" stroke="var(--text)" strokeWidth="2" />; })()}
        {label([0, -1, space ? -1 : 0], `→ ${data.driver.label} (${data.driver.unit})`)}
        {label([-1, -1, space ? -1 : 0], num(geo.x0), "start")}{label([1, -1, space ? -1 : 0], num(geo.x1), "end")}
        {label([-1, 1, space ? -1 : 0], `↑ ${data.subject.label} (${data.subject.unit}) · ${num(geo.y0)} bis ${num(geo.y1)}`, "start", -8)}
        {space && label([1, -1, 0], `Zeit: ${day(pts[0].day)} → ${day(last.day)}`, "start", 32)}
      </svg>
      {space && <div className="small muted">Mit der Maus ziehen dreht die Ansicht, Doppelklick stellt sie zurück. Die graue Linie am Boden ist der Schatten des Wegs (Treiber × Zeit).</div>}
    </>
  );
}

function Slope({ slope }: { slope: Json | null }) {
  if (!slope) return <span className="muted">zu wenige gemeinsame Änderungen</span>;
  const detail = `erklärt ${num(slope.r2 * 100)} % · t = ${slope.t == null ? "–" : num(slope.t)} · n = ${slope.n} · Hälften ${signed(slope.first_half, "")} / ${signed(slope.second_half, "")}`;
  const overlap = slope.overlapping ? " · Jahresraten überlappen: n und t sind überschätzt" : "";
  if (slope.weak) return <span className="muted" data-testid="slope-weak" title={`${signed(slope.beta, "")} ${slope.unit} · ${detail}${overlap}`}>kein belastbarer Zusammenhang im Zeitraum ({signed(slope.beta, "")} {slope.unit}, t = {slope.t == null ? "–" : num(slope.t)}{overlap})</span>;
  return <span><b>{signed(slope.beta, "")}</b> {slope.unit} <span className="muted">· {detail}{overlap}</span></span>;
}

/** The whole ladder on one sheet: every rung with its latest move and how unusual that move is. */
function Sheet({ subject, years, open }: { subject: string; years: number; open: (key: string) => void }) {
  const [data, setData] = useState<Json | null>(null);
  useEffect(() => { get("/charts/sheet", { key: subject, years: String(years) }).then(setData).catch(() => setData(null)); }, [subject, years]);
  if (!data) return <div className="muted small">Lade …</div>;
  return (
    <div className="box" data-testid="sheet">
      {data.rungs.map((r: Json, i: number) => {
        const rare = r.unusual != null && Math.abs(r.unusual) >= 2;
        return (
          <div key={r.key}>
            <div className={`rung ${rare ? "rare" : ""}`} data-testid={`rung-${r.key}`}>
              <span><span className="muted small">Stufe {i + 1}</span><br /><button className="link" onClick={() => open(r.key)}><b>{r.label}</b></button></span>
              <span className="tilevalue">{r.value == null ? "–" : num(r.value)} <span className="small muted">{r.unit}</span><br /><span className="small muted">{day(r.day)}</span></span>
              <span><Spark values={r.spark} /><span className="range" title="Lage des heutigen Werts in der Spanne des Zeitraums">{r.position != null && <i style={{ left: `${r.position * 100}%` }} />}</span></span>
              <span className="small">letzter Monat: <b className={r.move == null ? "" : r.move >= 0 ? "up" : "down"}>{signed(r.move, ` ${r.move_unit}`)}</b><br />
                <span className={rare ? "pill warn" : "muted"}>{r.unusual == null ? "zu wenige Werte" : `${signed(r.unusual, "")} Standardabweichungen${rare ? " – selten" : ""}`}</span></span>
            </div>
            {r.next && <div className="rungstep small">↓ hinterlegter Treiber <b>{r.next}</b>: <Slope slope={r.slope} /></div>}
          </div>
        );
      })}
      <p className="small muted">{data.note}</p>
    </div>
  );
}

/** Polar view: the angle is the phase of the driver, the radius the value of the subject. */
function Clock({ subject, driver, years }: { subject: string; driver: string; years: number }) {
  const [data, setData] = useState<Json | null>(null);
  const [error, setError] = useState("");
  const [hover, setHover] = useState<Json | null>(null);
  useEffect(() => {
    get("/charts/cycle", { key: subject, driver, years: String(years) }).then((d) => { setData(d); setError(""); }).catch((e) => { setData(null); setError(e.message); });
  }, [subject, driver, years]);
  const S = 820, C = S / 2, R = 270;
  const geo = useMemo(() => {
    if (!data) return null;
    const ys = data.points.map((p: Json) => p.y);
    const positive = ys.every((v: number) => v > 0);
    const f = (v: number) => (positive ? Math.log(v) : v);
    const lo = Math.min(...ys.map(f)), hi = Math.max(...ys.map(f));
    const radius = (v: number) => R * (0.22 + 0.78 * ((f(v) - lo) / (hi - lo || 1)));
    const at = (p: Json): [number, number] => { const a = (p.angle * Math.PI) / 180; return [C + radius(p.y) * Math.cos(a), C - radius(p.y) * Math.sin(a)]; };
    const ray = (deg: number, r: number): [number, number] => [C + r * Math.cos((deg * Math.PI) / 180), C - r * Math.sin((deg * Math.PI) / 180)];
    return { at, ray, lo: Math.min(...ys), hi: Math.max(...ys), screen: data.points.map(at) };
  }, [data]);
  if (error) return <div className="note" data-testid="clock-error">{error}</div>;
  if (!data || !geo) return <div className="muted small">Lade …</div>;
  const width = 360 / data.sectors.length;
  const last = data.points[data.points.length - 1];
  const shown = hover ?? last;
  const wedge = (() => { const [a, b] = [data.today * width - width / 2, data.today * width + width / 2]; const [p, q] = [geo.ray(a, R), geo.ray(b, R)]; return `M${C},${C} L${p[0]},${p[1]} A${R},${R} 0 0 0 ${q[0]},${q[1]} Z`; })();
  return (
    <div className="box" data-testid="clock">
      <div className="row"><h2 style={{ margin: 0 }}>{data.subject.label} auf der Zyklusuhr von {data.driver.label}</h2></div>
      <div className="small chartread" data-testid="clock-read"><b>{day(shown.day)}</b>{hover ? "" : " (letzter Wert)"} · Phase: {data.sectors[shown.sector]} · {data.subject.label}: {num(shown.y)} {data.subject.unit}</div>
      <div className="clockgrid">
        <svg className="clock" viewBox={`0 0 ${S} ${S}`} onMouseLeave={() => setHover(null)}
          onMouseMove={(e) => { const box = e.currentTarget.getBoundingClientRect(); const [mx, my] = [((e.clientX - box.left) / box.width) * S, ((e.clientY - box.top) / box.height) * S]; let best = 0, dist = Infinity; geo.screen.forEach(([x, y]: [number, number], i: number) => { const d = (x - mx) ** 2 + (y - my) ** 2; if (d < dist) { dist = d; best = i; } }); setHover(dist < 30 ** 2 ? data.points[best] : null); }}>
          <path d={wedge} fill="var(--accent)" opacity="0.1" />
          {[0.22, 0.61, 1].map((share) => <circle key={share} cx={C} cy={C} r={R * share} fill="none" stroke="var(--line)" />)}
          {data.sectors.map((name: string, i: number) => { const [x, y] = geo.ray(i * width + width / 2, R); const [tx, ty] = geo.ray(i * width, R + 26); return <g key={name}><line x1={C} y1={C} x2={x} y2={y} stroke="var(--line)" strokeDasharray="2 4" /><text x={tx} y={ty} textAnchor="middle" dominantBaseline="middle" fontSize="15" fill={i === data.today ? "var(--text)" : "var(--muted)"} fontWeight={i === data.today ? 700 : 400}>{name}</text></g>; })}
          {data.points.slice(1).map((p: Json, i: number) => <line key={p.day} x1={geo.screen[i][0]} y1={geo.screen[i][1]} x2={geo.screen[i + 1][0]} y2={geo.screen[i + 1][1]} stroke="var(--accent)" strokeWidth="1.8" strokeLinecap="round" opacity={0.15 + 0.85 * ((i + 1) / data.points.length)} />)}
          {hover && <circle cx={geo.at(hover)[0]} cy={geo.at(hover)[1]} r="4" fill="var(--accent)" />}
          <circle cx={geo.at(last)[0]} cy={geo.at(last)[1]} r="8" fill="none" stroke="var(--text)" strokeWidth="2" />
          <text x={C} y={C + 4} textAnchor="middle" fontSize="10" fill="var(--muted)">{num(geo.lo)}</text>
          <text x={C} y={C - R - 4} textAnchor="middle" fontSize="10" fill="var(--muted)">aussen {num(geo.hi)}</text>
        </svg>
        <div>
          <h3>Frühere Zeiträume in der heutigen Phase</h3>
          <p className="small">Heute: <b>{data.sectors[data.today]}</b> ({data.driver.label}).</p>
          <table className="small" data-testid="clock-episodes">
            <thead><tr><th>Zeitraum</th><th>Werte</th><th>{data.subject.label} in dieser Zeit</th></tr></thead>
            <tbody>{data.episodes.filter((e: Json) => e.n >= 3).map((e: Json) => <tr key={e.from}><td>{day(e.from)} – {day(e.to)}</td><td>{e.n}</td><td className={e.change_pct == null ? "" : e.change_pct >= 0 ? "up" : "down"}>{signed(e.change_pct)}</td></tr>)}</tbody>
          </table>
          <p className="small muted">Die Änderung gilt während des Zeitraums, nicht danach. Zeiträume mit weniger als drei Werten sind nicht aufgeführt. {data.episodes.filter((e: Json) => e.n >= 3).length < 4 ? "Das sind zu wenige Zeiträume für irgendeine Regel. " : ""}</p>
        </div>
      </div>
      <p className="small muted">{data.note} Die Bewegung des Treibers ist über {data.span} Beobachtungen gemessen.</p>
    </div>
  );
}

const LADDER_VIEWS: [string, string][] = [["sheet", "Ganze Leiter"], ["path", "Weg"], ["clock", "Zyklusuhr"], ["own", "Eigenwert"]];

function Ladder({ series, start, setStart }: { series: Json[]; start: string; setStart: (v: string) => void }) {
  const [trail, setTrail] = useState<string[]>([start]);
  useEffect(() => { setTrail((t) => (t[0] === start ? t : [start])); }, [start]);
  const [driver, setDriver] = useState("");
  const [years, setYears] = useState(3);
  const [view, setView] = useState("sheet");
  const [space, setSpace] = useState(false);
  const [data, setData] = useState<Json | null>(null);
  const [error, setError] = useState("");
  const key = trail[trail.length - 1];
  useEffect(() => {
    get("/charts/ladder", { key, driver, years: String(years) }).then((d) => { setData(d); setError(""); }).catch((e) => { setData(null); setError(e.message); });
  }, [key, driver, years]);
  const go = (next: string) => { setDriver(""); setTrail((t) => (t.includes(next) ? t.slice(0, t.indexOf(next) + 1) : [...t, next])); };
  const label = (k: string) => series.find((s) => s.key === k)?.label ?? k;
  const ownLast = data?.own?.length ? data.own[data.own.length - 1] : null;
  return (
    <div data-testid="ladder">
      <p className="small muted">Jeder Wert wird gegen das gezeigt, was hinter ihm steht: die Aktie gegen ihren Rohstoff, der Rohstoff gegen Realzins und Dollar, diese gegen Inflation und Liquidität, die Inflation gegen Energie.</p>
      <div className="row small" style={{ marginBottom: 8 }}>
        <SeriesSelect testid="ladder-subject" series={series} value={key} set={(v) => { setDriver(""); setTrail([v]); setStart(v); }} />
        <span className="row" data-testid="ladder-trail">{trail.map((k, i) => <span key={k}>{i > 0 && " → "}<button className={i === trail.length - 1 ? "on" : ""} onClick={() => go(k)}>{label(k)}</button></span>)}</span>
        <span className="right row">{LADDER_VIEWS.map(([k, name]) => <button key={k} data-testid={`view-${k}`} className={view === k ? "on" : ""} onClick={() => setView(k)}>{name}</button>)}<Years value={years} set={setYears} /></span>
      </div>
      {error && <div className="note">{error}</div>}
      {view === "sheet" && <Sheet subject={trail[0]} years={years} open={(k) => { if (k !== trail[0]) setTrail([trail[0], k]); setView("path"); }} />}
      {data && view !== "sheet" && (
        <div className="box">
          <div className="row">
            <h2 style={{ margin: 0 }}>{data.subject.label}</h2>
            {data.drivers.length > 0 ? <span className="small muted">gegen</span> : <span className="small muted">Für diese Reihe ist kein Treiber hinterlegt – hier endet die Leiter.</span>}
            {data.drivers.map((d: Json) => <button key={d.key} className={data.driver?.key === d.key ? "on" : ""} data-testid={`driver-${d.key}`} onClick={() => setDriver(d.key)}>{d.label}</button>)}
            {view === "path" && <label className="small"><input type="checkbox" data-testid="ladder-space" checked={space} onChange={() => setSpace(!space)} /> Raum (Zeit als dritte Achse)</label>}
            {data.driver?.has_drivers && !trail.includes(data.driver.key) && <button className="primary right" data-testid="ladder-deeper" onClick={() => go(data.driver.key)}>Eine Stufe tiefer: {data.driver.label} →</button>}
            {data.driver && trail.includes(data.driver.key) && <span className="small muted right">Hier schliesst sich der Kreis: {data.driver.label} steht schon in der Spur.</span>}
          </div>
          {view === "path" && (data.path.length > 1 ? <Space data={data} space={space} /> : data.driver && <div className="muted small chartempty">Keine gemeinsamen Werte in diesem Zeitraum.</div>)}
          {view === "path" && data.driver && <p className="small" data-testid="ladder-slope">Empfindlichkeit von {data.subject.label} auf {data.driver.label}: <Slope slope={data.slope} /></p>}
          {view === "own" && (ownLast ? (
            <div data-testid="own">
              <p data-testid="own-plain"><b>In einem Satz:</b> Seit {day(data.own[0].day)} hat sich {data.subject.label} um <b>{signed((Math.exp((ownLast.values[0] + ownLast.values[1]) / 100) - 1) * 100)}</b> verändert. {data.slope?.weak
                ? <>{data.driver.label} erklärt davon im Zeitraum nichts Belastbares – die Änderung liegt rechnerisch fast ganz am Wert selbst.</>
                : <>Rechnerisch kommen <b style={{ color: LINK_COLORS[0] }}>{signed(ownLast.values[0], "")}</b> Punkte von {data.driver.label} und <b style={{ color: LINK_COLORS[1] }}>{signed(ownLast.values[1], "")}</b> Punkte vom Wert selbst.</>}</p>
              <p className="small muted">Gesamt {signed(ownLast.values[0] + ownLast.values[1], "")} Punkte = <span style={{ color: LINK_COLORS[0] }}>{signed(ownLast.values[0], "")}</span> von {data.driver.label} erklärt + <span style={{ color: LINK_COLORS[1] }} data-testid="own-part">{signed(ownLast.values[1], "")}</span> eigener Anteil.</p>
              <Lines path={data.own} labels={[`von ${data.driver.label} erklärt`, `eigener Anteil (${data.subject.label})`]} />
              <p className="small muted">{data.own_note}</p>
            </div>
          ) : <div className="muted small chartempty" data-testid="own-empty">Der eigene Anteil lässt sich nur für Preise gegen Preise bilden und braucht genug gemeinsame Beobachtungen.</div>)}
          {view !== "clock" && <p className="small muted">{data.note}</p>}
        </div>
      )}
      {data && view === "clock" && data.driver && <Clock subject={key} driver={data.driver.key} years={Math.max(years, 3)} />}
      {data && view === "clock" && !data.driver && <div className="note">Für diese Reihe ist kein Treiber hinterlegt.</div>}
      {data && view !== "sheet" && (
        <div className="box">
          <h3>Was hängt an {data.subject.label}?</h3>
          {data.dependents.length === 0 ? <p className="small muted">Nichts Hinterlegtes.</p> : (
            <table className="small" data-testid="ladder-dependents">
              <thead><tr><th>Wert</th><th>Empfindlichkeit auf {data.subject.label} (Schätzung)</th></tr></thead>
              <tbody>{data.dependents.map((d: Json) => <tr key={d.key}><td><button className="link" onClick={() => { setDriver(""); setTrail([d.key]); setStart(d.key); }}>{d.label}</button></td><td><Slope slope={d.slope} /></td></tr>)}</tbody>
            </table>
          )}
        </div>
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
      {tab === "ladder" && subject && <Ladder series={series} start={subject} setStart={setSubject} />}
      {tab === "matrix" && <Matrix openChain={(key) => { if (key !== "gold") { setSubject(key); setTab("chain"); } }} />}
      {tab === "chain" && <Chain series={series} subject={subject} setSubject={setSubject} />}
      {tab === "lens" && <Lens series={series} subject={subject} setSubject={setSubject} />}
      {tab === "regime" && <Regime series={series} />}
    </div>
  );
}
