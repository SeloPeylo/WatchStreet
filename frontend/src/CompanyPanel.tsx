// Company view: does the company survive to benefit from its assets?
// Balance sheet, dilution, people, royalties, a due-diligence checklist and the assets.
import { useEffect, useState } from "react";
import { Derivation, MetricRow } from "./AssetPanel";
import type { Json, Metric } from "./api";
import { EPISTEMIC_LABEL, STATUS_LABEL, day, del, get, num, post } from "./api";
import type { ViewState } from "./state";
import { viewParams } from "./state";

const ENTRY: [string, string, boolean][] = [
  ["cash", "Kasse (USD)", false], ["debt", "Finanzschulden (USD)", false], ["burn_rate", "Mittelabfluss je Quartal (USD)", false],
  ["shares_outstanding", "Ausstehende Aktien", false], ["shares_diluted", "Aktien voll verwässert", false], ["insider_ownership", "Insiderbesitz (%)", false],
  ["royalty_burden", "Royalties und Streams (Text)", true], ["next_catalyst", "Nächster Katalysator (Text)", true],
];
const QUESTION_TEMPLATE: Record<string, string> = { people: "management", insiders: "management", financing: "financing", burn: "financing" };
const NO_FIN = { day: "", amount: "", price: "", note: "", kind: "equity", warrants: "", warrant_price: "", warrant_expiry: "", investors: "", announced: false };
const ROLE: Record<string, string> = { royalty: "Royalty", stream: "Stream" };

interface Props {
  id: number;
  state: ViewState;
  update: (change: Partial<ViewState>) => void;
  tick: number;
  onChanged: () => void;
  notify: (text: string) => void;
}

export function CompanyPanel({ id, state, update, tick, onChanged, notify }: Props) {
  const [data, setData] = useState<Json>(null);
  const [open, setOpen] = useState("");
  const [entry, setEntry] = useState({ metric: "cash", value: "" });
  const [person, setPerson] = useState({ name: "", role: "", track_record: "", prior_companies: "", shares_held: "" });
  const [fin, setFin] = useState(NO_FIN);
  useEffect(() => {
    get(`/companies/${id}`, viewParams(state)).then(setData).catch(() => setData(null));
  }, [id, state.asof, state.view, state.sc, state.pv, tick]);
  if (!data) return <p className="muted">Lädt …</p>;
  const act = async (run: () => Promise<Json>, text: string) => {
    try {
      await run();
      notify(text);
      onChanged();
      return true;
    } catch (error) {
      notify((error as Error).message);
      return false; // keep what the user typed
    }
  };
  const propose = (body: Json) => act(() => post("/proposals", { subject_type: "company", subject_id: id, ...body }), "Frage vorgemerkt – im Backlog prüfen und starten");
  const ask = (q: Json) => (q.missing.length > 0 ? propose({ template: "fill_metric", metric: q.missing[0] }) : propose({ template: QUESTION_TEMPLATE[q.key] ?? "free", question: QUESTION_TEMPLATE[q.key] ? "" : q.text }));
  const isText = ENTRY.find(([key]) => key === entry.metric)![2];
  const save = () =>
    act(() => post("/facts", { subject_type: "company", subject_id: id, metric: entry.metric, ...(isText ? { text: entry.value } : { value: Number(entry.value) }) }), "Kennzahl gespeichert").then((ok) => { if (ok) setEntry({ ...entry, value: "" }); });
  const savePerson = () => act(() => post(`/companies/${id}/people`, { ...person, shares_held: person.shares_held ? Number(person.shares_held) : null }), "Person erfasst").then((ok) => { if (ok) setPerson({ name: "", role: "", track_record: "", prior_companies: "", shares_held: "" }); });
  const saveFin = () =>
    act(() => post(`/companies/${id}/financings`, { day: fin.day, note: fin.note, kind: fin.kind, investors: fin.investors, announced: fin.announced, ...(fin.warrants ? { warrants: Number(fin.warrants) } : {}), ...(fin.warrant_price ? { warrant_price: Number(fin.warrant_price) } : {}), ...(fin.warrant_expiry ? { warrant_expiry: fin.warrant_expiry } : {}), ...(fin.amount ? { amount: Number(fin.amount) } : {}), ...(fin.price ? { price: Number(fin.price) } : {}) }), "Finanzierung erfasst").then((ok) => { if (ok) setFin(NO_FIN); });
  const answered = data.checklist.filter((q: Json) => q.answered).length;
  return (
    <div data-testid="company-panel">
      <div className="row">
        <h2>{data.name}</h2>
        {data.is_demo && <span className="demo">synthetisch</span>}
        <button className="right" onClick={() => update({ co: "" })} title="Schliessen">✕</button>
      </div>
      <p className="small muted">
        {data.symbol ? `${data.symbol} · Kurs ${num(data.price)}` : "nicht börsennotiert erfasst"} · {data.assets.length} Objekte (auf der Karte hervorgehoben)
      </p>

      <div className="section">
        <h3>Bilanz und Kapitalstruktur</h3>
        <table><tbody>
          {data.metrics.map((m: Metric) => <MetricRow key={m.metric} m={m} onOpen={() => setOpen(m.metric)} />)}
        </tbody></table>
      </div>

      <div className="section">
        <h3>Abgeleitet</h3>
        <table><tbody>{data.derived.map((m: Metric) => <MetricRow key={m.metric} m={m} />)}</tbody></table>
        <div className="note">Asset-NAV und das Verhältnis dazu sind einfache Modellrechnungen ohne Steuern, Investitionen, Schulden und Länderabschlag – keine Bewertung. Die Finanzierungslücke zeigt, wie viel Kapital für den Bau der Projekte noch fehlt; sie wird in aller Regel durch Verwässerung geschlossen.</div>
      </div>

      <div className="section">
        <h3>Prüfkatalog ({answered} von {data.checklist.length} belegt)</h3>
        <table data-testid="checklist"><tbody>
          {data.checklist.map((q: Json) => (
            <tr key={q.key}>
              <td>{q.answered ? "✔" : "○"}</td>
              <td>{q.text}</td>
              <td>{!q.answered && <button className="link small" onClick={() => ask(q)}>Recherche vormerken</button>}</td>
            </tr>
          ))}
        </tbody></table>
        <p className="small muted">„Belegt“ heisst: dazu liegt etwas vor – nicht, dass die Antwort gut ist.</p>
      </div>

      <div className="section">
        <h3>Menschen</h3>
        {data.people.length === 0 && <p className="muted small">Noch niemand erfasst.</p>}
        {data.people.map((p: Json) => (
          <div key={p.id} className="small" style={{ marginBottom: 4 }}>
            <b>{p.name}</b> · {p.role}{p.since ? ` seit ${p.since.slice(0, 4)}` : ""} {p.sourced && <span className="pill evidenced">mit Zitat</span>}
            {p.own_entry && <button className="link small" title="Eigenen Eintrag löschen" onClick={() => act(() => del(`/people/${p.id}`), "Person gelöscht")}> ✕</button>}
            <div className="muted">{p.track_record}</div>
            {p.prior_companies && <div className="muted">Frühere Unternehmen: {p.prior_companies}</div>}
            {p.shares_held != null && <div className="muted">Hält {num(p.shares_held)} Aktien{p.ownership != null ? ` (${num(p.ownership * 100)} % des Unternehmens)` : ""}</div>}
          </div>
        ))}
        <details>
          <summary className="small">Person erfassen</summary>
          <div className="row">
            <input placeholder="Name" value={person.name} onChange={(e) => setPerson({ ...person, name: e.target.value })} data-testid="person-name" />
            <input placeholder="Rolle" value={person.role} onChange={(e) => setPerson({ ...person, role: e.target.value })} />
          </div>
          <div className="row">
            <input className="grow" placeholder="Frühere Unternehmen und Ergebnis für Aktionäre" value={person.prior_companies} onChange={(e) => setPerson({ ...person, prior_companies: e.target.value })} />
            <input type="number" placeholder="Eigene Aktien" value={person.shares_held} onChange={(e) => setPerson({ ...person, shares_held: e.target.value })} />
          </div>
          <div className="row">
            <input className="grow" placeholder="Erfolgsbilanz: was hat die Person früher gebaut oder verkauft?" value={person.track_record} onChange={(e) => setPerson({ ...person, track_record: e.target.value })} />
            <button disabled={person.name.length < 2} onClick={savePerson}>Speichern</button>
          </div>
        </details>
      </div>

      <div className="section">
        <h3>Finanzierungen</h3>
        {data.financings.length === 0 && <p className="muted small">Keine Finanzierung erfasst.</p>}
        <table><tbody>
          {data.financings.map((f: Json) => (
            <tr key={f.id}><td>{day(f.day)}</td><td className="n">{num(f.amount)} USD</td><td className="n">{f.price != null ? `${num(f.price)} je Aktie` : ""}</td><td className="small muted">{f.warrants != null && <>+ {num(f.warrants)} Warrants{f.warrant_price != null ? ` zu ${num(f.warrant_price)}` : ""}{f.warrant_expiry ? ` bis ${day(f.warrant_expiry)}` : ""} · </>}{f.investors && <>{f.investors} · </>}{f.note}{f.announced && <> · <b>angekündigt</b></>}{f.after_balance && <> · <b>nach Bilanzstichtag</b></>}
              {f.own_entry && <button className="link small" title="Eigenen Eintrag löschen" onClick={() => act(() => del(`/financings/${f.id}`), "Finanzierung gelöscht")}> ✕</button>}</td></tr>
          ))}
        </tbody></table>
        <details>
          <summary className="small">Finanzierung erfassen</summary>
          <div className="row">
            <label className="small">Datum <input type="date" value={fin.day} onChange={(e) => setFin({ ...fin, day: e.target.value })} data-testid="fin-day" /></label>
            <select value={fin.kind} onChange={(e) => setFin({ ...fin, kind: e.target.value })}>
              <option value="equity">Eigenkapital</option><option value="debt">Fremdkapital</option><option value="royalty_sale">Royalty-Verkauf</option>
            </select>
            <input type="number" placeholder="Betrag USD" value={fin.amount} onChange={(e) => setFin({ ...fin, amount: e.target.value })} />
            <input type="number" placeholder="Preis je Aktie" value={fin.price} onChange={(e) => setFin({ ...fin, price: e.target.value })} />
          </div>
          <div className="row">
            <input type="number" placeholder="Warrants (Stück)" value={fin.warrants} onChange={(e) => setFin({ ...fin, warrants: e.target.value })} />
            <input type="number" placeholder="Ausübungspreis" value={fin.warrant_price} onChange={(e) => setFin({ ...fin, warrant_price: e.target.value })} />
            <label className="small">Warrants laufen bis <input type="date" value={fin.warrant_expiry} onChange={(e) => setFin({ ...fin, warrant_expiry: e.target.value })} /></label>
          </div>
          <div className="row">
            <label className="small" title="Geplant, noch nicht abgeschlossen: wird als Was-wäre-wenn eingerechnet und so gekennzeichnet; das Datum darf in der Zukunft liegen"><input type="checkbox" checked={fin.announced} onChange={() => setFin({ ...fin, announced: !fin.announced })} data-testid="fin-announced" /> nur angekündigt (Was-wäre-wenn)</label>
          </div>
          <div className="row">
            <input placeholder="Zeichner" value={fin.investors} onChange={(e) => setFin({ ...fin, investors: e.target.value })} />
            <input className="grow" placeholder="Notiz" value={fin.note} onChange={(e) => setFin({ ...fin, note: e.target.value })} />
            <button disabled={!fin.day || !fin.amount} onClick={saveFin}>Speichern</button>
          </div>
          <p className="small muted">Kasse und Aktienzahl oben bleiben auf dem Bilanzstichtag; Finanzierungen danach erscheinen unter „Abgeleitet“ als Pro-forma-Werte.</p>
        </details>
      </div>

      <div className="section">
        <h3>Royalties und Streams auf den Objekten</h3>
        {data.burdens.length === 0 && <p className="muted small">Keine erfasst. Das heisst nicht, dass es keine gibt.</p>}
        {data.burdens.map((b: Json) => <div key={`${b.asset_id}${b.holder}`} className="small">{b.asset}: {num(b.share_pct)} % {ROLE[b.role]} an {b.holder}</div>)}
      </div>

      <div className="section">
        <h3>Preishebel (anteiliger Cashflow p. a. der produzierenden Objekte)</h3>
        {data.sensitivity.length === 0 && <p className="muted small">Nicht anwendbar: kein produzierendes Objekt mit Eigentumsanteil und bekannten Kosten.</p>}
        <table><tbody>
          <tr>{data.sensitivity.map((row: Json) => <th key={row.change}>{row.change === 0 ? (state.sc ? "Szenario" : "heute") : `${row.change > 0 ? "+" : ""}${row.change * 100} %`}</th>)}</tr>
          <tr>{data.sensitivity.map((row: Json) => <td key={row.change} className={`n ${row.cash_flow < 0 ? "down" : ""}`}>{num(row.cash_flow)}</td>)}</tr>
        </tbody></table>
        <p className="small muted">Alle Rohstoffpreise bewegen sich gleich; Kosten bleiben fest.</p>
      </div>

      <div className="section">
        <h3>Objekte</h3>
        <table><tbody>
          {data.assets.map((a: Json) => (
            <tr key={a.id}>
              <td><button className="link" onClick={() => update({ a: String(a.id) })}>{a.name}</button></td>
              <td className="small muted">{STATUS_LABEL[a.status]}</td>
              <td className="n small">{a.owner_share ? `${Math.round(a.owner_share * 100)} %` : "–"}</td>
            </tr>
          ))}
        </tbody></table>
      </div>

      {(data.findings.length > 0 || data.proposals.length > 0) && (
        <div className="section">
          <h3>Auffälligkeiten und offene Fragen</h3>
          <div className="cardlist">
            {data.findings.map((f: Json) => (
              <div key={`f${f.id}`}><span className={`pill ${f.epistemic}`}>{EPISTEMIC_LABEL[f.epistemic]}</span> {f.text}
                {f.uncertainty && <div className="small muted">{f.uncertainty}</div>}</div>
            ))}
            {data.proposals.map((p: Json) => (
              <div key={`p${p.id}`}>
                <div className="small muted">{p.template_label}</div>{p.question}
                <div className="row" style={{ marginTop: 4 }}>
                  <button className="primary" onClick={() => act(() => post("/proposals/start", { ids: [p.id] }), "Recherche gestartet")}>Starten</button>
                  <button onClick={() => act(() => post(`/proposals/${p.id}/dismiss`), "Vorschlag verworfen")}>Verwerfen</button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="section">
        <h3>Eigene Angabe</h3>
        <div className="row">
          <select value={entry.metric} onChange={(e) => setEntry({ metric: e.target.value, value: "" })}>
            {ENTRY.map(([key, label]) => <option key={key} value={key}>{label}</option>)}
          </select>
          <input className="grow" type={isText ? "text" : "number"} value={entry.value} onChange={(e) => setEntry({ ...entry, value: e.target.value })} />
          <button disabled={!entry.value} onClick={save}>Speichern</button>
        </div>
        <p className="small muted">Eigene Angaben werden als Nutzereintrag geführt und von Agenten nie überschrieben.</p>
      </div>
      {open && <Derivation path={`/companies/${id}/facts/${open}`} thesisId={state.th} onClose={() => setOpen("")} notify={notify} onChanged={onChanged} />}
    </div>
  );
}
