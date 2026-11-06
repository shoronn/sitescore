import { useCallback, useSyncExternalStore } from "react";
import en, { type Messages } from "./locales/en";

/** The site speaks English and Bangla. The choice is remembered on this device. */
export type Lang = "en" | "bn";

const KEY = "sitescore-lang";
// Bangla loads only for visitors who use it, so the English pages stay light.
const DICTS: Record<Lang, Messages | null> = { en, bn: null };
const listeners = new Set<() => void>();
let version = 0;

function loadBangla() {
  if (DICTS.bn) return;
  import("./locales/bn")
    .then((m) => {
      DICTS.bn = m.default;
      version++;
      listeners.forEach((l) => l());
    })
    .catch(() => undefined);
}

/** A link with ?lang=bn (as in the report email) wins, then the saved choice, then the device language. */
function initial(): Lang {
  try {
    const fromUrl = new URLSearchParams(window.location.search).get("lang");
    if (fromUrl === "bn" || fromUrl === "en") {
      window.localStorage.setItem(KEY, fromUrl);
      return fromUrl;
    }
    const saved = window.localStorage.getItem(KEY);
    if (saved === "bn" || saved === "en") return saved;
  } catch {
    /* storage blocked: fall back to the device language */
  }
  const langs = typeof navigator !== "undefined" ? navigator.languages ?? [navigator.language] : [];
  return langs.some((l) => l?.toLowerCase().startsWith("bn")) ? "bn" : "en";
}

let current: Lang = typeof window !== "undefined" ? initial() : "en";

function apply() {
  if (typeof document === "undefined") return;
  document.documentElement.lang = current;
  listeners.forEach((l) => l());
}

export function getLang(): Lang {
  return current;
}

export function setLang(next: Lang) {
  current = next;
  if (next === "bn") loadBangla();
  try {
    window.localStorage.setItem(KEY, next);
  } catch {
    /* the choice lasts for this visit only */
  }
  apply();
}

if (typeof window !== "undefined") {
  document.documentElement.lang = current;
  if (current === "bn") loadBangla();
  window.addEventListener("storage", (e) => {
    if (e.key === KEY && (e.newValue === "bn" || e.newValue === "en")) {
      current = e.newValue;
      if (current === "bn") loadBangla();
      apply();
    }
  });
}

const BN_DIGITS = "০১২৩৪৫৬৭৮৯";

/** 42 -> ৪২ in Bangla; unchanged in English. */
export function digits(value: number | string, lang: Lang = current): string {
  const s = String(value);
  return lang === "bn" ? s.replace(/[0-9]/g, (d) => BN_DIGITS[Number(d)]) : s;
}

export type MessageKey = keyof Messages;
export type Vars = Record<string, string | number>;

/** Look up a phrase and fill in {placeholders}; numbers get Bangla digits in Bangla. */
export function translate(lang: Lang, key: MessageKey, vars?: Vars): string {
  const text = DICTS[lang]?.[key] ?? en[key] ?? String(key);
  if (!vars) return text;
  return text.replace(/\{(\w+)\}/g, (m, name: string) =>
    name in vars ? (typeof vars[name] === "number" ? digits(vars[name], lang) : String(vars[name])) : m,
  );
}

function subscribe(cb: () => void) {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

export function useLang(): Lang {
  // The server-rendered home page is English; the saved choice applies straight after.
  return useSyncExternalStore(subscribe, () => current, () => "en" as Lang);
}

/** Changes when the language changes or its words finish loading. */
function useVersion(): string {
  return useSyncExternalStore(subscribe, () => `${current}:${version}`, () => "en:0");
}

export function useT() {
  const lang = useLang();
  const v = useVersion();
  const t = useCallback((key: MessageKey, vars?: Vars) => translate(lang, key, vars), [lang, v]);
  const n = useCallback((value: number | string) => digits(value, lang), [lang]);
  return { t, n, lang };
}
