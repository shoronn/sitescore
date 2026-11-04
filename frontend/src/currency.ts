import { useSyncExternalStore } from "react";

/** Prices are shown in US dollars by default; visitors can switch to Bangladeshi taka. */
export type Currency = "usd" | "bdt";

const KEY = "sitescore-currency";
const listeners = new Set<() => void>();

function read(): Currency {
  try {
    return window.localStorage.getItem(KEY) === "bdt" ? "bdt" : "usd";
  } catch {
    return "usd";
  }
}

let current: Currency = typeof window !== "undefined" ? read() : "usd";

export function setCurrency(next: Currency) {
  current = next;
  try {
    window.localStorage.setItem(KEY, next);
  } catch {
    /* storage blocked: the choice lasts for this visit only */
  }
  listeners.forEach((l) => l());
}

if (typeof window !== "undefined") {
  window.addEventListener("storage", (e) => {
    if (e.key === KEY) {
      current = read();
      listeners.forEach((l) => l());
    }
  });
}

export function useCurrency(): [Currency, (c: Currency) => void] {
  const value = useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    () => current,
    () => "usd" as Currency,
  );
  return [value, setCurrency];
}

/** Whole-number prices: "$40" or "Tk 5,000". */
export function formatPrice(amount: number, currency: Currency): string {
  const n = Math.round(amount).toLocaleString("en-US");
  return currency === "usd" ? `$${n}` : `Tk ${n}`;
}

/** Used until the server's prices arrive, and if they cannot be loaded. */
export const DEFAULT_PRICES: Record<Currency, number> = { usd: 40, bdt: 5000 };
