// Research workspace: thesis board, backlog with deliberate start, tickets, situation report.
import { useEffect, useState } from "react";
import type { Json } from "./api";
import { EPISTEMIC_LABEL, ticketLabel, day, get, patch, post } from "./api";
import type { ViewState } from "./state";

const PARTS: Record<string, string> = { insight: "Erkenntnisgewinn", relevance: "Relevanz", novelty: "Neuartigkeit", data: "Datenlage", investment: "Investmentnutzen" };
const ASSUMPTION: Record<string, string> = { open: "offen", supported: "gestützt", contradicted: "widerlegt", unclear: "unklar" };
const ORIGIN: Record<string, string> = { user: "von dir", engine: "Analyse-Engine", agent: "Agent" };
const SECTIONS: [string, string][] = [["uncertainties", "Unsicherheiten"], ["alternatives", "Geprüfte Alternativen"], ["not_found", "Nicht gefunden"], ["rejected", "Abgelehnte Angaben des Agenten"], ["followups", "Vorgeschlagene Folgefragen"]];

interface Props {
  update: (change: Partial<ViewState>) => void;
  tick: number;
  refresh: () => void;
  notify: (text: string) => void;
  theses: Json[];
}

function TicketResult({ id, onClose, update }: { id: number; onClose: () => void; update: Props["update"] }) {
  const [ticket, setTicket] = useState<Json>(null);
  useEffect(() => {
    get(`/tickets/${id}`).then(setTicket);
    post(`/tickets/${id}/seen`);
  }, [id]);
  if (!ticket) return null;
  const result = ticket.result ?? {};
  return (
    <div className="modal" onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} data-testid="ticket-result">
        <div className="row"><h2>{ticket.title}</h2><button className="right" onClick={onClose}>Schliessen</button></div>
        <div className="row">
          <span className={`pill ${ticket.status}`}>{ticketLabel(ticket)}</span>
          <span className="muted small">{ticket.subject_name} · Agent: {ticket.runner || "–"}{result.agent_used === false ? " (nur deterministische Schritte)" : ""}</span>
          {ticket.subject_type === "asset" && <button className="link" onClick={() => update({ path: "/", a: String(ticket.subject_id) })}>Auf der Karte zeigen</button>}
        </div>
        {ticket.error && <div className="note">{ticket.error}</div>}
        <h3 className="section">Antwort</h3>
        <div style={{ whiteSpace: "pre-wrap" }}>{result.answer || "–"}</div>
        <p className="small muted">Belegte Kennzahlen: {result.fact_ids?.length ?? 0} · Quellen: {result.sources?.length ?? 0}</p>
        {SECTIONS.map(([key, label]) => result[key]?.length > 0 && (
          <div key={key}><h3 className="section">{label}</h3><ul>{result[key].map((line: string, i: number) => <li key={i}>{line}</li>)}</ul></div>
        ))}
      </div>
    </div>
  );
}

export function Research({ update, tick, refresh, notify, theses }: Props) {
  const [proposals, setProposals] = useState<Json[]>([]);
  const [tickets, setTickets] = useState<Json[]>([]);
  const [report, setReport] = useState<Json>({ changes: [] });
  const [since, setSince] = useState("");
  const [checked, setChecked] = useState<number[]>([]);
  const [open, setOpen] = useState<number | null>(null);
  const [thesisId, setThesisId] = useState<number | null>(null);
  const [draft, setDraft] = useState({ title: "", statement: "", horizon: "", commodity: "", assumption: "", criterion: "", review_by: "" });
  useEffect(() => {
    get("/proposals").then(setProposals);
    get("/tickets").then(setTickets);
    get("/changes", { since: since ? `${since}T00:00:00Z` : undefined }).then(setReport);
  }, [tick, since]);
  const act = async (run: () => Promise<Json>, text: string) => {
    try {
      await run();
      notify(text);
      refresh();
    } catch (error) {
      notify((error as Error).message);
    }
  };
  const thesis = theses.find((t) => t.id === thesisId) ?? theses[0];
  // A judgement needs a reason, so it can be checked against reality later.
  const judge = (a: Json, status: string) => {
    const reason = window.prompt(`Begründung für „${ASSUMPTION[status]}“:`, "") ?? "";
    if (!reason.trim()) return notify("Ohne Begründung wird der Status nicht geändert");
    return act(() => patch(`/assumptions/${a.id}`, { status, reason }), "Annahme eingeordnet");
  };
  const retest = (a: Json) => {
    const criterion = window.prompt("Welche Beobachtung würde die Annahme widerlegen?", a.criterion);
    if (criterion === null) return;
    const review = window.prompt("Prüfen bis (JJJJ-MM-TT, leer = kein Datum):", a.review_by ?? "");
    return act(() => patch(`/assumptions/${a.id}`, { criterion, review_by: review || null }), "Kriterium gespeichert");
  };
  const start = (ids: number[]) => act(() => post("/proposals/start", { ids }), `${ids.length} Recherche(n) gestartet`).then(() => setChecked([]));
  return (
    <div className="page"><div className="cols">
      <div className="box" data-testid="theses">
        <h2>Thesen</h2>
        <div className="row">{theses.map((t) => <button key={t.id} className={t.id === thesis?.id ? "primary" : ""} onClick={() => setThesisId(t.id)}>{t.title}</button>)}</div>
        {thesis && (
          <div className="section">
            <div className="row"><b>{thesis.title}</b>{thesis.is_demo && <span className="demo">synthetisch</span>}</div>
            <p>{thesis.statement}</p>
            <p className="small muted">Zeithorizont: {thesis.horizon || "–"} · {thesis.asset_ids.length} verknüpfte Objekte</p>
            <button onClick={() => update({ path: "/", th: String(thesis.id), c: thesis.commodity, a: "" })}>Auf der Karte zeigen</button>
            <h3 className="section">Annahmen</h3>
            {thesis.assumptions.map((a: Json) => (
              <div key={a.id} style={{ marginBottom: 8 }} data-assumption={a.id}>
                <div className="row">
                  <select value={a.status} onChange={(e) => judge(a, e.target.value)}>
                    {Object.entries(ASSUMPTION).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
                  </select>
                  <span className="grow">{a.text}</span>
                </div>
                <div className="small muted">
                  Widerlegt, wenn: {a.criterion || <i>kein Kriterium – so ist die Annahme nicht prüfbar</i>}
                  {a.review_by && <> · prüfen bis {day(a.review_by)}{a.review_due && <b style={{ color: "var(--warn)" }}> (fällig)</b>}</>}
                  {" · "}Evidenz: {a.supports} stützend, {a.contradicts} widersprechend{a.contradicts === 0 && a.status === "supported" ? " – kein Gegenargument geprüft" : ""}
                  {a.contradicts > 0 && a.status === "supported" && <b> · ⚠ gestützt trotz Gegenevidenz</b>}
                  {a.status !== "open" && a.supports + a.contradicts === 0 && <b> · ⚠ eingeordnet ohne Evidenz</b>}
                  {a.status !== "open" && !a.criterion && <b> · ⚠ kein Kriterium</b>}
                  {a.status_reason && <> · Begründung: {a.status_reason}</>}
                  {" "}<button className="link" onClick={() => retest(a)}>Kriterium ändern</button>
                </div>
              </div>
            ))}
            <div className="row">
              <input className="grow" placeholder="neue Annahme" value={draft.assumption} onChange={(e) => setDraft({ ...draft, assumption: e.target.value })} />
              <input className="grow" placeholder="widerlegt, wenn …" value={draft.criterion} onChange={(e) => setDraft({ ...draft, criterion: e.target.value })} />
              <input type="date" title="prüfen bis" value={draft.review_by} onChange={(e) => setDraft({ ...draft, review_by: e.target.value })} />
              <button onClick={() => act(() => post(`/theses/${thesis.id}/assumptions`, { text: draft.assumption, criterion: draft.criterion, review_by: draft.review_by || null }), "Annahme ergänzt").then(() => setDraft({ ...draft, assumption: "", criterion: "", review_by: "" }))}>+</button>
            </div>
            <h3 className="section">Evidenz</h3>
            {thesis.links.filter((l: Json) => l.target_type !== "asset").length === 0 && <p className="muted small">Noch keine Erkenntnis zugeordnet. Ergebnisse von Recherchen, die aus dieser These heraus vorgemerkt wurden, erscheinen hier.</p>}
            {thesis.links.filter((l: Json) => l.target_type !== "asset").map((l: Json) => (
              <div key={l.id} className="row small">
                <select value={l.stance} onChange={(e) => act(() => post(`/theses/${thesis.id}/links`, { target_type: l.target_type, target_id: l.target_id, stance: e.target.value }), "Einordnung gespeichert")}>
                  <option value="supports">stützt</option><option value="contradicts">widerspricht</option><option value="context">Kontext</option>
                </select>
                <select value={l.assumption_id ?? ""} title="Auf welche Annahme bezieht sich das?" onChange={(e) => act(() => post(`/theses/${thesis.id}/links`, { target_type: l.target_type, target_id: l.target_id, stance: l.stance, assumption_id: e.target.value ? Number(e.target.value) : null }), "Annahme zugeordnet")}>
                  <option value="">zur These allgemein</option>
                  {thesis.assumptions.map((a: Json) => <option key={a.id} value={a.id}>{a.text.slice(0, 40)}</option>)}
                </select>
                {l.finding ? (
                  <span className="grow"><span className={`pill ${l.finding.epistemic}`}>{EPISTEMIC_LABEL[l.finding.epistemic]}</span> {l.finding.text.slice(0, 220)}{" "}
                    {l.finding.subject_type === "asset" && <button className="link" onClick={() => update({ path: "/", a: String(l.finding.subject_id) })}>zum Objekt</button>}</span>
                ) : l.fact ? (
                  <span className="grow"><span className="pill">Kennzahl</span> {l.fact.display}{l.fact.document ? ` – ${l.fact.document.title}` : ""}</span>
                ) : <span>Dokument #{l.target_id}</span>}
              </div>
            ))}
          </div>
        )}
        <h3 className="section">Neue These</h3>
        <input placeholder="Titel" value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} style={{ width: "100%", marginBottom: 4 }} />
        <textarea placeholder="Aussage" value={draft.statement} onChange={(e) => setDraft({ ...draft, statement: e.target.value })} />
        <div className="row" style={{ marginBottom: 6 }}>
          <input placeholder="Zeithorizont, z. B. 5 Jahre" value={draft.horizon} onChange={(e) => setDraft({ ...draft, horizon: e.target.value })} />
          <select value={draft.commodity} onChange={(e) => setDraft({ ...draft, commodity: e.target.value })}>
            <option value="">kein Rohstoff</option><option value="gold">Gold</option><option value="silver">Silber</option><option value="copper">Kupfer</option><option value="uranium">Uran</option>
          </select>
        </div>
        <button onClick={() => act(async () => { const made = await post("/theses", draft); setThesisId(made.id); }, "These angelegt").then(() => setDraft({ title: "", statement: "", horizon: "", commodity: "", assumption: "", criterion: "", review_by: "" }))}>Anlegen</button>
      </div>

      <div>
        <div className="box" data-testid="backlog">
          <div className="row"><h2>Backlog – Vorschläge</h2>
            <button className="primary right" disabled={checked.length === 0} onClick={() => start(checked)}>Ausgewählte starten ({checked.length})</button></div>
          <p className="muted small">Nichts läuft, bevor du es startest. Der Nutzenwert sortiert nur; er verwirft nichts.</p>
          {proposals.length === 0 && <p className="muted">Keine offenen Vorschläge.</p>}
          <div className="cardlist">
            {proposals.map((p) => (
              <div key={p.id} data-proposal={p.id}>
                <div className="row small muted">
                  <input type="checkbox" checked={checked.includes(p.id)} onChange={() => setChecked(checked.includes(p.id) ? checked.filter((c) => c !== p.id) : [...checked, p.id])} />
                  <span>{p.template_label} · {ORIGIN[p.origin]}</span>
                  <button className="link" onClick={() => update({ path: "/", a: String(p.subject_id) })}>{p.subject_name}</button>
                  <span className="right" title={Object.entries(p.value_parts).map(([k, v]) => `${PARTS[k]}: ${v}`).join("\n")}>Nutzen {p.value_score.toFixed(2)} ⓘ</span>
                </div>
                <textarea defaultValue={p.question} onBlur={(e) => e.target.value !== p.question && act(() => patch(`/proposals/${p.id}`, { question: e.target.value }), "Auftrag geändert")} />
                <div className="row"><button className="primary" onClick={() => start([p.id])}>Starten</button>
                  <button onClick={() => act(() => post(`/proposals/${p.id}/dismiss`), "Vorschlag verworfen")}>Verwerfen</button></div>
              </div>
            ))}
          </div>
        </div>
        <div className="box section" data-testid="tickets">
          <h2>Recherchen</h2>
          {tickets.length === 0 && <p className="muted">Noch keine Recherche gestartet.</p>}
          <table><tbody>
            {tickets.map((t) => (
              <tr key={t.id}>
                <td><span className={`pill ${t.status}`}>{ticketLabel(t)}</span></td>
                <td><button className="link" onClick={() => setOpen(t.id)}>{t.title}</button><div className="small muted">{t.subject_name} · {t.summary.slice(0, 120)}</div></td>
                <td>{t.status === "failed" && <button onClick={() => act(() => post(`/tickets/${t.id}/retry`), "Erneut eingereiht")}>Wiederholen</button>}
                  {t.status === "queued" && <button onClick={() => act(() => post(`/tickets/${t.id}/cancel`), "Abgebrochen")}>Abbrechen</button>}</td>
              </tr>
            ))}
          </tbody></table>
        </div>
      </div>

      <div className="box" data-testid="report">
        <h2>Seit deinem letzten Besuch</h2>
        <div className="row small">
          <span className="muted">{report.last_visit ? `Letzter Besuch: ${day(report.last_visit)}` : "Noch kein Besuch markiert"}</span>
          <label>ab <input type="date" value={since} onChange={(e) => setSince(e.target.value)} /></label>
          <button onClick={() => act(() => post("/visits"), "Als gelesen markiert")}>Als gelesen markieren</button>
        </div>
        {report.changes.length === 0 && <p className="muted">Keine Änderungen in diesem Zeitraum.</p>}
        <table><tbody>
          {report.changes.map((c: Json) => (
            <tr key={c.id}>
              <td className="small muted">{day(c.at)}</td>
              <td><button className="link" onClick={() => c.subject_type === "asset" && update({ path: "/", a: String(c.subject_id) })}>{c.subject_name}</button>
                <div className="small">{c.summary}{c.old && <span className="muted"> (vorher: {c.old})</span>}</div></td>
            </tr>
          ))}
        </tbody></table>
        <p className="small muted">{Object.values(EPISTEMIC_LABEL).join(" · ")}: Erkenntnisse tragen immer ihren Belegstatus.</p>
      </div>
    </div>
    {open !== null && <TicketResult id={open} update={update} onClose={() => { setOpen(null); refresh(); }} />}
    </div>
  );
}
