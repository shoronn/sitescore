import { useSyncExternalStore } from "react";

/** The visitor's choice. "system" follows the device setting and changes with it. */
export type ThemePref = "system" | "light" | "dark";
export type Theme = "light" | "dark";

const KEY = "sitescore-theme";
const THEME_COLOR: Record<Theme, string> = { light: "#F2F2F7", dark: "#000000" };
const media = typeof window !== "undefined" && window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;
const listeners = new Set<() => void>();

function readPref(): ThemePref {
  try {
    const v = window.localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : "system";
  } catch {
    return "system";
  }
}

let pref: ThemePref = typeof window !== "undefined" ? readPref() : "system";

function resolve(p: ThemePref): Theme {
  if (p === "system") return media?.matches ? "dark" : "light";
  return p;
}

function apply() {
  const theme = resolve(pref);
  const root = document.documentElement;
  root.setAttribute("data-theme", theme);
  root.setAttribute("data-theme-pref", pref);
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", THEME_COLOR[theme]);
  listeners.forEach((l) => l());
}

export function setThemePref(next: ThemePref) {
  pref = next;
  try {
    if (next === "system") window.localStorage.removeItem(KEY);
    else window.localStorage.setItem(KEY, next);
  } catch {
    /* storage blocked: the choice lasts for this visit only */
  }
  apply();
}

if (typeof window !== "undefined") {
  apply();
  // Follow the device when it switches between light and dark (for example at sunset).
  media?.addEventListener?.("change", () => pref === "system" && apply());
  // Keep other open tabs in step.
  window.addEventListener("storage", (e) => {
    if (e.key === KEY || e.key === null) {
      pref = readPref();
      apply();
    }
  });
}

function subscribe(cb: () => void) {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

export function useTheme(): { pref: ThemePref; theme: Theme; setPref: (p: ThemePref) => void } {
  const snapshot = useSyncExternalStore(subscribe, () => `${pref}|${resolve(pref)}`, () => "system|light");
  const [p, t] = snapshot.split("|") as [ThemePref, Theme];
  return { pref: p, theme: t, setPref: setThemePref };
}
