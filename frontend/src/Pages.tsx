// Smaller pages: portfolio, sources, system, manual.
import { useEffect, useState } from "react";
import type { Json } from "./api";
import { day, del, get, num, post } from "./api";

type Notify = (text: string) => void;

export function Portfolio({ notify }: { notify: Notify }) {
  const [data, setData] = useState<Json>({ holdings: [], watchlist: [] });
  const [holding, setHolding] = useState({ symbol: "", quantity: "", avg_price: "", bought_at: "", intent: "" });
  const [watch, setWatch] = useState({ symbol: "", note: "" });
  const load = () => get("/portfolio").then(setData);
  useEffect(() => { load(); }, []);
  const act = (run: Promise<Json>) => run.then(load).catch((e) => notify(e.message));
  return (
    <div className="page">
      <div className="box" data-testid="holdings">
        <h2>Bestände</h2>
        <table>
          <thead><tr><th>Symbol</th><th>Name</th><th>Stück</th><th>Ø Kaufpreis</th><th>Kurs</th><th>Wert</th><th>G/V</th><th>Absicht und Bezug</th><th></th></tr></thead>
          <tbody>
            {data.holdings.map((h: Json) => (
              <tr key={h.id}><td><b>{h.symbol}</b></td><td>{h.name}</td><td className="n">{num(h.quantity)}</td><td className="n">{num(h.avg_price)}</td>
                <td className="n">{num(h.price)}</td><td className="n">{num(h.market_value)} {h.currency}</td>
                <td className={`n ${h.pnl_abs >= 0 ? "up" : "down"}`}>{num(h.pnl_abs)} ({num(h.pnl_pct)} %)</td><td>{h.intent}
                  <div className="small muted">{h.company ? <>{h.company.name} · {h.assets.length} Objekte{h.theses.length > 0 && <> · Thesen: {h.theses.map((t: Json) => t.title).join(", ")}</>}</> : "kein Unternehmen mit Objekten zugeordnet"}</div></td>
                <td><button onClick={() => act(del(`/portfolio/holdings/${h.id}`))}>Entfernen</button></td></tr>
            ))}
            {data.holdings.length === 0 && <tr><td colSpan={9} className="muted">Noch keine Bestände.</td></tr>}
          </tbody>
        </table>
        <div className="row section">
          <input placeholder="Symbol" value={holding.symbol} onChange={(e) => setHolding({ ...holding, symbol: e.target.value })} />
          <input placeholder="Stück" type="number" value={holding.quantity} onChange={(e) => setHolding({ ...holding, quantity: e.target.value })} />
          <input placeholder="Ø Kaufpreis" type="number" value={holding.avg_price} onChange={(e) => setHolding({ ...holding, avg_price: e.target.value })} />
          <input type="date" title="Kaufdatum (optional)" value={holding.bought_at} onChange={(e) => setHolding({ ...holding, bought_at: e.target.value })} />
          <input className="grow" placeholder="Absicht (optional)" value={holding.intent} onChange={(e) => setHolding({ ...holding, intent: e.target.value })} />
          <button className="primary" onClick={() => act(post("/portfolio/holdings", { ...holding, quantity: Number(holding.quantity), avg_price: Number(holding.avg_price), bought_at: holding.bought_at || null }))}>Hinzufügen</button>
        </div>
      </div>
      <div className="box section" data-testid="watchlist">
        <h2>Watchlist</h2>
        <table><tbody>
          {data.watchlist.map((w: Json) => (
            <tr key={w.id}><td><b>{w.symbol}</b></td><td>{w.name}</td><td className="n">{num(w.price)}</td><td>{w.note}</td>
              <td><button onClick={() => act(del(`/portfolio/watch/${w.id}`))}>Entfernen</button></td></tr>
          ))}
          {data.watchlist.length === 0 && <tr><td className="muted">Noch nichts auf der Watchlist.</td></tr>}
        </tbody></table>
        <div className="row section">
          <input placeholder="Symbol" value={watch.symbol} onChange={(e) => setWatch({ ...watch, symbol: e.target.value })} />
          <input className="grow" placeholder="Notiz (optional)" value={watch.note} onChange={(e) => setWatch({ ...watch, note: e.target.value })} />
          <button className="primary" onClick={() => act(post("/portfolio/watch", watch))}>Beobachten</button>
        </div>
      </div>
    </div>
  );
}

export function Sources() {
  const [documents, setDocuments] = useState<Json[]>([]);
  const [open, setOpen] = useState<Json>(null);
  useEffect(() => { get("/documents").then(setDocuments); }, []);
  return (
    <div className="page"><div className="box" data-testid="sources">
      <h2>Quellen</h2>
      <p className="muted small">Agenten lesen nur gespeicherte Dokumente. Jede berichtete Kennzahl verweist auf ein wörtliches Zitat aus einem dieser Dokumente.</p>
      <table>
        <thead><tr><th>Titel</th><th>Herausgeber</th><th>Veröffentlicht</th><th>Umfang</th></tr></thead>
        <tbody>
          {documents.map((d) => (
            <tr key={d.id}><td><button className="link" onClick={() => get(`/documents/${d.id}`).then(setOpen)}>{d.title}</button> {d.is_demo && <span className="demo">synthetisch</span>}</td>
              <td>{d.publisher}</td><td>{day(d.published_at)}</td><td className="n">{num(d.chars)} Zeichen</td></tr>
          ))}
          {documents.length === 0 && <tr><td className="muted">Noch keine Dokumente. Am Objekt lässt sich ein Bericht per URL hinzufügen.</td></tr>}
        </tbody>
      </table>
      {open && (
        <div className="modal" onClick={() => setOpen(null)}><div onClick={(e) => e.stopPropagation()}>
          <div className="row"><h2>{open.title}</h2><button className="right" onClick={() => setOpen(null)}>Schliessen</button></div>
          <p className="small muted">{open.url}</p><pre style={{ whiteSpace: "pre-wrap" }}>{open.text}</pre>
        </div></div>
      )}
    </div></div>
  );
}

export function System({ notify, tick }: { notify: Notify; tick: number }) {
  const [system, setSystem] = useState<Json>(null);
  useEffect(() => { get("/system").then(setSystem); }, [tick]);
  if (!system) return null;
  const rows: [string, string][] = [
    ["Datenmodus", system.is_demo ? "Demo (synthetische Daten)" : "Echtdaten"],
    ["Marktdaten", system.market],
    ["Agent", system.agent_available ? system.runner : "keiner – nur deterministische Schritte"],
    ["Worker", system.worker_alive ? "läuft" : "nicht erreichbar"],
    ["Letzter Hintergrundlauf", day(system.last_scan)],
    ["Objekte / Dokumente", `${system.assets} / ${system.documents}`],
    ["Recherchen", Object.entries(system.tickets).map(([k, v]) => `${k}: ${v}`).join(" · ")],
  ];
  return (
    <div className="page"><div className="box" data-testid="system" style={{ maxWidth: 720 }}>
      <h2>System</h2>
      <table><tbody>{rows.map(([label, value]) => <tr key={label}><th>{label}</th><td>{value}</td></tr>)}</tbody></table>
      <div className="row section">
        <button onClick={() => post("/system/scan").then(() => notify("Hintergrundlauf angefordert (Preise, Ereignisse, Regelprüfung)"))}>Hintergrundlauf jetzt</button>
        <span className="muted small">Der Hintergrundlauf startet nie einen Agenten; er erzeugt nur Vorschläge.</span>
      </div>
    </div></div>
  );
}

export function Manual() {
  const [html, setHtml] = useState("");
  useEffect(() => { get("/manual").then((d) => setHtml(d.html)).catch(() => setHtml("<p>Handbuch nicht gefunden.</p>")); }, []);
  // The manual is the project's own Markdown file rendered by the server, not user input.
  return <div className="page"><div className="box manual" data-testid="manual" dangerouslySetInnerHTML={{ __html: html }} /></div>;
}
