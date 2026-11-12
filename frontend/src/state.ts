// The whole view state lives in the URL, so views are shareable and Back works.
import { useCallback, useEffect, useState } from "react";

export interface ViewState {
  path: string;
  c: string; // commodity filter
  a: string; // active asset id
  sel: string; // selected asset ids, comma separated
  asof: string;
  view: string; // as_known | hindsight
  color: string;
  sc: string; // scenario, e.g. copper:5.2
  co: string; // highlighted company id
  th: string; // focused thesis id
  pv: string; // "1" = only proven figures (no imported or self-confirmed ones)
}

const KEYS = ["c", "a", "sel", "asof", "view", "color", "sc", "co", "th", "pv"] as const;

function read(): ViewState {
  const query = new URLSearchParams(window.location.search);
  const state = { path: window.location.pathname } as ViewState;
  for (const key of KEYS) state[key] = query.get(key) ?? "";
  return state;
}

export function useViewState(): [ViewState, (change: Partial<ViewState>) => void] {
  const [state, setState] = useState(read);
  useEffect(() => {
    const onPop = () => setState(read());
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);
  const update = useCallback((change: Partial<ViewState>) => {
    const next = { ...read(), ...change };
    const query = new URLSearchParams();
    for (const key of KEYS) if (next[key]) query.set(key, next[key]);
    const url = `${next.path}${query.size ? `?${query}` : ""}`;
    // moving between pages is a history step; tuning a view is not
    if (change.path && change.path !== window.location.pathname) window.history.pushState(null, "", url);
    else window.history.replaceState(null, "", url);
    setState(next);
  }, []);
  return [state, update];
}

export const selection = (state: ViewState): number[] => state.sel.split(",").filter(Boolean).map(Number);

/** Query parameters every data request shares (reference date, view, scenario). */
export const viewParams = (state: ViewState): Record<string, string | undefined> => ({
  asof: state.asof || undefined,
  view: state.asof && state.view ? state.view : undefined,
  scenario: state.sc || undefined,
  proven: state.pv ? "true" : undefined,
});
