// Shell: commodity bar, navigation, search, notifications and the page switch.
import { useCallback, useEffect, useRef, useState } from "react";
import type { Commodity, Json } from "./api";
import { TICKET_LABEL, get, num } from "./api";
import { Explorer } from "./Explorer";
import { Manual, Portfolio, Sources, System } from "./Pages";
import { Research } from "./Research";
import { useViewState } from "./state";

const NAV: [string, string][] = [["/", "Explorer"], ["/research", "Research"], ["/portfolio", "Portfolio"], ["/sources", "Quellen"], ["/system", "System"], ["/manual", "Handbuch"]];
const POLL_MS = 4000;

export function App() {
  const [state, update] = useViewState();
  const [commodities, setCommodities] = useState<Commodity[]>([]);
  const [templates, setTemplates] = useState<Json[]>([]);
  const [theses, setTheses] = useState<Json[]>([]);
  const [bell, setBell] = useState<Json>({ running: 0, unseen: [] });
  const [bellOpen, setBellOpen] = useState(false);
  const [tick, setTick] = useState(0);
  const [toast, setToast] = useState("");
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<Json[]>([]);
  const [demo, setDemo] = useState(false);
  const signature = useRef("");
  const refresh = useCallback(() => setTick((t) => t + 1), []);
  const notify = useCallback((text: string) => {
    setToast(text);
    window.setTimeout(() => setToast(""), 3500);
  }, []);

  useEffect(() => {
    get("/commodities").then(setCommodities);
    get("/templates").then(setTemplates);
    get("/system").then((s) => setDemo(s.is_demo));
  }, []);
  useEffect(() => { get("/theses").then(setTheses); }, [tick]);
  useEffect(() => {
    // Polling keeps the UI usable while research runs; a change triggers one refresh.
    const poll = () => get("/notifications").then((data) => {
      const next = `${data.running}:${data.unseen.map((t: Json) => t.id).join(",")}`;
      if (signature.current && next !== signature.current) {
        refresh();
        if (data.unseen.length > bell.unseen.length) notify(`Ergebnis da: ${data.unseen[0].title}`);
      }
      signature.current = next;
      setBell(data);
    }).catch(() => undefined);
    poll();
    const timer = window.setInterval(poll, POLL_MS);
    return () => window.clearInterval(timer);
  }, [bell.unseen.length]);
  useEffect(() => {
    if (query.trim().length < 2) { setHits([]); return; }
    const timer = window.setTimeout(() => get("/search", { q: query }).then(setHits), 200);
    return () => window.clearTimeout(timer);
  }, [query]);

  const go = (hit: Json) => {
    setQuery("");
    setHits([]);
    if (hit.type === "asset") update({ path: "/", a: String(hit.id) });
    else if (hit.type === "company") update({ path: "/", co: String(hit.id), a: "" });
    else update({ path: "/", th: String(hit.id), a: "" });
  };
  const common = { tick, refresh, notify };
  return (
    <div className="shell">
      <header className="top">
        <span className="brand">WatchStreet</span>
        {demo && <span className="demo" title="Alle Daten sind synthetisch">DEMO</span>}
        <nav className="nav">{NAV.map(([path, label]) => <button key={path} className={state.path === path ? "on" : ""} onClick={() => update({ path })}>{label}</button>)}</nav>
        <div className="commodities" data-testid="commodities">
          {commodities.map((c) => (
            <button key={c.key} className={`commodity ${state.c === c.key ? "on" : ""}`} style={{ "--c": c.color } as React.CSSProperties}
              onClick={() => update({ path: "/", c: state.c === c.key ? "" : c.key, sc: "" })}>
              <b>{c.label}</b>
              <span>{num(c.price)} <span className={(c.change_pct ?? 0) >= 0 ? "up" : "down"}>{c.change_pct != null ? `${c.change_pct >= 0 ? "+" : ""}${c.change_pct.toFixed(1)} %` : ""}</span></span>
            </button>
          ))}
        </div>
        <div className="search grow">
          <input style={{ width: "100%" }} placeholder="Suche: Mine, Projekt, Unternehmen, These" value={query} onChange={(e) => setQuery(e.target.value)} />
          {hits.length > 0 && <ul>{hits.map((hit) => <li key={`${hit.type}${hit.id}`}><button onClick={() => go(hit)}>{hit.label} <span className="muted small">{{ asset: "Objekt", company: "Unternehmen", thesis: "These" }[hit.type as string]}</span></button></li>)}</ul>}
        </div>
        <div className="bell">
          <button data-testid="bell" onClick={() => setBellOpen(!bellOpen)}>🔔 {bell.running > 0 ? `${bell.running} läuft` : ""}</button>
          {bell.unseen.length > 0 && <span className="count">{bell.unseen.length}</span>}
          {bellOpen && (
            <div className="popover">
              {bell.unseen.length === 0 && <span className="muted">Keine neuen Ergebnisse.</span>}
              {bell.unseen.map((t: Json) => (
                <div key={t.id} style={{ marginBottom: 6 }}>
                  <span className={`pill ${t.status}`}>{TICKET_LABEL[t.status]}</span>{" "}
                  <button className="link" onClick={() => { setBellOpen(false); update(t.subject_type === "asset" ? { path: "/", a: String(t.subject_id) } : { path: "/research" }); }}>{t.title}</button>
                  <div className="small muted">{t.subject_name} – zum Ort springen</div>
                </div>
              ))}
              <button onClick={() => { setBellOpen(false); update({ path: "/research" }); }}>Zum Research-Bereich</button>
            </div>
          )}
        </div>
      </header>
      {state.path === "/research" ? <Research update={update} theses={theses} {...common} />
        : state.path === "/portfolio" ? <Portfolio notify={notify} />
        : state.path === "/sources" ? <Sources />
        : state.path === "/system" ? <System notify={notify} tick={tick} />
        : state.path === "/manual" ? <Manual />
        : <Explorer state={state} update={update} commodities={commodities} templates={templates} theses={theses} {...common} />}
      {toast && <div className="toast" role="status">{toast}</div>}
    </div>
  );
}
