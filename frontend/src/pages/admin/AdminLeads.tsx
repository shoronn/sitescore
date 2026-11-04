import { Check, ChevronLeft, ChevronRight, Download, Inbox, Loader2, PhoneCall, Search, Trash2, X } from "lucide-react";
import { m } from "motion/react";
import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { adminApi, type ApiError, type LeadQuery, type LeadRow, type SalesStatus, type Stats } from "../../api";
import { ErrorText, Field } from "../../components/Form";
import Sheet from "../../components/Sheet";
import { EASE_OUT } from "../../motion";
import { AdminHeader, ScoreBadge, STATUS_LABEL, StatusPill, timeAgo, useStaff } from "./shared";

const FILTERS: { key: string; label: string; query: LeadQuery }[] = [
  { key: "callback", label: "Wants a call", query: { callback: true } },
  { key: "all", label: "All", query: {} },
  ...(["new", "contacted", "interested", "won", "lost"] as SalesStatus[]).map((s) => ({
    key: s,
    label: STATUS_LABEL[s],
    query: { status: s },
  })),
];

export default function AdminLeads() {
  const staff = useStaff();
  const [params, setParams] = useSearchParams();
  const filter = params.get("f") ?? "all";
  const page = Number(params.get("page") ?? "1");
  const [search, setSearch] = useState(params.get("q") ?? "");
  const [stats, setStats] = useState<Stats | null>(null);
  const [data, setData] = useState<{ total: number; per_page: number; leads: LeadRow[] } | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const location = useLocation();
  const navigate = useNavigate();
  // A message passed from the page that sent us here, e.g. "Deleted Karim Shop."
  const [notice, setNotice] = useState<string | null>((location.state as { notice?: string } | null)?.notice ?? null);
  const [reload, setReload] = useState(0);
  useEffect(() => {
    if (!notice) return;
    navigate(location.pathname + location.search, { replace: true, state: null });
    const t = setTimeout(() => setNotice(null), 4000);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [notice]);

  useEffect(() => {
    document.title = "Leads | SiteScore";
  }, []);

  const query: LeadQuery = { ...(FILTERS.find((f) => f.key === filter)?.query ?? {}), q: params.get("q") ?? undefined, page };

  useEffect(() => {
    if (!staff) return;
    adminApi.stats().then(setStats).catch(() => undefined);
  }, [staff, reload]);

  useEffect(() => {
    if (!staff) return;
    setData(null);
    setLoadError(null);
    adminApi.leads(query).then(setData).catch((e) => setLoadError(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [staff, params.toString(), reload]);

  const set = (next: Record<string, string | null>) => {
    const p = new URLSearchParams(params);
    for (const [k, v] of Object.entries(next)) (v ? p.set(k, v) : p.delete(k));
    if (!("page" in next)) p.delete("page");
    setParams(p);
  };

  const pages = data ? Math.max(1, Math.ceil(data.total / data.per_page)) : 1;

  return (
    <>
      <AdminHeader staff={staff} />
      <main className="shell relative z-10 pb-16 pt-6">
        <h1 className="px-1 font-display text-[30px] font-bold tracking-tight">Leads</h1>
        {notice ? (
          <p className="glass rise-enter mt-3 flex items-center gap-2.5 rounded-2xl px-4 py-3 text-[15px] font-semibold" role="status">
            <Check size={18} strokeWidth={2.6} className="ink-pass shrink-0" aria-hidden="true" /> {notice}
          </p>
        ) : null}

        <section className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4" aria-label="Summary">
          <Tile label="Want a call" value={stats?.callbacks_waiting} highlight onClick={() => set({ f: "callback" })} />
          <Tile label="New leads, 7 days" value={stats?.leads_7d} />
          <Tile label="Scans, 24 hours" value={stats?.scans_today} />
          <Tile label="Won, 30 days" value={stats?.won_30d} />
        </section>

        <div className="mt-6 flex flex-col gap-3 md:flex-row md:items-center">
          <form
            role="search"
            className="glass search-pill flex flex-1 items-center gap-2 rounded-capsule pl-4 pr-1.5"
            onSubmit={(e) => {
              e.preventDefault();
              set({ q: search.trim() || null });
            }}
          >
            <Search size={18} className="text-3 shrink-0" aria-hidden="true" />
            <input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search name, email, phone or website"
              aria-label="Search leads"
              enterKeyHint="search"
              className="h-12 w-full min-w-0 bg-transparent text-[16px] outline-none placeholder:text-[var(--label-3)] [&::-webkit-search-cancel-button]:hidden"
            />
            {params.get("q") || search ? (
              <button
                type="button"
                className="text-2 flex h-9 w-9 shrink-0 items-center justify-center rounded-full"
                style={{ background: "var(--field-fill)" }}
                aria-label="Clear search"
                onClick={() => {
                  setSearch("");
                  set({ q: null });
                }}
              >
                <X size={16} strokeWidth={2.4} aria-hidden="true" />
              </button>
            ) : null}
          </form>
          <div className="flex shrink-0 gap-3">
            <a href={adminApi.csvUrl(query)} className="btn-glass flex-1 md:flex-none">
              <Download size={18} aria-hidden="true" /> Export CSV
            </a>
            {staff?.role === "admin" ? (
              <ClearAll
                total={stats ? Object.values(stats.by_status).reduce((a, b) => a + b, 0) : null}
                onCleared={(n) => {
                  setNotice(`Cleared ${n} ${n === 1 ? "lead" : "leads"} and their scans.`);
                  setReload((r) => r + 1);
                }}
              />
            ) : null}
          </div>
        </div>

        <nav className="-mx-5 mt-3 flex gap-2 overflow-x-auto px-5 py-1 [scrollbar-width:none]" aria-label="Filter leads">
          {FILTERS.map((f) => {
            const active = f.key === filter;
            const count = f.key === "callback" ? stats?.callbacks_waiting : stats && f.key in stats.by_status ? stats.by_status[f.key as SalesStatus] : undefined;
            return (
              <button
                key={f.key}
                onClick={() => set({ f: f.key === "all" ? null : f.key })}
                aria-pressed={active}
                className={`chip relative ${active ? "" : "glass"}`}
              >
                {active ? <m.span layoutId="filter-thumb" className="chip-thumb absolute inset-0 rounded-capsule" transition={{ type: "spring", stiffness: 500, damping: 40 }} /> : null}
                <span className="relative">{f.label}</span>
                {count !== undefined ? <span className="tabular relative text-[13px] font-semibold opacity-60">{count}</span> : null}
              </button>
            );
          })}
        </nav>

        <div className="glass mt-3 overflow-hidden rounded-glass">
        {data && data.leads.length ? (
          <div className="text-3 hairline hidden border-b px-5 py-2.5 text-[12px] font-semibold uppercase tracking-[0.06em] lg:grid lg:grid-cols-[40px_40px_minmax(0,1.4fr)_minmax(0,1.1fr)_150px_96px_18px] lg:gap-5 lg:px-5" aria-hidden="true">
            <span title="AI agent readiness">AI</span>
            <span>Health</span>
            <span>Lead</span>
            <span>Website</span>
            <span>Status</span>
            <span>When</span>
            <span />
          </div>
        ) : null}
        <ul aria-busy={!data && !loadError}>
          {loadError ? (
            <li className="px-5 py-6"><ErrorText>{loadError}</ErrorText></li>
          ) : !data ? (
            Array.from({ length: 5 }, (_, i) => (
              <li key={i} className={`flex items-center gap-3 px-4 py-4 ${i ? "hairline border-t" : ""}`} aria-hidden="true">
                <span className="skeleton h-10 w-10 shrink-0 rounded-[12px]" />
                <span className="flex-1 space-y-2">
                  <span className="skeleton block h-4 w-2/5" />
                  <span className="skeleton block h-3.5 w-3/4" />
                </span>
              </li>
            ))
          ) : data.leads.length === 0 ? (
            <li className="flex flex-col items-center px-5 py-12 text-center">
              <span className="flex h-12 w-12 items-center justify-center rounded-full" style={{ background: "var(--field-fill)" }} aria-hidden="true">
                <Inbox size={22} className="text-2" />
              </span>
              <p className="mt-3 text-[16px] font-semibold">{params.get("q") ? "No leads match your search" : "No leads here yet"}</p>
              <p className="text-2 mt-1 max-w-[40ch] text-[14px] leading-snug">
                {params.get("q") ? "Try a different name, email, phone number or website." : "New leads show up as soon as visitors enter their email."}
              </p>
            </li>
          ) : (
            data.leads.map((l, i) => {
              const who = l.business_name || l.name || l.email;
              const contact = l.business_name || l.name ? l.email : l.phone || "No phone";
              const when = timeAgo(l.callback_requested_at ?? l.created_at);
              const wantsCall = Boolean(l.callback_requested_at && l.sales_status === "new");
              return (
                <m.li
                  key={l.id}
                  className={i ? "hairline border-t" : ""}
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.3, ease: EASE_OUT, delay: Math.min(i, 12) * 0.025 }}
                >
                  <Link to={`/admin/leads/${l.id}`} className="row-btn grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 px-4 py-3.5 lg:grid-cols-[40px_40px_minmax(0,1.4fr)_minmax(0,1.1fr)_150px_96px_18px] lg:gap-5 lg:px-5">
                    <span className="flex gap-1.5 lg:contents">
                      <ScoreBadge score={l.latest_scan?.agent_score ?? null} kind="agent" />
                      <ScoreBadge score={l.latest_scan?.score ?? null} band={l.latest_scan?.band ?? null} />
                    </span>
                    <span className="min-w-0">
                      <span className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
                        <span className="min-w-0 truncate text-[16px] font-semibold">{who}</span>
                        <span className="lg:hidden"><StatusPill status={l.sales_status} /></span>
                        {wantsCall ? (
                          <span className="ink-brand inline-flex items-center gap-1 text-[13px] font-semibold lg:hidden">
                            <PhoneCall size={13} aria-hidden="true" /> Wants a call
                          </span>
                        ) : null}
                      </span>
                      <span className="text-2 mt-0.5 block truncate text-[14px] lg:hidden">
                        {[l.latest_scan?.host ?? "No scan yet", contact, when].join(" · ")}
                      </span>
                      <span className="text-2 mt-0.5 hidden truncate text-[14px] lg:block">{contact}</span>
                    </span>
                    <span className="hidden min-w-0 lg:block">
                      <span className="block truncate text-[15px] font-medium">{l.latest_scan?.host ?? "No scan yet"}</span>
                      <span className="text-2 block truncate text-[14px]">{l.phone || "No phone"}</span>
                    </span>
                    <span className="hidden min-w-0 flex-col items-start gap-1 lg:flex">
                      <StatusPill status={l.sales_status} />
                      {wantsCall ? (
                        <span className="ink-brand inline-flex items-center gap-1 text-[12px] font-semibold">
                          <PhoneCall size={12} aria-hidden="true" /> Wants a call
                        </span>
                      ) : null}
                    </span>
                    <span className="text-2 hidden text-[14px] lg:block">{when}</span>
                    <ChevronRight size={18} className="text-3 shrink-0" aria-hidden="true" />
                  </Link>
                </m.li>
              );
            })
          )}
        </ul>
        </div>

        {data && pages > 1 ? (
          <nav className="mt-4 flex items-center justify-between gap-3" aria-label="Pages">
            <button className="btn-glass min-h-[44px] px-4" disabled={page <= 1} onClick={() => set({ page: String(page - 1) })}>
              <ChevronLeft size={18} aria-hidden="true" /> Previous
            </button>
            <span className="text-2 tabular text-[14px] font-medium">Page {page} of {pages}</span>
            <button className="btn-glass min-h-[44px] px-4" disabled={page >= pages} onClick={() => set({ page: String(page + 1) })}>
              Next <ChevronRight size={18} aria-hidden="true" />
            </button>
          </nav>
        ) : null}
      </main>
    </>
  );
}

function Tile({ label, value, highlight, onClick }: { label: string; value?: number; highlight?: boolean; onClick?: () => void }) {
  const inner = (
    <>
      <div className="tabular font-display text-[30px] font-bold leading-none tracking-tight" style={{ color: highlight && value ? "var(--brand-ink)" : undefined }}>
        {value ?? <span className="skeleton inline-block h-7 w-10 align-middle" aria-label="Loading" />}
      </div>
      <div className="text-2 mt-2 text-[14px] font-medium">{label}</div>
    </>
  );
  return onClick ? (
    <button onClick={onClick} className="glass row-btn rounded-[24px] p-4 text-left">
      {inner}
    </button>
  ) : (
    <div className="glass rounded-[24px] p-4">{inner}</div>
  );
}


/** Admins only: delete every lead and scan, after typing DELETE ALL. */
function ClearAll({ total, onCleared }: { total: number | null; onCleared: (n: number) => void }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ready = text.trim().toUpperCase() === "DELETE ALL";
  const close = () => {
    if (busy) return;
    setOpen(false);
    setText("");
    setError(null);
  };
  const clear = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!ready) return;
    setBusy(true);
    setError(null);
    try {
      const r = await adminApi.clearLeads(text);
      setBusy(false);
      setOpen(false);
      setText("");
      onCleared(r.leads);
    } catch (err) {
      setError((err as ApiError).message);
      setBusy(false);
    }
  };
  return (
    <>
      <button type="button" className="btn-glass ink-fail flex-1 md:flex-none" onClick={() => setOpen(true)} disabled={total === 0}>
        <Trash2 size={18} aria-hidden="true" /> Clear all
      </button>
      <Sheet open={open} title="Clear all leads?" onClose={close}>
        <form onSubmit={clear} className="space-y-4">
          <p className="text-2 text-[16px] leading-snug">
            This deletes {total === null ? "every lead" : <span className="font-semibold" style={{ color: "var(--label)" }}>all {total} leads</span>}, with
            their scans and results links, for everyone on the team. Export a CSV first if you need a copy. This cannot be undone.
          </p>
          <Field label="Type DELETE ALL to confirm" error={error ?? undefined}>
            <input
              className="field"
              value={text}
              onChange={(e) => setText(e.target.value)}
              autoComplete="off"
              autoCapitalize="characters"
              spellCheck={false}
              placeholder="DELETE ALL"
            />
          </Field>
          <div className="grid gap-2.5 sm:grid-cols-2">
            <button type="button" className="btn-glass" onClick={close} disabled={busy}>
              Cancel
            </button>
            <button type="submit" className="btn-danger" disabled={!ready || busy} aria-busy={busy || undefined}>
              {busy ? <Loader2 size={19} className="spin" aria-hidden="true" /> : <Trash2 size={18} aria-hidden="true" />} Clear all
            </button>
          </div>
        </form>
      </Sheet>
    </>
  );
}

