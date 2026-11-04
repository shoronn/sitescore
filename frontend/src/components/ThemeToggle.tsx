import { Check, Monitor, Moon, Sun, type LucideIcon } from "lucide-react";
import { m } from "motion/react";
import { useEffect, useId, useRef, useState } from "react";
import { useTheme, type ThemePref } from "../theme";

const OPTIONS: { value: ThemePref; label: string; icon: LucideIcon }[] = [
  { value: "system", label: "Automatic", icon: Monitor },
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
];

/** Round header button with a small menu: Automatic, Light, Dark. */
export function ThemeMenu() {
  const { pref, theme, setPref } = useTheme();
  const [open, setOpen] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const items = useRef<(HTMLButtonElement | null)[]>([]);
  const menuId = useId();
  const Icon = theme === "dark" ? Moon : Sun;
  // The icon spins in only when the theme changes, not on page load.
  const changed = useRef(false);
  const firstTheme = useRef(theme);
  if (theme !== firstTheme.current) changed.current = true;

  useEffect(() => {
    if (!open) return;
    const current = OPTIONS.findIndex((o) => o.value === pref);
    items.current[current]?.focus();
    const onDown = (e: PointerEvent) => {
      if (!wrap.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", onDown);
    return () => document.removeEventListener("pointerdown", onDown);
  }, [open, pref]);

  const onMenuKey = (e: React.KeyboardEvent) => {
    const i = items.current.findIndex((el) => el === document.activeElement);
    if (e.key === "Escape") {
      e.preventDefault();
      setOpen(false);
      button.current?.focus();
    } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      const next = (i + (e.key === "ArrowDown" ? 1 : OPTIONS.length - 1)) % OPTIONS.length;
      items.current[next]?.focus();
    } else if (e.key === "Tab") {
      setOpen(false);
    }
  };

  return (
    <div className="relative" ref={wrap}>
      <button
        ref={button}
        type="button"
        className="glass icon-btn"
        aria-label={`Appearance: ${OPTIONS.find((o) => o.value === pref)?.label}`}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        onClick={() => setOpen((o) => !o)}
      >
        <m.span
          key={theme}
          initial={changed.current ? { rotate: -45, scale: 0.6 } : false}
          animate={{ rotate: 0, scale: 1 }}
          transition={{ type: "spring", stiffness: 400, damping: 22 }}
          className="flex"
        >
          <Icon size={19} strokeWidth={2.1} aria-hidden="true" />
        </m.span>
      </button>
      {open ? (
        <div
          id={menuId}
          role="menu"
          aria-label="Appearance"
          className="menu-pop glass-float absolute right-0 top-[calc(100%+8px)] z-50 w-48 p-1.5"
          onKeyDown={onMenuKey}
        >
          {OPTIONS.map((o, i) => (
            <button
              key={o.value}
              ref={(el) => {
                items.current[i] = el;
              }}
              type="button"
              role="menuitemradio"
              aria-checked={pref === o.value}
              className="menu-item"
              onClick={() => {
                setPref(o.value);
                setOpen(false);
                button.current?.focus();
              }}
            >
              <o.icon size={17} aria-hidden="true" className="text-2" />
              <span className="flex-1 text-left">{o.label}</span>
              {pref === o.value ? <Check size={17} strokeWidth={2.5} aria-hidden="true" style={{ color: "var(--brand-ink)" }} /> : null}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

/** Three-way segmented control with a sliding thumb, used in the footer. */
export function ThemeSegmented() {
  const { pref, setPref } = useTheme();
  const onKey = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    e.preventDefault();
    const i = OPTIONS.findIndex((o) => o.value === pref);
    const next = OPTIONS[(i + (e.key === "ArrowRight" ? 1 : OPTIONS.length - 1)) % OPTIONS.length];
    setPref(next.value);
    e.currentTarget.querySelector<HTMLButtonElement>(`[data-value="${next.value}"]`)?.focus();
  };
  return (
    <div role="radiogroup" aria-label="Appearance" className="segmented" onKeyDown={onKey}>
      {OPTIONS.map((o) => {
        const on = pref === o.value;
        return (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={on}
            tabIndex={on ? 0 : -1}
            data-value={o.value}
            className="segmented-item relative"
            onClick={() => setPref(o.value)}
          >
            {on ? <m.span layoutId="theme-thumb" className="segmented-thumb absolute inset-0 rounded-capsule" transition={{ type: "spring", stiffness: 500, damping: 38 }} /> : null}
            <span className="relative inline-flex items-center gap-1.5">
              <o.icon size={15} aria-hidden="true" />
              {o.label}
            </span>
          </button>
        );
      })}
    </div>
  );
}
