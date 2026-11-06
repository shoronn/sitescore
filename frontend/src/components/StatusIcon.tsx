import { AlertTriangle, Check, Loader2, Minus, X } from "lucide-react";
import type { Status } from "../api";
import { useT } from "../i18n";

const BG: Record<Status, string> = {
  pass: "var(--pass)",
  warn: "var(--warn)",
  fail: "var(--fail)",
  not_checked: "var(--neutral)",
};

/** `label` overrides the spoken status, e.g. "Small improvement" for a minor warning. */
export default function StatusIcon({ status, size = 26, label }: { status?: Status; size?: number; label?: string }) {
  const { t } = useT();
  if (!status) {
    return (
      <span className="inline-flex shrink-0 items-center justify-center" style={{ width: size, height: size }} role="img" aria-label={t("status.checking")}>
        <Loader2 className="spin text-3" size={size * 0.75} aria-hidden="true" />
      </span>
    );
  }
  const m = { bg: BG[status], label: label ?? t(`status.${status}`) };
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
