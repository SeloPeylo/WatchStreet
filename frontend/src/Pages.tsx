// Smaller pages: portfolio, sources, system, manual.
import { useEffect, useState } from "react";
import type { Json } from "./api";
import { day, del, get, num, patch, post, put } from "./api";

type Notify = (text: string) => void;
const STATE: Record<string, string> = { open: "offen", supported: "gestützt", contradicted: "widerlegt", unclear: "unklar" };

export function Portfolio({ notify }: { notify: Notify }) {
  const [data, setData] = useState<Json>({ holdings: [], watchlist: [] });
  const empty = { symbol: "", quantity: "", avg_price: "", bought_at: "", intent: "", thesis_id: "", exit_condition: "" };
  const [holding, setHolding] = useState(empty);
  const [theses, setTheses] = useState<Json[]>([]);
  const [journal, setJournal] = useState<Json[]>([]);
  const [watch, setWatch] = useState({ symbol: "", note: "" });
  const load = () => { get("/portfolio/decisions").then(setJournal); return get("/portfolio").then(setData); };
  useEffect(() => { load(); get("/theses").then(setTheses); }, []);
  const adjust = (h: Json) => {
    const exit_condition = window.prompt("Ausstiegsbedingung: Was müsste eintreten, damit du verkaufst?", h.exit_condition ?? "");
    if (exit_condition === null) return;
    const reason = window.prompt("Warum änderst du sie? (steht im Entscheidungsprotokoll)", "") ?? "";
    if (!reason.trim()) return notify("Ohne Begründung wird nichts geändert");
    act(patch(`/portfolio/holdings/${h.id}`, { exit_condition, reason }));
  };
  const sell = (h: Json) => {
    const reason = window.prompt(`Warum schliesst du ${h.symbol}? (steht im Entscheidungsprotokoll)`, "") ?? "";
    if (!reason.trim()) return notify("Ohne Begründung wird die Position nicht geschlossen");
    const price = Number(window.prompt("Verkaufspreis je Stück (leer lassen, wenn unbekannt)", "") ?? "");
    act(post(`/portfolio/holdings/${h.id}/sell`, { reason, ...(price > 0 ? { price } : {}) }));
  };
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
                  <div className="small">{h.thesis ? <>These: <b>{h.thesis.title}</b>{h.thesis.contradicted ? ` ⚠ ${h.thesis.contradicted} Annahme(n) widerlegt` : ""}{h.thesis.due ? ` · ${h.thesis.due} Prüfung(en) fällig` : ""}</> : <span className="muted">⚠ keiner These zugeordnet</span>}</div>
                  <div className="small">{h.exit_condition ? <>Ausstieg: {h.exit_condition}</> : <span className="muted">⚠ keine Ausstiegsbedingung</span>}</div>
                  <div className="small muted">{h.company ? <>{h.company.name} · {h.assets.length} Objekte{h.theses.length > 0 && <> · Thesen: {h.theses.map((t: Json) => `${t.title}${t.contradicted ? ` (⚠ ${t.contradicted} Annahme(n) widerlegt)` : ""}${t.due ? ` (${t.due} Prüfung(en) fällig)` : ""}`).join(", ")}</>}</> : "kein Unternehmen mit Objekten zugeordnet"}</div></td>
                <td><button onClick={() => adjust(h)}>Ausstieg ändern</button> <button onClick={() => sell(h)}>Schliessen</button></td></tr>
            ))}
            {data.holdings.length === 0 && <tr><td colSpan={9} className="muted">Noch keine Bestände.</td></tr>}
          </tbody>
        </table>
        <div className="row section">
          <input placeholder="Symbol" value={holding.symbol} onChange={(e) => setHolding({ ...holding, symbol: e.target.value })} />
          <input placeholder="Stück" type="number" value={holding.quantity} onChange={(e) => setHolding({ ...holding, quantity: e.target.value })} />
          <input placeholder="Ø Kaufpreis" type="number" value={holding.avg_price} onChange={(e) => setHolding({ ...holding, avg_price: e.target.value })} />
          <input type="date" title="Kaufdatum (optional)" value={holding.bought_at} onChange={(e) => setHolding({ ...holding, bought_at: e.target.value })} />
        </div>
        <div className="row">
          <select value={holding.thesis_id} onChange={(e) => setHolding({ ...holding, thesis_id: e.target.value })} data-testid="holding-thesis">
            <option value="">These wählen …</option>
            {theses.map((t) => <option key={t.id} value={t.id}>{t.title}</option>)}
          </select>
          <input className="grow" placeholder="Warum kaufst du? (Absicht)" value={holding.intent} onChange={(e) => setHolding({ ...holding, intent: e.target.value })} />
          <input className="grow" placeholder="Ausstiegsbedingung: Was müsste eintreten, damit du verkaufst?" value={holding.exit_condition} onChange={(e) => setHolding({ ...holding, exit_condition: e.target.value })} />
          <button className="primary" onClick={() => act(post("/portfolio/holdings", { ...holding, quantity: Number(holding.quantity), avg_price: Number(holding.avg_price), bought_at: holding.bought_at || null, thesis_id: holding.thesis_id ? Number(holding.thesis_id) : null })).then(() => setHolding(empty))}>Hinzufügen</button>
        </div>
      </div>
      <div className="box section" data-testid="journal">
        <h2>Entscheidungsprotokoll</h2>
        <p className="muted small">Jeder Kauf, jede Änderung und jeder Verkauf mit Begründung und dem, was damals bekannt war. Einträge lassen sich nicht ändern.</p>
        <table><tbody>
          {journal.map((d) => (
            <tr key={d.id}>
              <td>{day(d.day)}</td><td><b>{d.symbol}</b></td><td>{{ buy: "Kauf", sell: "Verkauf", adjust: "Änderung" }[d.kind as string]}</td>
              <td className="n">{d.quantity != null ? `${num(d.quantity)} Stück` : ""}{d.price != null ? ` zu ${num(d.price)}` : ""}</td>
              <td>{d.reason || <span className="muted">ohne Begründung</span>}
                <div className="small muted">Damals: Kurs {num(d.snapshot.price)}{d.snapshot.thesis ? ` · These „${d.snapshot.thesis.title}“ (${d.snapshot.thesis.assumptions.map((a: Json) => `${a.text}: ${STATE[a.status] ?? a.status}`).join("; ") || "ohne Annahmen"})` : " · ohne These"}{Object.keys(d.snapshot.figures ?? {}).length > 0 ? ` · ${Object.entries(d.snapshot.figures).map(([k, v]) => `${k} ${v}`).join(", ")}` : ""}</div></td>
            </tr>
          ))}
          {journal.length === 0 && <tr><td className="muted">Noch keine Entscheidung protokolliert.</td></tr>}
        </tbody></table>
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

const IMPORT_EXAMPLE = "name;company;commodity;country;lat;lon;status;production;aisc;reserves\nMina Ejemplo;Ejemplo Mining;copper;Chile;-23.5;-69.1;production;120000000;1.85;2400000000";

function ImportBox({ notify, onDone }: { notify: Notify; onDone: () => void }) {
  const [form, setForm] = useState({ title: "", source: "", text: "" });
  const [report, setReport] = useState<Json>(null);
  const [open, setOpen] = useState<Json[]>([]);
  const load = () => get("/imports/unverified").then(setOpen);
  useEffect(() => { load(); }, []);
  const run = (call: Promise<Json>, text?: string) => call.then((r) => { if (text) notify(text); load(); onDone(); return r; }).catch((e) => notify(e.message));
  const upload = (file: File | undefined) => file?.text().then((text) => setForm({ ...form, text, title: form.title || file.name }));
  return (
    <div className="box" data-testid="import">
      <h2>Analyse importieren</h2>
      <p className="muted small">Tabelle einfügen oder Datei wählen (CSV, TSV, „;“ oder Markdown-Tabelle). Die Kopfzeile nennt mindestens <code>name</code>; neue Objekte brauchen <code>lat</code>, <code>lon</code> und <code>commodity</code>. Alles erscheint sofort als „ungeprüft“ und überschreibt nie belegte oder eigene Angaben.</p>
      <div className="row">
        <input placeholder="Titel" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
        <input placeholder="Quelle, z. B. Newsletter" value={form.source} onChange={(e) => setForm({ ...form, source: e.target.value })} />
        <input type="file" accept=".csv,.tsv,.txt,.md" onChange={(e) => upload(e.target.files?.[0])} data-testid="import-file" />
      </div>
      <textarea rows={6} style={{ width: "100%" }} placeholder={IMPORT_EXAMPLE} value={form.text} onChange={(e) => setForm({ ...form, text: e.target.value })} data-testid="import-text" />
      <div className="row">
        <button className="primary" disabled={form.text.trim().length < 20} onClick={() => run(post("/imports", form)).then((r) => r && setReport(r))} data-testid="import-run">Importieren</button>
        <button onClick={() => setForm({ ...form, text: IMPORT_EXAMPLE })}>Beispiel einsetzen</button>
      </div>
      {report && (
        <div className="note" data-testid="import-report">
          <b>{report.created} neue, {report.matched} bekannte Objekte · {report.facts} Angaben übernommen · {report.unchanged} unverändert</b>
          {report.ticket_id && <div>Kein Tabellenformat erkannt: Der Agent zerlegt den Text (Recherche #{report.ticket_id}).</div>}
          {report.conflicts.map((line: string) => <div key={line} className="small">Abweichung: {line}</div>)}
          {report.skipped.map((line: string) => <div key={line} className="small muted">Übersprungen: {line}</div>)}
        </div>
      )}
      <h3>Ungeprüfte Angaben ({open.length})</h3>
      {open.length > 0 && (
        <div className="row">
          <button onClick={() => run(post("/imports/verify"), "Prüfungen vorgemerkt – im Research-Backlog starten")}>Prüfung gegen Primärquellen für alle vormerken</button>
          <span className="muted small">Zuerst sucht das System die Zahl ohne Agent in den gespeicherten Primärdokumenten.</span>
        </div>
      )}
      <table data-testid="unverified"><tbody>
        {open.map((f) => (
          <tr key={f.fact_id}>
            <td>{f.name}</td><td>{f.label}</td><td className="n">{f.display}</td><td className="small muted">{f.document}</td>
            <td><button className="link small" onClick={() => run(post(`/facts/${f.fact_id}/confirm`), "Bestätigt")}>bestätigen</button> · <button className="link small" onClick={() => run(post(`/facts/${f.fact_id}/retract`), "Storniert")}>stornieren</button></td>
          </tr>
        ))}
        {open.length === 0 && <tr><td className="muted">Nichts offen.</td></tr>}
      </tbody></table>
    </div>
  );
}

export function Sources({ notify }: { notify: Notify }) {
  const [documents, setDocuments] = useState<Json[]>([]);
  const [open, setOpen] = useState<Json>(null);
  const load = () => get("/documents").then(setDocuments);
  useEffect(() => { load(); }, []);
  return (
    <div className="page"><ImportBox notify={notify} onDone={load} /><div className="box" data-testid="sources">
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

const RUNNER_LABEL: Record<string, string> = { offline: "kein Agent (nur deterministische Schritte)", anthropic: "Anthropic-API (Schlüssel)", openai: "OpenAI-kompatibler Server (eigene Hardware: Ollama, llama.cpp, vLLM – oder ein API-Anbieter)" };

function AgentBox({ notify, onChanged }: { notify: Notify; onChanged: () => void }) {
  const [view, setView] = useState<Json>(null);
  const [form, setForm] = useState({ runner: "offline", model: "", base_url: "", api_key: "" });
  const apply = (v: Json) => { setView(v); setForm({ runner: v.runner in RUNNER_LABEL ? v.runner : "offline", model: v.model, base_url: v.base_url, api_key: "" }); };
  useEffect(() => { get("/system/agent").then(apply); }, []);
  if (!view) return null;
  const save = () => put("/system/agent", form).then((v) => { apply(v); notify("Agent gespeichert"); onChanged(); }).catch((e) => notify(e.message));
  const test = () => post("/system/agent/test").then((r) => notify(r.ok ? `Agent antwortet: ${r.detail}` : `Agent nicht erreichbar: ${r.detail}`)).catch((e) => notify(e.message));
  return (
    <div className="box" data-testid="agent" style={{ maxWidth: 720 }}>
      <h2>Agent</h2>
      <p className="muted small">Aktiv: <b>{view.active}</b> ({view.source === "runtime" ? "hier eingestellt" : "aus der Server-Konfiguration"}). Recherchen laufen nur, wenn du sie startest. Der Schlüssel wird in der Datenbank dieses Servers gespeichert und nie wieder angezeigt.</p>
      <div className="row">
        <select value={form.runner} onChange={(e) => setForm({ ...form, runner: e.target.value })} data-testid="agent-runner">
          {view.choices.map((key: string) => <option key={key} value={key}>{RUNNER_LABEL[key]}</option>)}
        </select>
      </div>
      {form.runner !== "offline" && (
        <>
          <div className="row">
            <input className="grow" placeholder={form.runner === "anthropic" ? "Modell, z. B. claude-haiku-5-5 (günstig)" : "Modell, z. B. qwen2.5:7b"} value={form.model} onChange={(e) => setForm({ ...form, model: e.target.value })} />
            {form.runner === "openai" && <input className="grow" placeholder="Adresse, z. B. http://host.docker.internal:11434/v1" value={form.base_url} onChange={(e) => setForm({ ...form, base_url: e.target.value })} />}
          </div>
          <div className="row">
            <input className="grow" type="password" autoComplete="off" placeholder={view.has_key ? "Schlüssel gespeichert – leer lassen, um ihn zu behalten" : "API-Schlüssel (für lokale Server leer)"} value={form.api_key} onChange={(e) => setForm({ ...form, api_key: e.target.value })} />
          </div>
        </>
      )}
      <div className="row"><button className="primary" onClick={save}>Speichern</button><button onClick={test}>Verbindung testen</button></div>
    </div>
  );
}

export function System({ notify, tick }: { notify: Notify; tick: number }) {
  const [system, setSystem] = useState<Json>(null);
  const load = () => get("/system").then(setSystem);
  useEffect(() => { load(); }, [tick]);
  if (!system) return null;
  const rows: [string, string][] = [
    ["Datenmodus", system.is_demo ? "Demo (synthetische Daten)" : "Echtdaten"],
    ["Marktdaten", system.market],
    ["Agent", system.agent_available ? system.runner : "keiner – nur deterministische Schritte"],
    ["Worker", system.worker_alive ? "läuft" : "nicht erreichbar"],
    ["Letzter Hintergrundlauf", day(system.last_scan)],
    ["Objekte / Dokumente", `${system.assets} / ${system.documents}`],
    ["Ungeprüfte importierte Angaben", String(system.unverified)],
    ["Recherchen", Object.entries(system.tickets).map(([k, v]) => `${k}: ${v}`).join(" · ")],
  ];
  return (
    <div className="page"><AgentBox notify={notify} onChanged={load} /><div className="box" data-testid="system" style={{ maxWidth: 720 }}>
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
