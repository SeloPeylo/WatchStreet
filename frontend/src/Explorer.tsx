// Explorer workspace: map, context panel, selection tray, scenario and timeline.
import { useEffect, useMemo, useState } from "react";
import { AssetPanel, MetricRow } from "./AssetPanel";
import type { Card, Commodity, Json } from "./api";
import { COMMODITY_LABEL, KNOWLEDGE_LABEL, STATUS_LABEL, day, get, num } from "./api";
import { KNOWLEDGE_COLORS, MapView, SCALES, SHAPES } from "./MapView";
import type { ViewState } from "./state";
import { selection, viewParams } from "./state";

const MODES: Record<string, string> = { status: "Rohstoff (neutral)", margin: "Marge", delta: "Änderung im Szenario", knowledge: "Wissensstatus", quality: "Datenqualität" };
const LAYERS = ["production", "development", "exploration", "closed"];
const SHAPE_SIGN: Record<string, string> = { circle: "●", diamond: "◆", triangle: "▲", square: "■" };

interface Props {
  state: ViewState;
  update: (change: Partial<ViewState>) => void;
  commodities: Commodity[];
  tick: number;
  refresh: () => void;
  notify: (text: string) => void;
  templates: Json[];
  theses: Json[];
}

function Legend({ mode, commodities }: { mode: string; commodities: Commodity[] }) {
  const scale = SCALES[mode];
  return (
    <div className="legend" data-testid="legend">
      <div><b>Form = Status:</b> {LAYERS.map((s) => `${SHAPE_SIGN[SHAPES[s]]} ${STATUS_LABEL[s]}`).join("  ")}</div>
      <div style={{ marginTop: 4 }}>
        <b>Farbe = {MODES[mode]}:</b>{" "}
        {mode === "status" && commodities.map((c) => <span key={c.key}><i style={{ background: c.color }} />{c.label} </span>)}
        {mode === "knowledge" && Object.entries(KNOWLEDGE_COLORS).map(([k, color]) => <span key={k}><i style={{ background: color }} />{KNOWLEDGE_LABEL[k]} </span>)}
        {scale && (
          <>
            {scale.colors.map((color, i) => <span key={color}><i style={{ background: color }} />{i === 0 ? `< ${scale.stops[0] * 100} %` : i === scale.colors.length - 1 ? `≥ ${scale.stops[i - 1] * 100} %` : ""} </span>)}
            <span><i className="hatch" />Daten fehlen</span>
          </>
        )}
      </div>
      <div className="muted">Punkt am Marker: blau = Recherche läuft · grün = neues Ergebnis · gelb = offene Frage</div>
    </div>
  );
}

function Timeline({ commodity, state, update, milestones }: { commodity: Commodity | undefined; state: ViewState; update: Props["update"]; milestones: Json[] }) {
  const [points, setPoints] = useState<{ day: string; close: number }[]>([]);
  useEffect(() => {
    if (commodity) get(`/commodities/${commodity.key}/prices`).then(setPoints);
  }, [commodity?.key]);
  if (!commodity) return <div className="timeline muted small">Rohstoff wählen, um Preisverlauf, Stichtag und Szenario zu nutzen.</div>;
  if (points.length === 0) return <div className="timeline muted small">Für {commodity.label} liegt noch kein Preisverlauf vor.</div>;
  const times = points.map((p) => Date.parse(p.day));
  const t0 = Math.min(...times, ...milestones.map((m) => Date.parse(m.day)));
  const t1 = Date.now();
  const lo = Math.min(...points.map((p) => p.close));
  const hi = Math.max(...points.map((p) => p.close));
  const x = (t: number) => ((t - t0) / (t1 - t0 || 1)) * 1000;
  const y = (v: number) => 70 - ((v - lo) / (hi - lo || 1)) * 60;
  const path = points.map((p, i) => `${i ? "L" : "M"}${x(times[i]).toFixed(1)},${y(p.close).toFixed(1)}`).join(" ");
  const pick = (e: React.MouseEvent<SVGSVGElement>) => {
    const box = e.currentTarget.getBoundingClientRect();
    const t = t0 + ((e.clientX - box.left) / box.width) * (t1 - t0);
    update({ asof: new Date(t).toISOString().slice(0, 10) });
  };
  const sorted = [...milestones].sort((a, b) => a.day.localeCompare(b.day));
  const step = (direction: 1 | -1) => {
    const current = state.asof || "9999";
    const next = direction === 1 ? sorted.find((m) => m.day > current) : [...sorted].reverse().find((m) => m.day < current);
    update({ asof: next ? next.day : "" });
  };
  const current = commodity.price ?? 0;
  const scenario = state.sc.startsWith(`${commodity.key}:`) ? Number(state.sc.split(":")[1]) : null;
  return (
    <div className="timeline" data-testid="timeline">
      <div className="row small">
        <b>{commodity.label}</b>
        <span className="muted">{commodity.price_unit}</span>
        <label>Stichtag <input type="date" value={state.asof} max={new Date().toISOString().slice(0, 10)} onChange={(e) => update({ asof: e.target.value })} /></label>
        {state.asof && (
          <>
            <select value={state.view || "as_known"} onChange={(e) => update({ view: e.target.value })} title="Welche Informationen zählen zum Stichtag?">
              <option value="as_known">wie damals bekannt</option>
              <option value="hindsight">rückblickend bekannt</option>
            </select>
            <button onClick={() => update({ asof: "", view: "" })}>Heute</button>
          </>
        )}
        {sorted.length > 0 && (
          <span className="row" title="Lebenslauf schrittweise durchlaufen">
            Replay <button onClick={() => step(-1)}>◀</button><button onClick={() => step(1)}>▶</button>
          </span>
        )}
        <span className="right row">
          Szenariopreis
          <input data-testid="scenario" type="range" min={current * 0.4} max={current * 2} step={current / 200 || 1} value={scenario ?? current}
            onChange={(e) => update({ sc: `${commodity.key}:${Number(e.target.value).toPrecision(4)}`, color: state.color && state.color !== "status" ? state.color : "margin" })} />
          <b>{(scenario ?? current).toLocaleString("de-DE", { maximumFractionDigits: 2 })}</b>
          {scenario !== null && <button onClick={() => update({ sc: "" })}>Zurücksetzen</button>}
        </span>
      </div>
      <svg viewBox="0 0 1000 86" preserveAspectRatio="none" onClick={pick}>
        <path d={path} fill="none" stroke={commodity.color} strokeWidth="1.6" vectorEffect="non-scaling-stroke" />
        {sorted.map((m) => <line key={m.id} x1={x(Date.parse(m.day))} x2={x(Date.parse(m.day))} y1="4" y2="80" stroke="var(--muted)" strokeDasharray="3 3" vectorEffect="non-scaling-stroke"><title>{m.title} ({m.day})</title></line>)}
        {state.asof && <line x1={x(Date.parse(state.asof))} x2={x(Date.parse(state.asof))} y1="0" y2="86" stroke="var(--warn)" strokeWidth="2" vectorEffect="non-scaling-stroke" />}
      </svg>
    </div>
  );
}

function Compare({ ids, state, onClose }: { ids: number[]; state: ViewState; onClose: () => void }) {
  const [data, setData] = useState<Json>(null);
  const [anchor, setAnchor] = useState("discovery");
  useEffect(() => {
    get("/compare", { ids: ids.join(","), anchor, ...viewParams(state) }).then(setData);
  }, [ids.join(","), anchor, state.asof, state.sc]);
  if (!data) return null;
  const cards: Card[] = data.cards;
  const keys = [...new Set(cards.flatMap((c) => [...c.metrics, ...c.economics].map((m) => m.metric)))];
  const find = (c: Card, key: string) => [...c.metrics, ...c.economics].find((m) => m.metric === key);
  const label = (key: string) => cards.map((c) => find(c, key)).find(Boolean)!.label;
  const bases = new Set(cards.map((c) => find(c, "aisc")?.basis).filter(Boolean));
  return (
    <div className="modal" onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} data-testid="compare">
        <div className="row"><h2>Vergleich</h2><button className="right" onClick={onClose}>Schliessen</button></div>
        {bases.size > 1 && <div className="note">Achtung: Die Kosten beruhen auf unterschiedlichen Definitionen und sind nicht direkt vergleichbar.</div>}
        <table>
          <thead><tr><th></th>{cards.map((c, i) => <th key={c.id}>{i + 1}. {c.name}<div>{STATUS_LABEL[c.status]} · {c.country}</div></th>)}</tr></thead>
          <tbody>
            {keys.map((key) => (
              <tr key={key}><th>{label(key)}</th>
                {cards.map((c) => { const m = find(c, key); return <td key={c.id}>{m ? <table><tbody><MetricRow m={{ ...m, label: "" }} /></tbody></table> : <span className="muted">–</span>}</td>; })}
              </tr>
            ))}
          </tbody>
        </table>
        <div className="row section"><h3>Lebensläufe ab gemeinsamem Anker</h3>
          <select value={anchor} onChange={(e) => setAnchor(e.target.value)}>
            <option value="discovery">Jahr 0 = Entdeckung</option><option value="feasibility">Jahr 0 = Machbarkeitsstudie</option>
            <option value="construction">Jahr 0 = Baubeginn</option><option value="first_production">Jahr 0 = Erste Produktion</option>
          </select>
        </div>
        <table><tbody>
          {data.lanes.map((lane: Json) => (
            <tr key={lane.asset_id}><th>{cards.find((c) => c.id === lane.asset_id)?.name}</th>
              <td>{lane.anchor_day ? lane.milestones.map((m: Json) => `${m.title}: Jahr ${m.years}`).join(" → ") : <span className="muted">Anker für dieses Objekt nicht erfasst</span>}</td></tr>
          ))}
        </tbody></table>
        <p className="muted small">Originalwerte; keine Inflations- oder Rohstoffäquivalent-Umrechnung.</p>
      </div>
    </div>
  );
}

export function Explorer({ state, update, commodities, tick, refresh, notify, templates, theses }: Props) {
  const [world, setWorld] = useState<Json>({ features: [], events: [] });
  const [hidden, setHidden] = useState<string[]>([]);
  const [showEvents, setShowEvents] = useState(true);
  const [comparing, setComparing] = useState(false);
  const [milestones, setMilestones] = useState<Json[]>([]);
  const mode = state.color || "status";
  const selected = selection(state);
  const active = state.a ? Number(state.a) : null;
  useEffect(() => {
    get("/map", { commodity: state.c || undefined, color: mode, ...viewParams(state) }).then(setWorld).catch((e) => notify(e.message));
  }, [state.c, mode, state.asof, state.view, state.sc, tick]);
  useEffect(() => {
    if (active) get(`/assets/${active}`).then((d) => setMilestones(d.milestones)).catch(() => setMilestones([]));
    else setMilestones([]);
  }, [active]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).matches("input, textarea, select")) return;
      if (e.key === "Escape") update({ a: "" });
      if (e.key === "c" && selected.length > 1) setComparing(true);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selected.length]);
  const features = useMemo(
    () => world.features.filter((f: Json) => !hidden.includes(f.properties.status === "care_maintenance" ? "closed" : f.properties.status)),
    [world, hidden],
  );
  const thesis = theses.find((t) => String(t.id) === state.th);
  const activeFeature = world.features.find((f: Json) => f.id === active);
  const commodity = commodities.find((c) => c.key === (state.c || activeFeature?.properties.commodity));
  const pick = (id: number, add: boolean) => {
    if (add) update({ sel: (selected.includes(id) ? selected.filter((s) => s !== id) : [...selected, id].slice(0, 8)).join(",") });
    else update({ a: String(id) });
  };
  const name = (id: number) => world.features.find((f: Json) => f.id === id)?.properties.name ?? `#${id}`;
  const [scKey, scPrice] = state.sc.split(":");
  const stress = world.summary;
  const stressText = stress && stress.producing > 0 ? ` · ${stress.under_water} von ${stress.producing - stress.unknown} Minen mit negativer Marge${stress.production_share_under_water != null ? ` (${Math.round(stress.production_share_under_water * 100)} % der Produktion)` : ""}${stress.unknown ? `, ${stress.unknown} ohne Kostendaten` : ""}` : "";
  const banner = state.sc ? `Szenario: ${COMMODITY_LABEL[scKey] ?? scKey} = ${Number(scPrice).toLocaleString("de-DE")}${stressText}${state.asof ? ` auf Datenstand ${day(state.asof)}` : ""}` : state.asof ? `Stichtag ${day(state.asof)} – ${state.view === "hindsight" ? "rückblickend bekannt" : "wie damals bekannt"}` : "";
  return (
    <div className="explorer">
      <div className="mapwrap">
        <MapView features={features} events={showEvents ? world.events : []} mode={mode} commodities={commodities} selected={selected} active={active}
          company={state.co} focus={thesis ? thesis.asset_ids : []} onPick={pick} />
        <div className="maptools">
          <label className="small">Farbe{" "}
            <select data-testid="color-mode" value={mode} onChange={(e) => update({ color: e.target.value })}>
              {Object.entries(MODES).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
            </select>
          </label>
          {LAYERS.map((layer) => (
            <label key={layer} className="small"><input type="checkbox" checked={!hidden.includes(layer)} onChange={() => setHidden(hidden.includes(layer) ? hidden.filter((h) => h !== layer) : [...hidden, layer])} /> {SHAPE_SIGN[SHAPES[layer]]} {STATUS_LABEL[layer]}</label>
          ))}
          <label className="small"><input type="checkbox" checked={showEvents} onChange={() => setShowEvents(!showEvents)} /> ◯ Ereignisse</label>
          {state.co && <button onClick={() => update({ co: "" })}>Hervorhebung aufheben</button>}
          {thesis && <div className="small">These: <b>{thesis.title}</b> <button className="link" onClick={() => update({ th: "" })}>lösen</button></div>}
          <div className="muted small">{features.length} Objekte · Umschalt+Klick wählt mehrere</div>
        </div>
        {banner && <div className="banner" data-testid="banner">{banner}</div>}
        <Legend mode={mode} commodities={commodities} />
      </div>
      <div className="tray" data-testid="tray">
        <b className="small">Auswahl</b>
        {selected.length === 0 && <span className="muted small">leer – Umschalt+Klick auf Marker oder „+ Zur Auswahl“ in der Karte</span>}
        {selected.map((id, index) => (
          <span className="item" key={id}><b>{index + 1}</b><button className="link" onClick={() => update({ a: String(id) })}>{name(id)}</button>
            <button onClick={() => update({ sel: selected.filter((s) => s !== id).join(",") })}>✕</button></span>
        ))}
        {selected.length > 1 && <button className="primary" data-testid="compare-button" onClick={() => setComparing(true)}>Vergleichen (c)</button>}
        {selected.length > 0 && <button onClick={() => update({ sel: "" })}>Leeren</button>}
      </div>
      <Timeline commodity={commodity} state={state} update={update} milestones={milestones} />
      <aside className="side">
        {active ? (
          <AssetPanel id={active} state={state} update={update} tick={tick} templates={templates} thesisTitle={thesis?.title ?? ""} onChanged={refresh} notify={notify} />
        ) : (
          <div data-testid="overview">
            <h2>Weltkarte</h2>
            <p className="muted">Rohstoff oben wählen, Marker anklicken. Jede Zahl zeigt ihre Herkunft: <b>B</b> berichtet, <b>≈</b> berechnet, <b>~</b> geschätzt, <b>?</b> unbekannt.</p>
            {world.features.length === 0 && <div className="note">Über diesen Ausschnitt liegt noch nichts vor. „Unbekannt“ heisst nicht „existiert nicht“ – Objekte entstehen durch belegte Recherche.</div>}
            {world.features.some((f: Json) => f.properties.is_demo) && <div className="note">Alle gezeigten Objekte, Werte und Ereignisse sind <b>synthetische Demo-Daten</b>.</div>}
            <h3>Thesen</h3>
            {theses.map((t) => <div key={t.id}><button className="link" onClick={() => update({ th: String(t.id), c: t.commodity })}>{t.title}</button></div>)}
            <h3 className="section">Objekte</h3>
            <table data-testid="cost-table">
              <thead><tr><th>Objekt</th><th>Status</th><th title="Stückkosten (berichtet oder geschätzt)">Kosten</th><th title="(Preis − Kosten) / Preis in dieser Ansicht">Marge</th><th>Wissen</th></tr></thead>
              <tbody>
              {[...features].sort((x: Json, y: Json) => (x.properties.unit_cost ?? Infinity) - (y.properties.unit_cost ?? Infinity)).map((f: Json) => (
                <tr key={f.id}><td><button className="link" onClick={() => update({ a: String(f.id) })}>{f.properties.name}</button></td>
                  <td className="small muted">{STATUS_LABEL[f.properties.status]}</td>
                  <td className="n">{f.properties.unit_cost != null ? num(f.properties.unit_cost) : <span className="muted">?</span>}</td>
                  <td className={`n ${f.properties.margin != null && f.properties.margin < 0 ? "down" : ""}`}>{f.properties.margin != null ? `${Math.round(f.properties.margin * 100)} %` : <span className="muted">?</span>}</td>
                  <td className="small muted">{KNOWLEDGE_LABEL[f.properties.knowledge]}</td></tr>
              ))}
              </tbody></table>
            <p className="small muted">Sortiert nach Stückkosten (niedrigste zuerst); „?“ = nicht belegt. Kosten verschiedener Rohstoffe sind nicht vergleichbar – Rohstoff oben wählen.</p>
          </div>
        )}
      </aside>
      {comparing && <Compare ids={selected} state={state} onClose={() => setComparing(false)} />}
    </div>
  );
}
