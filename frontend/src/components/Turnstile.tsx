import { useEffect, useRef } from "react";

declare global {
  interface Window {
    turnstile?: {
      render: (el: HTMLElement, opts: Record<string, unknown>) => string;
      remove: (id: string) => void;
    };
  }
}

const SRC = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";

function loadScript(): Promise<void> {
  if (window.turnstile) return Promise.resolve();
  const existing = document.querySelector<HTMLScriptElement>(`script[src="${SRC}"]`);
  return new Promise((resolve) => {
    const s = existing ?? Object.assign(document.createElement("script"), { src: SRC, async: true });
    s.addEventListener("load", () => resolve());
    if (!existing) document.head.appendChild(s);
  });
}

/** Cloudflare's bot check. Renders nothing when no site key is configured. */
export default function Turnstile({ siteKey, onToken }: { siteKey: string | null; onToken: (t: string | null) => void }) {
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!siteKey || !box.current) return;
    let id: string | undefined;
    let cancelled = false;
    loadScript().then(() => {
      if (cancelled || !box.current || !window.turnstile) return;
      id = window.turnstile.render(box.current, {
        sitekey: siteKey,
        appearance: "interaction-only",
        theme: document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light",
        callback: (t: string) => onToken(t),
        "expired-callback": () => onToken(null),
        "error-callback": () => onToken(null),
      });
    });
    return () => {
      cancelled = true;
      if (id && window.turnstile) window.turnstile.remove(id);
    };
  }, [siteKey, onToken]);

  if (!siteKey) return null;
  return <div ref={box} className="flex justify-center" />;
}
