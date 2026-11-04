import { Loader2, LogOut, Minus } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { adminApi, ApiError, type SalesStatus, type Staff } from "../../api";
import { Brand } from "../../components/Header";
import { ThemeMenu } from "../../components/ThemeToggle";

export const STATUS_LABEL: Record<SalesStatus, string> = {
  new: "New",
  contacted: "Contacted",
  interested: "Interested",
  won: "Won",
  lost: "Lost",
};

export const STATUS_STYLE: Record<SalesStatus, { bg: string; fg: string }> = {
  new: { bg: "var(--tint-brand)", fg: "var(--brand-ink)" },
  contacted: { bg: "var(--tint-blue)", fg: "var(--blue-ink)" },
  interested: { bg: "var(--tint-purple)", fg: "var(--purple-ink)" },
  won: { bg: "var(--tint-pass)", fg: "var(--pass-ink)" },
  lost: { bg: "var(--field-fill)", fg: "var(--label-2)" },
};

export function StatusPill({ status }: { status: SalesStatus }) {
  const s = STATUS_STYLE[status];
  return (
    <span className="inline-flex shrink-0 items-center rounded-capsule px-2.5 py-[3px] text-[12px] font-semibold leading-tight" style={{ background: s.bg, color: s.fg }}>
      {STATUS_LABEL[status]}
    </span>
  );
}

const BAND: Record<string, { bg: string; fg: string }> = {
  good: { bg: "var(--tint-pass)", fg: "var(--pass-ink)" },
  attention: { bg: "var(--tint-warn)", fg: "var(--warn-ink)" },
  risk: { bg: "var(--tint-fail)", fg: "var(--fail-ink)" },
};

/** Same colour bands as the health score: 80 and up good, 50 and up attention. */
export function bandOf(score: number | null | undefined): string | null {
  if (score === null || score === undefined) return null;
  return score >= 80 ? "good" : score >= 50 ? "attention" : "risk";
}

export function ScoreBadge({ score, band, kind = "health" }: { score: number | null; band?: string | null; kind?: "health" | "agent" }) {
  const b = band === undefined ? bandOf(score) : band;
  const c = (b && BAND[b]) || { bg: "var(--field-fill)", fg: "var(--label-3)" };
  const name = kind === "agent" ? "AI agent readiness" : "Health score";
  return (
    <span
      className="tabular inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] text-[15px] font-bold"
      style={{ background: c.bg, color: c.fg }}
      aria-label={score === null ? `${name}: none yet` : `${name} ${score}`}
      title={name}
    >
      {score ?? <Minus size={16} aria-hidden="true" />}
    </span>
  );
}

export function timeAgo(iso: string): string {
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  if (s < 86400 * 7) return `${Math.floor(s / 86400)} d ago`;
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

/** Bangladeshi local numbers (01XXXXXXXXX) become 8801XXXXXXXXX for wa.me links. */
export function whatsappNumber(phone: string): string {
  const digits = phone.replace(/\D/g, "");
  if (digits.startsWith("01") && digits.length === 11) return `88${digits}`;
  return digits;
}

/** Loads the signed-in staff member, or sends them to the sign-in page. */
export function useStaff(): Staff | null {
  const [staff, setStaff] = useState<Staff | null>(null);
  const navigate = useNavigate();
  useEffect(() => {
    adminApi
      .me()
      .then((r) => setStaff(r.staff))
      .catch((e: ApiError) => {
        if (e.status === 401) navigate("/admin/login", { replace: true });
      });
  }, [navigate]);
  return staff;
}

export function AdminHeader({ staff }: { staff: Staff | null }) {
  const navigate = useNavigate();
  const [leaving, setLeaving] = useState(false);
  return (
    <header className="shell relative z-20 flex items-center justify-between gap-3 pt-[max(16px,env(safe-area-inset-top))]">
      <Brand to="/admin" sub="Sales" label="SiteScore sales, leads" />
      <div className="flex min-w-0 items-center gap-2">
        {staff ? (
          <button
            className="btn-glass min-h-[44px] min-w-0 gap-2 px-4 text-[14px]"
            aria-label={`Sign out ${staff.name}`}
            disabled={leaving}
            onClick={async () => {
              setLeaving(true);
              await adminApi.logout().catch(() => undefined);
              navigate("/admin/login");
            }}
          >
            <span className="max-w-[28vw] truncate">{staff.name}</span>
            {leaving ? <Loader2 size={16} className="spin" aria-hidden="true" /> : <LogOut size={16} aria-hidden="true" />}
          </button>
        ) : null}
        <ThemeMenu />
      </div>
    </header>
  );
}
