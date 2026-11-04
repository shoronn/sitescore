export type Status = "pass" | "warn" | "fail" | "not_checked";
export type Band = "good" | "attention" | "risk";

export interface CheckResult {
  key: string;
  name: string;
  category: string;
  weight: number;
  status: Status;
  points: number;
  title: string;
  summary: string;
  why: string;
  fix: string;
  offer: string;
  critical: boolean;
  evidence: Record<string, unknown>;
}

export interface AgentScore {
  score: number | null;
  level: "ready" | "almost" | "partly" | "started" | "not_ready" | null;
  label: string | null;
  band: Band | null;
}

export interface CategoryScore {
  key: string;
  label: string;
  score: number | null;
  earned: number;
  available: number;
}

export interface Scan {
  token: string;
  status: "queued" | "running" | "done" | "failed";
  host: string;
  created_at: string;
  finished_at: string | null;
  progress: { done: number; total: number };
  score: number | null;
  band: Band | null;
  band_label: string | null;
  capped: boolean;
  coverage: number | null;
  /** AI agent readiness, scored separately from the health score above. */
  agent: AgentScore;
  categories: CategoryScore[];
  results: CheckResult[];
  pending: string[];
  error?: { code: string; message: string };
  is_owner: boolean;
  callback_requested: boolean;
  owner_email: string | null;
  report_emailed: boolean;
  /** sent, pending (being prepared), failed (last try failed; retries continue), none (scan not done). */
  report_status: "sent" | "pending" | "failed" | "none";
}

export interface PublicConfig {
  turnstile_site_key: string | null;
  whatsapp_number: string | null;
  /** "Call us" number, country code first, digits only. */
  contact_phone?: string | null;
  /** Fix-It Starter Pack one-time price, whole numbers. */
  prices?: { usd: number; bdt: number };
}

/** The visitor's session. Only the address: stored contact details are never sent back. */
export interface Lead {
  email: string;
}

export class ApiError extends Error {
  status: number;
  code: string;
  field?: string;
  constructor(status: number, body: { error?: string; message?: string; field?: string }) {
    super(body.message || "Something went wrong. Please try again.");
    this.status = status;
    this.code = body.error || "error";
    this.field = body.field;
  }
}

// Empty in development (Vite proxies /api). In production: https://api-sitescore.maktechgroup.com
export const API_BASE = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api${path}`, {
      credentials: "include", // the session cookie lives on the API domain
      headers: init?.body ? { "Content-Type": "application/json" } : undefined,
      ...init,
    });
  } catch {
    throw new ApiError(0, { error: "offline", message: "Could not reach SiteScore. Check your connection and try again." });
  }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(res.status, body);
  return body as T;
}

const post = <T>(path: string, data?: unknown) =>
  call<T>(path, { method: "POST", body: data === undefined ? undefined : JSON.stringify(data) });

export const api = {
  config: () => call<PublicConfig>("/config"),
  me: () => call<{ lead: Lead }>("/me"),
  /** Checks the address (format, a domain that takes mail, no throwaway inboxes) and signs in. */
  signUp: (data: {
    email: string;
    name?: string;
    business_name?: string;
    phone?: string;
    turnstile_token?: string;
  }) => post<{ ok: true; lead: Lead }>("/auth/start", data),
  startScan: (url: string) => post<{ token: string; reused: boolean }>("/scans", { url }),
  scan: (token: string) => call<Scan>(`/scans/${encodeURIComponent(token)}`),
  requestCallback: (token: string) => post<{ ok: true }>(`/scans/${encodeURIComponent(token)}/callback`),
  reportUrl: (token: string) => `${API_BASE}/api/scans/${encodeURIComponent(token)}/report.pdf`,
};

// ---------------------------------------------------------------- sales dashboard

export type SalesStatus = "new" | "contacted" | "interested" | "won" | "lost";

export interface Staff {
  id: number;
  email: string;
  name: string;
  role: string;
}

export interface LeadRow {
  id: number;
  email: string;
  name: string | null;
  business_name: string | null;
  phone: string | null;
  sales_status: SalesStatus;
  sales_owner: string | null;
  callback_requested_at: string | null;
  created_at: string;
  scan_count: number;
  latest_scan: { token: string; host: string; score: number | null; band: string | null; agent_score: number | null; status: string; created_at: string } | null;
}

export interface LeadDetail extends LeadRow {
  notes: string | null;
  consent_at: string | null;
  scans: {
    token: string; host: string; status: string; score: number | null; band: string | null; created_at: string;
    agent_score: number | null;
    emailed: boolean; report_status: "sent" | "pending" | "failed" | "none"; report_error: string | null;
    /** Why the speed test gave no result (staff only), e.g. "timeout No result within 180 s." */
    speed_error: string | null;
  }[];
}

export interface Stats {
  leads_7d: number;
  callbacks_waiting: number;
  scans_today: number;
  won_30d: number;
  by_status: Record<SalesStatus, number>;
}

export type LoginStep =
  | { step: "code" }
  | { step: "enroll"; enroll_token: string; secret: string; qr_svg: string }
  | { step: "done"; staff: Staff };

export interface LeadQuery {
  q?: string;
  status?: SalesStatus;
  callback?: boolean;
  page?: number;
}

function qs(params: LeadQuery): string {
  const p = new URLSearchParams();
  if (params.q) p.set("q", params.q);
  if (params.status) p.set("status", params.status);
  if (params.callback) p.set("callback", "true");
  if (params.page && params.page > 1) p.set("page", String(params.page));
  const s = p.toString();
  return s ? `?${s}` : "";
}

export const adminApi = {
  login: (email: string, password: string, code?: string) => post<LoginStep>("/admin/login", { email, password, code }),
  enroll: (enroll_token: string, code: string) => post<LoginStep>("/admin/enroll", { enroll_token, code }),
  logout: () => post<{ ok: true }>("/admin/logout"),
  me: () => call<{ staff: Staff }>("/admin/me"),
  stats: () => call<Stats>("/admin/stats"),
  leads: (q: LeadQuery) => call<{ total: number; page: number; per_page: number; leads: LeadRow[] }>(`/admin/leads${qs(q)}`),
  lead: (id: number) => call<LeadDetail>(`/admin/leads/${id}`),
  updateLead: (id: number, data: { sales_status?: SalesStatus; sales_owner?: string; notes?: string }) =>
    call<{ ok: true; sales_status: SalesStatus; sales_owner: string | null; notes: string | null }>(`/admin/leads/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  sendReport: (token: string) => post<{ ok: true }>(`/admin/scans/${encodeURIComponent(token)}/send-report`),
  /** Delete one lead with all its scans. */
  deleteLead: (id: number) => call<{ ok: true; scans: number }>(`/admin/leads/${id}`, { method: "DELETE" }),
  /** Delete every lead and scan. Admin accounts only; `confirm` must be "DELETE ALL". */
  clearLeads: (confirm: string) => post<{ ok: true; leads: number; scans: number }>("/admin/leads/clear", { confirm }),
  csvUrl: (q: LeadQuery) => `${API_BASE}/api/admin/leads.csv${qs({ ...q, page: undefined })}`,
};
