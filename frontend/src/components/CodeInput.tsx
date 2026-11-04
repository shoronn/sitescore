import { useEffect, useRef, useState } from "react";

interface Props {
  value: string;
  onChange: (v: string) => void;
  onComplete: (v: string) => void;
  invalid?: boolean;
  disabled?: boolean;
  /** Changes every time a wrong code comes back, to replay the shake. */
  errorKey?: number;
  describedBy?: string;
}

/** Six boxes backed by one real input, so paste and SMS/email autofill work. */
export default function CodeInput({ value, onChange, onComplete, invalid, disabled, errorKey, describedBy }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [focused, setFocused] = useState(false);
  const [shake, setShake] = useState(false);
  const digits = value.padEnd(6, " ").slice(0, 6).split("");

  useEffect(() => {
    if (!errorKey) return;
    setShake(true);
    const t = setTimeout(() => setShake(false), 420);
    // Back in the boxes, ready for the next try.
    input.current?.focus();
    return () => clearTimeout(t);
  }, [errorKey]);

  return (
    <div className={`relative ${shake ? "shake" : ""}`} onClick={() => input.current?.focus()}>
      <input
        ref={input}
        value={value}
        disabled={disabled}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        onChange={(e) => {
          const v = e.target.value.replace(/\D/g, "").slice(0, 6);
          onChange(v);
          if (v.length === 6) onComplete(v);
        }}
        inputMode="numeric"
        autoComplete="one-time-code"
        pattern="[0-9]*"
        maxLength={6}
        aria-label="6-digit code"
        aria-invalid={invalid || undefined}
        aria-describedby={describedBy}
        className="absolute inset-0 h-full w-full cursor-text opacity-0"
        style={{ caretColor: "transparent" }}
        autoFocus
      />
      <div className="grid grid-cols-6 gap-2" aria-hidden="true">
        {digits.map((d, i) => {
          const active = focused && !disabled && i === Math.min(value.length, 5);
          const filled = d.trim() !== "";
          const border = invalid ? "var(--fail-ink)" : active ? "var(--brand)" : "var(--field-edge)";
          return (
            <div
              key={i}
              className="tabular relative flex h-[58px] items-center justify-center rounded-2xl font-display text-[26px] font-semibold"
              style={{
                background: active ? "var(--field-focus)" : "var(--field-fill)",
                border: `1.5px solid ${border}`,
                boxShadow: active ? "var(--focus-ring)" : undefined,
                opacity: disabled ? 0.6 : 1,
                transition: "border-color .15s ease, box-shadow .15s ease, background-color .15s ease",
              }}
            >
              {filled ? d : active ? <span className="caret h-7 w-[2px] rounded-full" style={{ background: "var(--brand)" }} /> : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}
