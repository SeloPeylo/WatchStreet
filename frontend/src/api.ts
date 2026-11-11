// Thin client for the JSON API. Every figure arrives in the same shape (see Metric).

export interface Metric {
  metric: string;
  label: string;
  provenance: "reported" | "derived" | "estimated" | "unknown";
  value?: number | null;
  low?: number | null;
  high?: number | null;
  text?: string;
  unit?: string;
  claim_kind?: string;
  basis?: string;
  period_end?: string | null;
  published_at?: string | null;
  stale?: boolean;
  formula?: string;
  origin?: string;
  is_demo?: boolean;
}

export interface Card {
  id: number;
  name: string;
  kind: string;
  lat: number;
  lon: number;
  country: string;
  region: string;
  mining_method: string;
  summary: string;
  is_demo: boolean;
  commodity: string;
  commodities: { key: string; role: string }[];
  status: string;
  status_since: string | null;
  operator: string | null;
  stakes: { company_id: number; company: string; role: string; share_pct: number | null }[];
  metrics: Metric[];
  economics: Metric[];
  economics_is_forecast: boolean;
  by_product_note: boolean;
  price: number | null;
  mode: "today" | "as_of" | "scenario";
  knowledge: { status: string; open_questions: number; running: boolean; new_result: boolean; missing: string[] };
}

export interface Commodity {
  key: string;
  label: string;
  unit: string;
  price_unit: string;
  color: string;
  price: number | null;
  change_pct: number | null;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type Json = any;

async function request(method: string, path: string, body?: unknown): Promise<Json> {
  const response = await fetch(`/api/v1${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : `Fehler ${response.status}`);
  return data;
}

export const get = (path: string, params: Record<string, string | undefined> = {}): Promise<Json> => {
  const query = new URLSearchParams(Object.entries(params).filter(([, v]) => v) as [string, string][]).toString();
  return request("GET", query ? `${path}?${query}` : path);
};
export const post = (path: string, body: unknown = {}): Promise<Json> => request("POST", path, body);
export const patch = (path: string, body: unknown): Promise<Json> => request("PATCH", path, body);
export const del = (path: string): Promise<Json> => request("DELETE", path);

// --- labels and formatting (German UI) -------------------------------------------------

export const STATUS_LABEL: Record<string, string> = {
  production: "Produktion",
  development: "Entwicklung",
  exploration: "Exploration",
  care_maintenance: "Ruhend",
  closed: "Stillgelegt",
  unknown: "Status unbekannt",
};
export const PROVENANCE: Record<string, { chip: string; label: string }> = {
  reported: { chip: "B", label: "berichtet" },
  derived: { chip: "≈", label: "berechnet" },
  estimated: { chip: "~", label: "geschätzt" },
  unknown: { chip: "?", label: "unbekannt" },
};
export const CLAIM_LABEL: Record<string, string> = {
  actual: "Ist",
  guidance: "Unternehmensprognose",
  hypothesis: "Hypothese",
  ai_inference: "KI-Schlussfolgerung",
};
export const KNOWLEDGE_LABEL: Record<string, string> = {
  unexamined: "Noch nicht geprüft",
  known: "Bekannt",
  deep: "Vertieft untersucht",
  new: "Neue Entwicklung",
  stale: "Veraltet",
};
export const TICKET_LABEL: Record<string, string> = {
  queued: "Wartet",
  running: "Läuft",
  done: "Abgeschlossen",
  failed: "Fehlgeschlagen",
  cancelled: "Abgebrochen",
};
export const EPISTEMIC_LABEL: Record<string, string> = {
  unresolved: "Nicht belegt",
  correlation: "Korrelation",
  hypothesis: "Begründete Hypothese",
  evidenced: "Belegt",
};
export const COMMODITY_LABEL: Record<string, string> = { gold: "Gold", silver: "Silber", copper: "Kupfer", uranium: "Uran" };
export const METHOD_LABEL: Record<string, string> = {
  open_pit: "Tagebau",
  underground: "Untertage",
  isr: "In-situ-Recovery",
  heap_leach: "Haufenlaugung",
  unknown: "unbekannt",
};

const compact = new Intl.NumberFormat("de-DE", { notation: "compact", maximumFractionDigits: 2 });
const plain = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 2 });

export function num(value: number | null | undefined): string {
  if (value === null || value === undefined) return "–";
  return Math.abs(value) >= 100000 ? compact.format(value) : plain.format(value);
}

export function metricText(m: Metric): string {
  if (m.provenance === "unknown") return "unbekannt";
  if (m.unit === "Anteil") {
    const pct = (v: number) => `${plain.format(v * 100)} %`;
    return m.value != null ? pct(m.value) : `${pct(m.low!)} bis ${pct(m.high!)}`;
  }
  if (m.value != null) return `${num(m.value)} ${m.unit ?? ""}`.trim();
  if (m.low != null && m.high != null) return `${num(m.low)} – ${num(m.high)} ${m.unit ?? ""}`.trim();
  return m.text || "unbekannt";
}

export const day = (iso: string | null | undefined): string =>
  iso ? new Date(iso).toLocaleDateString("de-DE", { year: "numeric", month: "2-digit", day: "2-digit" }) : "–";
