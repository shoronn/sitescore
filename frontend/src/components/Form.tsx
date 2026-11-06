import { AlertCircle } from "lucide-react";
import { cloneElement, isValidElement, useEffect, useId, useState } from "react";
import { useT } from "../i18n";

/** Label above a control, optional hint, and an error tied to the control for screen readers. */
export function Field({
  label,
  optional,
  error,
  children,
}: {
  label: string;
  optional?: boolean;
  error?: string;
  children: React.ReactElement<{ id?: string; "aria-describedby"?: string; "aria-invalid"?: boolean }>;
}) {
  const id = useId();
  const errId = `${id}-err`;
  const control = isValidElement(children)
    ? cloneElement(children, { id, "aria-describedby": error ? errId : undefined, "aria-invalid": error ? true : undefined })
    : children;
  return (
    <div>
      <label htmlFor={id} className="mb-1.5 flex items-baseline justify-between px-1 text-[14px] font-semibold">
        {label}
        {optional ? <span className="text-3 text-[13px] font-medium"><OptionalLabel /></span> : null}
      </label>
      {control}
      {error ? <ErrorText id={errId}>{error}</ErrorText> : null}
    </div>
  );
}

export function ErrorText({ children, id, className = "" }: { children: React.ReactNode; id?: string; className?: string }) {
  return (
    <p id={id} role="alert" className={`ink-fail mt-1.5 flex items-start gap-1.5 px-1 text-[14px] font-medium leading-snug ${className}`}>
      <AlertCircle size={16} className="mt-[1px] shrink-0" aria-hidden="true" />
      <span>{children}</span>
    </p>
  );
}

function OptionalLabel() {
  return <>{useT().t("optional")}</>;
}

export function useMediaQuery(query: string): boolean {
  const get = () => typeof window !== "undefined" && !!window.matchMedia?.(query).matches;
  const [match, setMatch] = useState(get);
  useEffect(() => {
    const m = window.matchMedia?.(query);
    if (!m) return;
    const on = () => setMatch(m.matches);
    m.addEventListener?.("change", on);
    return () => m.removeEventListener?.("change", on);
  }, [query]);
  return match;
}
