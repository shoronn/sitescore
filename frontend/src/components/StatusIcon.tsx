import { AlertTriangle, Check, Loader2, Minus, X } from "lucide-react";
import type { Status } from "../api";

const META: Record<Status, { bg: string; label: string }> = {
  pass: { bg: "var(--pass)", label: "Passed" },
  warn: { bg: "var(--warn)", label: "Could be better" },
  fail: { bg: "var(--fail)", label: "Needs fixing" },
  not_checked: { bg: "var(--neutral)", label: "Not checked" },
};

export default function StatusIcon({ status, size = 26 }: { status?: Status; size?: number }) {
  if (!status) {
    return (
      <span className="inline-flex shrink-0 items-center justify-center" style={{ width: size, height: size }} role="img" aria-label="Checking">
        <Loader2 className="spin text-3" size={size * 0.75} aria-hidden="true" />
      </span>
    );
  }
  const m = META[status];
  const Icon = status === "pass" ? Check : status === "warn" ? AlertTriangle : status === "fail" ? X : Minus;
  return (
    <span
      className="inline-flex shrink-0 items-center justify-center rounded-full"
      style={{ width: size, height: size, background: m.bg }}
      role="img"
      aria-label={m.label}
    >
      <Icon size={size * 0.56} strokeWidth={3} color={status === "warn" ? "#3d2c00" : "#fff"} aria-hidden="true" />
    </span>
  );
}
