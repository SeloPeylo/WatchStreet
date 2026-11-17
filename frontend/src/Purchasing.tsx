// Purchasing-power band: one value over time, measured in five yardsticks at once (no dollar inside).
import { useEffect, useMemo, useState } from "react";
import type { Json } from "./api";
import { get } from "./api";

const W = 1000;
const H = 360;
const PAD = { left: 8, right: 8, top: 12, bottom: 22 };
const STRIP_H = 28;
// percentage changes that may become value ticks (log scale: points = 100 × ln(1 + pct/100))
const TICK_PCT = [-95, -90, -80, -67, -50, -33, -20, -10, 0, 10, 25, 50, 100, 200, 300, 500, 1000, 2000];
const MAX_TICKS = 8;
const VERDICT: [string, string, string][] = [
  ["all_up", "alle Massstäbe: gewonnen", "var(--ok)"],
  ["most_up", "Mehrheit gewonnen", "color-mix(in srgb, var(--ok) 40%, var(--panel))"],
  ["split", "uneinig", "var(--line)"],
  ["most_down", "Mehrheit verloren", "color-mix(in srgb, var(--bad) 40%, var(--panel))"],
  ["all_down", "alle Massstäbe: verloren", "var(--bad)"],
];
// Categorical slots 1–5 of the validated reference palette (light / dark steps), fixed per yardstick.
const CSS = `
.pp { --pp-1:#2a78d6; --pp-2:#eb6834; --pp-3:#1baf7a; --pp-4:#eda100; --pp-5:#e87ba4; }
@media (prefers-color-scheme: dark) { :root:where(:not([data-theme="light"])) .pp { --pp-1:#3987e5; --pp-2:#d95926; --pp-3:#199e70; --pp-4:#c98500; --pp-5:#d55181; } }
:root[data-theme="dark"] .pp { --pp-1:#3987e5; --pp-2:#d95926; --pp-3:#199e70; --pp-4:#c98500; --pp-5:#d55181; }
.pp .plot svg { width: 100%; height: ${H}px; display: block; cursor: crosshair; }
.pp .strip svg { width: 100%; height: ${STRIP_H}px; display: block; }
.pp .ends span { position: absolute; right: 4px; transform: translateY(-50%); font-size: 11px; background: color-mix(in srgb, var(--panel) 80%, transparent); padding: 0 3px; border-radius: 3px; }
.pp .ticks span { position: absolute; left: 4px; transform: translateY(-50%); font-size: 11px; color: var(--muted); }
.pp .swatch { display: inline-block; width: 12px; height: 3px; border-radius: 2px; vertical-align: middle; margin-right: 4px; }
.pp .read { min-height: 40px; display: flex; flex-wrap: wrap; gap: 4px 14px; align-items: baseline; }
`;
const EXPLAIN = [
  "Jede farbige Linie ist der Wert, gemessen in einem Massstab: in Warenkörben, Arbeitsstunden, Anteilen an der Geldmenge, Unzen Gold oder Barrel Öl. Wert und Massstab sind beide in Dollar notiert; beim Teilen kürzt sich der Dollar heraus.",
  "Die dicke Linie ist die Mitte (Median) der Massstäbe. Das dunkle Band reicht vom zweitniedrigsten bis zum zweithöchsten Massstab, das helle vom niedrigsten bis zum höchsten.",
  "Liegt das ganze Band über der Nulllinie, hat der Wert nach jedem Massstab an Kaufkraft gewonnen; schneidet es die Null, hängt das Urteil am Massstab. Der Streifen unter dem Chart zeigt das für jeden Monat.",
  "Wie breit das Band ist, hängt nicht vom Wert ab, sondern nur davon, wie weit die Massstäbe selbst auseinanderlaufen. Wähle „US-Dollar (Bargeld)“, um das Band pur zu sehen.",
  "„Seit Ausgangsmonat“: Änderung seit dem ersten Monat (ein Klick in den Chart setzt ihn neu). „Je 12 Monate“: Änderung gegenüber dem Vorjahresmonat – so sieht man einzelne Episoden.",
  "Gold hat ein eigenes Regime (Realzins, Angst, Käufe der Notenbanken). Darum ist es nur einer von fünf Massstäben; wähle Gold als Wert, um sein Regime gegen die übrigen vier zu sehen.",
  "Gerechnet auf Monatsmitteln. Ein Monat zählt nur, wenn der Wert und alle Massstäbe einen eigenen Wert haben; deshalb endet das Band mit der spätesten gemeinsamen Veröffentlichung (meist M2).",
  "Die Skala ist logarithmisch: +100 % und −50 % liegen gleich weit von der Null. Rückschau, keine Prognose und kein Signal.",
];

const pct = (points: number) => (Math.exp(points / 100) - 1) * 100;
const round = (v: number) => (Math.abs(v) >= 10 ? Math.round(v).toLocaleString("de-DE") : v.toLocaleString("de-DE", { maximumFractionDigits: 1 }));
const signedPct = (points: number) => { const p = pct(points); return `${p >= 0 ? "+" : p < 0 ? "−" : ""}${round(Math.abs(p))} %`; };
const monthText = (iso: string) => new Date(iso).toLocaleDateString("de-DE", { month: "short", year: "numeric", timeZone: "UTC" });
const colorOf = (slot: number) => `var(--pp-${slot + 1})`;
const MIN_TICK_GAP = 26; // viewBox units between two value ticks

function area(top: number[], bottom: number[], x: (i: number) => number, y: (v: number) => number): string {
  const upper = top.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const lower = bottom.map((_, k) => { const i = bottom.length - 1 - k; return `L${x(i).toFixed(1)},${y(bottom[i]).toFixed(1)}`; }).join(" ");
  return `${upper} ${lower} Z`;
}

function line(values: number[], x: (i: number) => number, y: (v: number) => number): string {
  return values.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
}

/** Right-hand labels at the last value, pushed apart so they do not overlap. */
function spread(items: { key: string; top: number }[], gap: number): Record<string, number> {
  const sorted = [...items].sort((a, b) => a.top - b.top);
  const out: Record<string, number> = {};
  let last = -Infinity;
  for (const item of sorted) { const top = Math.max(item.top, last + gap); out[item.key] = top; last = top; }
  return out;
}

function Band({ data, setStart }: { data: Json; setStart: (iso: string) => void }) {
  const [hover, setHover] = useState<number | null>(null);
  const months: string[] = data.months;
  const n = months.length;
  const keys: string[] = data.yardsticks.map((y: Json) => y.key);
  const lo = Math.min(0, ...data.low);
  const hi = Math.max(0, ...data.high);
  const margin = (hi - lo) * 0.04 || 1;
  const x = (i: number) => PAD.left + (i / Math.max(n - 1, 1)) * (W - PAD.left - PAD.right);
  const y = (v: number) => PAD.top + (1 - (v - (lo - margin)) / (hi - lo + 2 * margin)) * (H - PAD.top - PAD.bottom);
  const ticks = useMemo(() => {
    const inside = TICK_PCT.map((p) => 100 * Math.log(1 + p / 100)).filter((v) => v >= lo - margin && v <= hi + margin);
    const kept: number[] = [0];
    for (const v of [...inside].sort((a, b) => Math.abs(a) - Math.abs(b))) {
      if (kept.length < MAX_TICKS && kept.every((k) => Math.abs(y(k) - y(v)) >= MIN_TICK_GAP)) kept.push(v);
    }
    return kept.sort((a, b) => a - b);
  }, [lo, hi, margin]);
  const years = months.map((m, i) => [m, i] as [string, number]).filter(([m]) => m.endsWith("-01-01"));
  const yearStep = Math.max(Math.ceil(years.length / 12), 1);
  const at = hover ?? n - 1;
  const move = (e: React.MouseEvent<SVGSVGElement>) => {
    const box = e.currentTarget.getBoundingClientRect();
    const share = (((e.clientX - box.left) / box.width) * W - PAD.left) / (W - PAD.left - PAD.right);
    setHover(Math.min(Math.max(Math.round(share * (n - 1)), 0), n - 1));
  };
  const ends = spread(keys.map((k) => ({ key: k, top: (y(data.lines[k][n - 1]) / H) * H })), 14);
  const verdictOf = (i: number) => {
    const count = keys.length, up = data.up[i], down = data.down[i];
    if (up === count) return 0; if (down === count) return 4; if (up * 2 > count) return 1; if (down * 2 > count) return 3; return 2;
  };
  return (
    <div>
      <div className="small read" data-testid="pp-read">
        <b>{monthText(months[at])}</b>
        <span>Mitte <b>{signedPct(data.median[at])}</b></span>
        {data.yardsticks.map((ys: Json) => <span key={ys.key}><i className="swatch" style={{ background: colorOf(ys.slot) }} />in {ys.phrase} {signedPct(data.lines[ys.key][at])}</span>)}
        <span className="muted">{VERDICT[verdictOf(at)][1]}{hover === null ? " (letzter Monat)" : ""}</span>
      </div>
      <div className="plot" style={{ position: "relative" }}>
        <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" onMouseMove={move} onMouseLeave={() => setHover(null)} onClick={() => hover !== null && data.mode === "since" && setStart(months[hover])} data-testid="pp-chart" role="img" aria-label={`Kaufkraft-Band: ${data.plain}`}>
          {ticks.map((t) => <line key={t} x1={PAD.left} x2={W - PAD.right} y1={y(t)} y2={y(t)} stroke="var(--line)" strokeWidth={t === 0 ? 1.6 : 1} vectorEffect="non-scaling-stroke" />)}
          {years.filter((_, i) => i % yearStep === 0).map(([m, i]) => <line key={m} x1={x(i)} x2={x(i)} y1={PAD.top} y2={H - PAD.bottom} stroke="var(--line)" strokeDasharray="2 4" vectorEffect="non-scaling-stroke" />)}
          <path d={area(data.high, data.low, x, y)} fill="var(--text)" fillOpacity={0.07} data-testid="pp-band-outer" />
          <path d={area(data.inner_high, data.inner_low, x, y)} fill="var(--text)" fillOpacity={0.14} data-testid="pp-band-inner" />
          {data.yardsticks.map((ys: Json) => <path key={ys.key} d={line(data.lines[ys.key], x, y)} fill="none" stroke={colorOf(ys.slot)} strokeWidth={1.4} vectorEffect="non-scaling-stroke" data-testid={`pp-line-${ys.key}`} />)}
          <path d={line(data.median, x, y)} fill="none" stroke="var(--text)" strokeWidth={2.6} vectorEffect="non-scaling-stroke" data-testid="pp-median" />
          {hover !== null && <line x1={x(hover)} x2={x(hover)} y1={PAD.top} y2={H - PAD.bottom} stroke="var(--muted)" vectorEffect="non-scaling-stroke" />}
        </svg>
        <div className="ticks">{ticks.map((t) => <span key={t} style={{ top: `${(y(t) / H) * 100}%` }}>{t === 0 ? "0 %" : signedPct(t)}</span>)}</div>
        <div className="ends">{data.yardsticks.map((ys: Json) => <span key={ys.key} style={{ top: `${(ends[ys.key] / H) * 100}%`, color: "var(--text)", borderRight: `3px solid ${colorOf(ys.slot)}` }}>{ys.label}</span>)}</div>
        <div className="chartyears">{years.filter((_, i) => i % yearStep === 0).map(([m, i]) => <span key={m} style={{ left: `${(x(i) / W) * 100}%` }}>{m.slice(0, 4)}</span>)}</div>
      </div>
      <div className="strip" title="Einigkeit der Massstäbe je Monat">
        <svg viewBox={`0 0 ${W} ${STRIP_H}`} preserveAspectRatio="none" data-testid="pp-strip" onMouseMove={move} onMouseLeave={() => setHover(null)}>
          {months.map((m, i) => <rect key={m} x={x(i) - (W - PAD.left - PAD.right) / Math.max(n - 1, 1) / 2} width={(W - PAD.left - PAD.right) / Math.max(n - 1, 1) + 0.6} y={2} height={STRIP_H - 4} fill={VERDICT[verdictOf(i)][2]} data-verdict={VERDICT[verdictOf(i)][0]} />)}
          {hover !== null && <line x1={x(hover)} x2={x(hover)} y1={0} y2={STRIP_H} stroke="var(--text)" vectorEffect="non-scaling-stroke" />}
        </svg>
      </div>
      <div className="row small muted" data-testid="pp-strip-legend" style={{ marginTop: 4 }}>
        <span>Streifen:</span>
        {VERDICT.map(([key, label, color]) => <span key={key}><i className="swatch" style={{ background: color, height: 10 }} />{label}</span>)}
      </div>
    </div>
  );
}

export function Purchasing({ subject, setSubject }: { subject: string; setSubject: (key: string) => void }) {
  const [mode, setMode] = useState("since");
  const [start, setStart] = useState("");
  const [data, setData] = useState<Json | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    setLoading(true);
    let current = true; // a slower answer to an older choice must not overwrite a newer one
    get("/charts/purchasing", { key: subject || "GOLDWB", mode, start })
      .then((d) => { if (current) { setData(d); setError(""); } })
      .catch((e) => { if (current) { setData(null); setError(e.message); } })
      .finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [subject, mode, start]);
  const firstYear = data ? Number(data.first.slice(0, 4)) : 0;
  const years = data ? Array.from({ length: Number(data.end.slice(0, 4)) - firstYear }, (_, i) => firstYear + i) : [];
  const choices = data?.objects ?? [];
  return (
    <div className="pp" data-testid="purchasing" data-loading={loading ? "yes" : "no"}>
      <style>{CSS}</style>
      <div className="row" style={{ marginBottom: 8 }}>
        <select data-testid="pp-subject" value={data?.subject.key ?? ""} onChange={(e) => { setStart(""); setSubject(e.target.value); }}>
          <optgroup label="Werte">{choices.filter((o: Json) => !o.share).map((o: Json) => <option key={o.key} value={o.key}>{o.label}{o.synthetic ? " – Demo, synthetisch" : ""}</option>)}</optgroup>
          <optgroup label="Aktien">{choices.filter((o: Json) => o.share).map((o: Json) => <option key={o.key} value={o.key}>{o.label}{o.synthetic ? " – Demo, synthetisch" : ""}</option>)}</optgroup>
        </select>
        <span className="tabs">
          <button data-testid="pp-mode-since" className={mode === "since" ? "on" : ""} onClick={() => setMode("since")}>seit Ausgangsmonat</button>
          <button data-testid="pp-mode-rolling" className={mode === "rolling" ? "on" : ""} onClick={() => setMode("rolling")}>je 12 Monate</button>
        </span>
        <label className="small muted">ab{" "}
          <select data-testid="pp-start" value={start.slice(0, 4)} onChange={(e) => setStart(e.target.value ? `${e.target.value}-01` : "")}>
            <option value="">Anfang</option>
            {years.map((yr) => <option key={yr} value={String(yr)}>{yr}</option>)}
          </select>
        </label>
        {start && <button className="small" data-testid="pp-start-reset" onClick={() => setStart("")}>Ausgangsmonat zurücksetzen</button>}
      </div>
      {error && <div className="muted" data-testid="pp-error">{error}</div>}
      {loading && <span className="small muted" data-testid="pp-loading">Lade …</span>}
      {data && (
        <div style={{ opacity: loading ? 0.45 : 1, transition: "opacity 0.15s" }}>
          {data.notice && <p className="small muted" data-testid="pp-notice">{data.notice}</p>}
          {data.subject.synthetic && <p className="small" data-testid="pp-synthetic"><span className="demo">Demo</span> synthetische Kurse</p>}
          <p className="plain" data-testid="plain">{data.plain}</p>
          <div className="box">
            <div className="row"><h2 style={{ margin: 0 }}>{data.subject.label} in Kaufkraft</h2>
              <span className="muted small">{data.mode === "since" ? `Änderung seit ${monthText(data.start)}` : "Änderung gegenüber dem Vorjahresmonat"} · {monthText(data.start)} bis {monthText(data.end)} · Monatsmittel · {data.mode === "since" ? "Klick in den Chart setzt den Ausgangsmonat" : ""}</span>
            </div>
            <Band data={data} setStart={setStart} />
          </div>
          <div className="box" style={{ overflowX: "auto" }}>
            <table data-testid="pp-yardsticks">
              <thead><tr><th>Massstab</th><th>{data.mode === "since" ? "Änderung seit Ausgangsmonat" : "letzte 12 Monate"}</th><th>Monate allein abweichend</th><th>Was man über ihn wissen muss</th></tr></thead>
              <tbody>{data.yardsticks.map((ys: Json) => (
                <tr key={ys.key}>
                  <td style={{ whiteSpace: "nowrap" }}><i className="swatch" style={{ background: colorOf(ys.slot) }} />{ys.label}</td>
                  <td className={data.lines[ys.key][data.months.length - 1] >= 0 ? "up" : "down"}>{signedPct(data.lines[ys.key][data.months.length - 1])}</td>
                  <td>{data.summary.alone[ys.key]}</td>
                  <td className="small">{ys.note}</td>
                </tr>
              ))}</tbody>
            </table>
            {data.skipped.length > 0 && <p className="small muted" data-testid="pp-skipped">Nicht verwendet: {data.skipped.map((s: Json) => `${s.label} (${s.reason})`).join("; ")}.</p>}
            <p className="small muted">Am weitesten auseinander lagen die Massstäbe im {monthText(data.summary.widest_month)}: der höchste zeigte das {round(Math.exp(data.summary.widest_points / 100))}-Fache des niedrigsten. Quellen: FRED (Verbraucherpreise, Stundenlohn, M2, Rohöl, IMF-Rohstoffpreise, Minenindex), Weltbank (Gold, Monatsmittel).</p>
          </div>
          <details className="explain" data-testid="explain">
            <summary>Was heisst das?</summary>
            <ul className="small">{EXPLAIN.map((text) => <li key={text}>{text}</li>)}</ul>
          </details>
        </div>
      )}
    </div>
  );
}
