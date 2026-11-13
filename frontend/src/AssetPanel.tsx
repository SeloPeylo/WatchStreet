// Context panel for one asset: the character card first, depth on demand.
import { useEffect, useState } from "react";
import type { Card, Json, Metric } from "./api";
import { CLAIM_LABEL, COMMODITY_LABEL, EPISTEMIC_LABEL, KNOWLEDGE_LABEL, METHOD_LABEL, ORIGIN_LABEL, PROVENANCE, STATUS_LABEL, TICKET_LABEL, day, get, metricText, post } from "./api";
import type { ViewState } from "./state";
import { selection, viewParams } from "./state";

export function Chip({ m }: { m: Metric }) {
  const p = PROVENANCE[m.provenance];
  const claim = m.claim_kind ? ` · ${CLAIM_LABEL[m.claim_kind] ?? m.claim_kind}` : "";
  // An imported or merely self-confirmed figure must not carry the sign of a sourced one.
  const weak = m.provenance === "reported" && (m.unverified || m.own_claim);
  return (
    <span className={`prov ${weak ? "unknown" : m.provenance}`} title={weak ? (m.own_claim ? "Eigene Annahme: von dir bestätigt, ohne Primärquelle" : "Übernommen aus einer importierten Analyse, nicht geprüft") : `${p.label}${claim}`}>
      {weak ? (m.own_claim ? "E" : "N") : p.chip}
    </span>
  );
}

export function MetricRow({ m, onOpen, action }: { m: Metric; onOpen?: () => void; action?: React.ReactNode }) {
  const forecast = m.claim_kind === "guidance" || m.claim_kind === "hypothesis";
  return (
    <tr className={onOpen ? "metric" : ""} onClick={onOpen} data-metric={m.metric}>
      <td>
        <Chip m={m} />
        {m.label}
      </td>
      <td className={`n ${forecast ? "forecast" : ""}`}>
        {metricText(m)}
        {m.stale && <span title="veraltet"> ⚠</span>}
        {m.unverified && <span className="pill unresolved" title="Stammt aus einer importierten Analyse oder beruht darauf; noch nicht gegen eine Primärquelle geprüft"> ungeprüft</span>}
        {m.own_claim && <span className="pill unresolved" title="Von dir bestätigt, ohne Primärquelle"> eigene Annahme</span>}
        {action}
        {m.provenance !== "unknown" && (
          <div className="muted small">
            {m.period_end ? `Stand ${m.period_end.slice(0, 4)}` : m.published_at ? `veröffentlicht ${m.published_at.slice(0, 4)}, Zeitraum unbekannt` : m.formula ?? ""}
            {forecast ? " · Prognose" : ""}
          </div>
        )}
      </td>
    </tr>
  );
}

export function Derivation({ path, thesisId, onClose, notify, onChanged }: { path: string; thesisId: string; onClose: () => void; notify: (text: string) => void; onChanged: () => void }) {
  const [data, setData] = useState<Json>(null);
  useEffect(() => {
    get(path).then(setData);
  }, [path]);
  const link = (factId: number, stance: string) =>
    post(`/theses/${thesisId}/links`, { target_type: "fact", target_id: factId, stance }).then(() => { notify("Kennzahl der aktiven These als Evidenz zugeordnet"); onChanged(); }).catch((e) => notify(e.message));
  const change = (url: string, text: string, body: Json = {}) =>
    post(url, body).then(() => { notify(text); onChanged(); return get(path).then(setData); }).catch((e) => notify(e.message));
  if (!data) return null;
  const block = (f: Json, title: string) => (
    <div key={f.id} className="box" style={{ marginBottom: 10 }}>
      <div className="row">
        <b>{title}</b>
        <span className="pill">{PROVENANCE[f.provenance].label}</span>
        <span className="pill">{CLAIM_LABEL[f.claim_kind]}</span>
        <span className="pill">Vertrauen: {f.confidence}</span>
        {f.is_demo && <span className="demo">synthetisch</span>}
        {f.retracted ? <span className="pill">storniert</span> : f.superseded && <span className="pill">ersetzt</span>}
        {f.unverified && !f.superseded && <span className="pill unresolved">ungeprüft</span>}
        {f.own_claim && <span className="pill unresolved">eigene Annahme, keine Primärquelle</span>}
      </div>
      <table>
        <tbody>
          <tr><th>Wert</th><td>{f.display}</td></tr>
          {f.basis && <tr><th>Definition / Methode</th><td>{f.basis}</td></tr>}
          <tr><th>Zeitraum</th><td>bis {day(f.period_end)} · veröffentlicht {day(f.published_at)} · erfasst {day(f.recorded_at)}</td></tr>
          {f.formula_key && <tr><th>Formel</th><td>{f.formula_key}</td></tr>}
          {f.document && (
            <tr><th>Quelle</th><td>{f.document.title} ({f.document.publisher}) – <a href={f.document.url} target="_blank" rel="noreferrer">{f.document.url}</a></td></tr>
          )}
          <tr><th>Herkunft</th><td>{ORIGIN_LABEL[f.origin as string]}</td></tr>
        </tbody>
      </table>
      {f.confirm_reason && <div className="small">Deine Begründung: {f.confirm_reason}</div>}
      {f.quote && <div className="quote">„{f.quote}“</div>}
      {!f.superseded && (f.origin === "user" || f.origin === "import") && (
        <div className="row small">
          {f.unverified && <button onClick={() => { const reason = window.prompt("Woher weisst du, dass die Angabe stimmt? (bleibt als eigene Annahme markiert)", "") ?? ""; if (reason.trim().length >= 10) change(`/facts/${f.id}/confirm`, "Als eigene Annahme übernommen", { reason }); else notify("Ohne Begründung (mindestens 10 Zeichen) wird nichts bestätigt"); }}>Selbst bestätigen</button>}
          <button onClick={() => change(`/facts/${f.id}/retract`, "Angabe storniert")}>Stornieren</button>
          <span className="muted">Stornierte Angaben bleiben in der Historie sichtbar.</span>
        </div>
      )}
      {thesisId && !f.superseded && (
        <div className="row small">Als Evidenz der aktiven These: <button onClick={() => link(f.id, "supports")}>stützt</button><button onClick={() => link(f.id, "contradicts")}>widerspricht</button></div>
      )}
    </div>
  );
  return (
    <div className="modal" onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} data-testid="derivation">
        <div className="row"><h2>Herleitung: {data.label}</h2><button className="right" onClick={onClose}>Schliessen</button></div>
        {data.history.length === 0 && <p className="muted">Zu dieser Kennzahl liegt noch nichts vor.</p>}
        {data.history.map((f: Json, i: number) => block(f, i === 0 ? "Aktueller Wert" : "Früherer Wert"))}
        {data.inputs.length > 0 && <h3>Eingangsgrössen</h3>}
        {data.inputs.map((f: Json) => block(f, "Eingang"))}
      </div>
    </div>
  );
}

interface Props {
  id: number;
  state: ViewState;
  update: (change: Partial<ViewState>) => void;
  tick: number;
  templates: Json[];
  thesisTitle: string;
  onChanged: () => void;
  notify: (text: string) => void;
}

export function AssetPanel({ id, state, update, tick, templates, thesisTitle, onChanged, notify }: Props) {
  const [data, setData] = useState<Json>(null);
  const [open, setOpen] = useState("");
  const [ask, setAsk] = useState({ template: "takeover", question: "" });
  const [url, setUrl] = useState("");
  useEffect(() => {
    get(`/assets/${id}`, viewParams(state)).then(setData).catch(() => setData(null));
  }, [id, state.asof, state.view, state.sc, state.pv, tick]);
  if (!data) return <p className="muted">Lädt …</p>;
  const card: Card = data.card;
  const selected = selection(state);
  const act = async (run: () => Promise<Json>, text: string) => {
    try {
      await run();
      notify(text);
      onChanged();
    } catch (error) {
      notify(String((error as Error).message));
    }
  };
  const propose = (body: Json, text: string) => act(() => post("/proposals", { subject_id: id, ...body }), text);
  const modeText = { today: "", as_of: `Stand ${day(state.asof)} – ${state.view === "hindsight" ? "rückblickend bekannt" : "wie damals bekannt"}`, scenario: "Szenario – modellierte Werte" }[card.mode];
  return (
    <div data-testid="asset-panel">
      <div className="row">
        <h2>{card.name}</h2>
        {card.is_demo && <span className="demo">synthetisch</span>}
        <button className="right" onClick={() => update({ a: "" })} title="Schliessen (Esc)">✕</button>
      </div>
      <div className="row">
        <span className="status">{STATUS_LABEL[card.status]}{card.status_since ? ` seit ${card.status_since.slice(0, 4)}` : ""}</span>
        <span className="muted">{card.region}, {card.country} · {METHOD_LABEL[card.mining_method] ?? card.mining_method}</span>
      </div>
      <p className="small">
        Betreiber:{" "}
        {card.stakes.filter((s) => s.role === "operator").map((s) => (
          <button key={s.company_id} className="link" onClick={() => update({ co: String(s.company_id), a: "" })} title="Unternehmensansicht öffnen">
            {s.company}
          </button>
        ))}
        {!card.operator && <span className="muted">unbekannt</span>}
        {card.royalty_pct > 0 && <> · Royalty-Last {card.royalty_pct.toLocaleString("de-DE")} % vom Umsatz</>}
        {" · "}Rohstoffe: {card.commodities.map((c) => `${COMMODITY_LABEL[c.key] ?? c.key}${c.role === "by_product" ? " (Nebenprodukt)" : ""}`).join(", ")}
      </p>
      {card.registry_source && card.status === "unknown" && (
        <div className="note" data-testid="registry-note">
          Aus einem öffentlichen Register übernommen ({card.registry_source === "mrds" ? "USGS MRDS" : "Wikidata"}). Belegt sind nur Ort und Name{card.operator ? " sowie der dort genannte Betreiber" : ""}.{" "}
          <button className="link" onClick={() => propose({ template: "profile" }, "Profil-Recherche vorgemerkt – im Backlog starten")}>Profil recherchieren</button>
        </div>
      )}
      {modeText && <div className="note"><b>{modeText}</b>{card.price != null && ` · Preis ${card.price.toLocaleString("de-DE")}`}</div>}
      <div className="row">
        <button onClick={() => update({ sel: (selected.includes(id) ? selected.filter((s) => s !== id) : [...selected, id].slice(0, 8)).join(",") })}>
          {selected.includes(id) ? "Aus Auswahl entfernen" : "+ Zur Auswahl"}
        </button>
        <span className="pill" title="Wissensstatus (abgeleitet)">{KNOWLEDGE_LABEL[card.knowledge.status]}</span>
      </div>

      <div className="section">
        <h3>{card.status === "production" ? "Kennzahlen" : "Studienwerte (Prognosen)"}</h3>
        <table>
          <tbody>
            {card.metrics.map((m) => (
              <MetricRow
                key={m.metric}
                m={m}
                onOpen={() => setOpen(m.metric)}
                action={
                  m.provenance === "unknown" ? (
                    <div>
                      <button className="link small" onClick={(e) => { e.stopPropagation(); propose({ template: "fill_metric", metric: m.metric }, "Recherche vorgemerkt – im Backlog starten"); }}>
                        Recherche vorschlagen
                      </button>
                    </div>
                  ) : undefined
                }
              />
            ))}
          </tbody>
        </table>
      </div>

      <div className="section">
        <h3>Wirtschaftlichkeit {card.economics_is_forecast ? "(Prognose × Preis)" : ""}</h3>
        {card.economics.length === 0 ? (
          <p className="muted small">Nicht berechenbar: Preis oder Stückkosten sind unbekannt. Es wird nichts geschätzt, was nicht belegt ist.</p>
        ) : (
          <table><tbody>{card.economics.map((m) => <MetricRow key={m.metric} m={m} />)}</tbody></table>
        )}
        {card.by_product_note && <div className="note">Nebenproduktgutschrift nicht an den Szenariopreis angepasst (Mengen unbekannt).</div>}
      </div>

      <div className="section">
        <h3>Frage vormerken</h3>
        {thesisTitle && <div className="small muted">Das Ergebnis wird der These „{thesisTitle}“ zugeordnet.</div>}
        <div className="row">
          <select value={ask.template} onChange={(e) => setAsk({ ...ask, template: e.target.value })}>
            {templates.filter((t) => !["fill_metric", "read_document"].includes(t.key)).map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
          </select>
          <input className="grow" placeholder="eigene Formulierung (optional)" value={ask.question} onChange={(e) => setAsk({ ...ask, question: e.target.value })} />
          <button data-testid="add-question" onClick={() => propose({ ...ask, thesis_id: state.th ? Number(state.th) : null }, "Frage vorgemerkt – im Backlog prüfen und starten")}>+ Frage</button>
        </div>
        {data.proposals.length > 0 && (
          <div className="cardlist" style={{ marginTop: 8 }}>
            {data.proposals.map((p: Json) => (
              <div key={p.id}>
                <div className="small muted">{p.template_label}</div>
                {p.question}
                <div className="row" style={{ marginTop: 4 }}>
                  <button className="primary" onClick={() => act(() => post("/proposals/start", { ids: [p.id] }), "Recherche gestartet")}>Starten</button>
                  <button onClick={() => act(() => post(`/proposals/${p.id}/dismiss`), "Vorschlag verworfen")}>Verwerfen</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {(data.tickets.length > 0 || data.findings.length > 0) && (
        <div className="section">
          <h3>Recherche und Erkenntnisse</h3>
          <div className="cardlist">
            {data.tickets.map((t: Json) => (
              <div key={`t${t.id}`}>
                <div className="row"><span className={`pill ${t.status}`}>{TICKET_LABEL[t.status]}</span><button className="link" onClick={() => update({ path: "/research" })}>{t.title}</button></div>
                {t.error && <div className="small" style={{ color: "var(--bad)" }}>{t.error}</div>}
              </div>
            ))}
            {data.findings.map((f: Json) => (
              <div key={`f${f.id}`}>
                <div className="row"><span className={`pill ${f.epistemic}`}>{EPISTEMIC_LABEL[f.epistemic]}</span><span className="muted small">{day(f.created_at)}</span></div>
                <div style={{ whiteSpace: "pre-wrap" }}>{f.text}</div>
                {f.uncertainty && <div className="small muted">Unsicherheit: {f.uncertainty}</div>}
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="section">
        <h3>Lebenslauf</h3>
        {data.milestones.length === 0 && <p className="muted small">Noch keine Meilensteine erfasst.</p>}
        <table><tbody>
          {data.milestones.map((m: Json) => (
            <tr key={m.id}>
              <td>{m.day.slice(0, 7)}</td><td>{m.title}</td>
              <td><button className="link small" title="Stand zu diesem Zeitpunkt ansehen" onClick={() => update({ asof: m.day })}>ansehen</button></td>
            </tr>
          ))}
        </tbody></table>
      </div>

      <div className="section">
        <h3>Quellen</h3>
        {data.documents.map((d: Json) => (
          <div key={d.id} className="small">{d.title} · {d.publisher} · {day(d.published_at)} {d.is_demo && <span className="demo">synthetisch</span>}</div>
        ))}
        <div className="row" style={{ marginTop: 6 }}>
          <input className="grow" placeholder="https://… Bericht oder Studie" value={url} onChange={(e) => setUrl(e.target.value)} />
          <button disabled={!url} onClick={() => act(() => post("/documents", { asset_id: id, url }), "Dokument wird abgerufen und gelesen").then(() => setUrl(""))}>Dokument lesen</button>
        </div>
      </div>
      {open && <Derivation path={`/assets/${id}/facts/${open}`} thesisId={state.th} onClose={() => setOpen("")} notify={notify} onChanged={onChanged} />}
    </div>
  );
}
