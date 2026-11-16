// Light/dark switch: "auto" follows the system, a choice is kept in this browser.
export type Theme = "auto" | "light" | "dark";
export const THEME_EVENT = "watchstreet-theme";
const KEY = "theme";
const ORDER: Theme[] = ["auto", "light", "dark"];
export const THEME_LABEL: Record<Theme, string> = { auto: "Automatisch (wie das System)", light: "Hell", dark: "Dunkel" };
export const THEME_ICON: Record<Theme, string> = { auto: "◐", light: "☀", dark: "☾" };

export function storedTheme(): Theme {
  try {
    const value = window.localStorage.getItem(KEY);
    return ORDER.includes(value as Theme) ? (value as Theme) : "auto";
  } catch {
    return "auto";
  }
}

export function applyTheme(theme: Theme): void {
  const root = document.documentElement;
  if (theme === "auto") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", theme);
  try {
    window.localStorage.setItem(KEY, theme);
  } catch {
    // private window: the choice lasts until the page is closed
  }
  window.dispatchEvent(new Event(THEME_EVENT));
}

export const nextTheme = (theme: Theme): Theme => ORDER[(ORDER.indexOf(theme) + 1) % ORDER.length];
