import { ArrowLeft, Check, Download, ExternalLink, Loader2, Mail, MailCheck, MailWarning, MessageCircle, Phone, PhoneCall, SearchX, Send, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { adminApi, api, ApiError, type LeadDetail, type SalesStatus } from "../../api";
import { ErrorText } from "../../components/Form";
import Sheet from "../../components/Sheet";
import { AdminHeader, ScoreBadge, STATUS_LABEL, STATUS_STYLE, timeAgo, useStaff, whatsappNumber } from "./shared";

const STATUSES: SalesStatus[] = ["new", "contacted", "interested", "won", "lost"];

export default function AdminLead() {
  const staff = useStaff();
  const { id = "" } = useParams();
  const [lead, setLead] = useState<LeadDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<SalesStatus>("new");
  const [owner, setOwner] = useState("");
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!staff) return;
    adminApi
      .lead(Number(id))
      .then((l) => {
        setLead(l);
        setStatus(l.sales_status);
        setOwner(l.sales_owner ?? "");
        setNotes(l.notes ?? "");
      })
      .catch((e: ApiError) => setError(e.message));
  }, [staff, id]);

  const dirty = lead !== null && (status !== lead.sales_status || owner !== (lead.sales_owner ?? "") || notes !== (lead.notes ?? ""));

  useEffect(() => {
    if (lead) document.title = `${lead.business_name || lead.name || lead.email} | SiteScore leads`;
  }, [lead]);

  // Warn before closing the tab with unsaved notes.
  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const save = async () => {
    if (!lead) return;
    setSaving(true);
    setError(null);
    try {
      const r = await adminApi.updateLead(lead.id, { sales_status: status, sales_owner: owner, notes });
      setLead({ ...lead, sales_status: r.sales_status, sales_owner: r.sales_owner, notes: r.notes });
      setOwner(r.sales_owner ?? "");
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <AdminHeader staff={staff} />
      <main className="shell relative z-10 pb-20 pt-6">
        <Link to="/admin" className="link-quiet -ml-1 px-1 text-[15px]">
          <ArrowLeft size={16} aria-hidden="true" /> Leads
        </Link>
        {!lead ? (
          error ? (
            <div className="glass mt-6 flex flex-col items-center rounded-glass px-6 py-10 text-center">
              <SearchX size={26} className="text-2" aria-hidden="true" />
              <p className="mt-3 text-[16px] font-semibold">Lead not found</p>
              <p className="text-2 mt-1 text-[14px]">{error}</p>
            </div>
          ) : (
            <div className="mt-4 space-y-3" aria-busy="true" aria-label="Loading lead">
              <span className="skeleton block h-8 w-1/2" />
              <span className="skeleton block h-4 w-3/4" />
              <span className="skeleton mt-6 block h-48 w-full rounded-glass" />
            </div>
          )
        ) : (
          <>
            <h1 className="mt-2 font-display text-[28px] font-bold leading-tight tracking-tight">{lead.business_name || lead.name || lead.email}</h1>
            <p className="text-2 text-[15px]">
              {[lead.name && lead.business_name ? lead.name : null, lead.email, lead.phone].filter(Boolean).join(" · ")}
            </p>
            {lead.callback_requested_at ? (
              <p className="ink-brand mt-2 inline-flex items-center gap-1.5 text-[15px] font-semibold">
                <PhoneCall size={16} aria-hidden="true" /> Asked for a call {timeAgo(lead.callback_requested_at)}
              </p>
            ) : null}

            <div className="mt-4 grid grid-cols-3 gap-2 sm:max-w-md">
              {lead.phone ? (
                <a className="btn-glass min-h-[64px] flex-col gap-1 rounded-[20px] py-2 text-[13px]" href={`tel:${lead.phone}`}>
                  <Phone size={20} className="ink-pass" aria-hidden="true" /> Call
                </a>
              ) : null}
              {lead.phone ? (
                <a className="btn-glass min-h-[64px] flex-col gap-1 rounded-[20px] py-2 text-[13px]" href={`https://wa.me/${whatsappNumber(lead.phone)}`} target="_blank" rel="noreferrer">
                  <MessageCircle size={20} className="ink-pass" aria-hidden="true" /> WhatsApp
                </a>
              ) : null}
              <a className="btn-glass min-h-[64px] flex-col gap-1 rounded-[20px] py-2 text-[13px]" href={`mailto:${lead.email}`}>
                <Mail size={20} className="ink-brand" aria-hidden="true" /> Email
              </a>
            </div>

            <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)] xl:gap-8">
              <section className="glass rounded-glass p-5" aria-labelledby="follow-up">
                <h2 id="follow-up" className="font-display text-[19px] font-bold tracking-tight">Follow-up</h2>
                <div className="mt-3 flex flex-wrap gap-2" role="radiogroup" aria-label="Sales status">
                  {STATUSES.map((s) => {
                    const active = s === status;
                    return (
                      <button
                        key={s}
                        role="radio"
                        aria-checked={active}
                        onClick={() => setStatus(s)}
                        className="inline-flex min-h-[40px] items-center gap-1.5 rounded-capsule px-3.5 text-[15px] font-semibold transition-colors"
                        style={{
                          background: active ? STATUS_STYLE[s].bg : "var(--field-fill)",
                          color: active ? STATUS_STYLE[s].fg : "var(--label-2)",
                          boxShadow: active ? `inset 0 0 0 1.5px ${STATUS_STYLE[s].fg}` : "inset 0 0 0 1px var(--field-edge)",
                        }}
                      >
                        {active ? <Check size={15} strokeWidth={2.8} aria-hidden="true" /> : null}
                        {STATUS_LABEL[s]}
                      </button>
                    );
                  })}
                </div>
                <label className="mt-4 block">
                  <span className="mb-1.5 block px-1 text-[14px] font-semibold">Owner</span>
                  <input className="field" value={owner} onChange={(e) => setOwner(e.target.value)} placeholder="Who is handling this lead" />
                </label>
                <label className="mt-3 block">
                  <span className="mb-1.5 block px-1 text-[14px] font-semibold">Notes</span>
                  <textarea
                    className="field min-h-[120px] py-3"
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    placeholder="What was discussed, what they need, next step"
                  />
                </label>
                {error ? <ErrorText className="mt-2">{error}</ErrorText> : null}
                {saved && !dirty ? (
                  <p className="mt-4 flex min-h-[52px] items-center justify-center gap-2 rounded-capsule text-[16px] font-semibold" style={{ background: "var(--tint-pass)" }} role="status">
                    <Check size={19} strokeWidth={2.6} className="ink-pass" aria-hidden="true" /> Saved
                  </p>
                ) : (
                  <button className="btn-primary mt-4 w-full" onClick={save} disabled={!dirty || saving} aria-busy={saving || undefined}>
                    {saving ? <Loader2 className="spin" size={20} aria-hidden="true" /> : null}
                    {saving ? "Saving..." : dirty ? "Save changes" : "No changes to save"}
                  </button>
                )}
              </section>

              <section aria-labelledby="scans">
                <h2 id="scans" className="px-1 font-display text-[19px] font-bold tracking-tight">Scans</h2>
                <ul className="glass mt-3 overflow-hidden rounded-glass">
                  {lead.scans.map((s, i) => (
                    <li key={s.token} className={`px-4 py-3.5 ${i ? "hairline border-t" : ""}`}>
                      <div className="flex items-center gap-3">
                        <span className="flex gap-1.5">
                          <ScoreBadge score={s.agent_score} kind="agent" />
                          <ScoreBadge score={s.score} band={s.band} />
                        </span>
                        <div className="min-w-0 flex-1">
                          <div className="truncate text-[16px] font-semibold">{s.host}</div>
                          <div className="text-2 text-[14px]">
                            AI {s.agent_score ?? "--"} · Health {s.score ?? "--"} · {timeAgo(s.created_at)}
                          </div>
                        </div>
                      </div>
                      {s.speed_error ? (
                        <p className="text-2 mt-2 pl-[98px] text-[13px] leading-snug">
                          <span className="font-semibold">Speed test gave no result:</span> {s.speed_error}
                        </p>
                      ) : null}
                      <ReportState scan={s} onSent={(next) => setLead({ ...lead, scans: lead.scans.map((x) => (x.token === s.token ? { ...x, ...next } : x)) })} />
                      <div className="mt-2.5 flex flex-wrap gap-2 pl-[98px]">
                        <a className="btn-glass min-h-[38px] px-3.5 text-[14px]" href={`/scan/${s.token}`} target="_blank" rel="noreferrer">
                          <ExternalLink size={15} aria-hidden="true" /> Results
                        </a>
                        {s.status === "done" ? (
                          <a className="btn-glass min-h-[38px] px-3.5 text-[14px]" href={api.reportUrl(s.token)}>
                            <Download size={15} aria-hidden="true" /> PDF
                          </a>
                        ) : null}
                      </div>
                    </li>
                  ))}
                </ul>
                <p className="text-2 mt-3 px-1 text-[13px] leading-snug">
                  Signed up {timeAgo(lead.created_at)}{lead.consent_at ? `, accepted the privacy notice on ${new Date(lead.consent_at).toLocaleDateString("en-GB")}` : ""}.
                </p>
                <DeleteLead lead={lead} />
              </section>
            </div>
          </>
        )}
      </main>
    </>
  );
}

type ScanRow = LeadDetail["scans"][number];

/** Report email state for one scan, with a way to send it again. */
function ReportState({ scan, onSent }: { scan: ScanRow; onSent: (next: Partial<ScanRow>) => void }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  if (scan.status !== "done") return null;
  const st = scan.report_status;
  const resend = async () => {
    setBusy(true);
    setErr(null);
    try {
      await adminApi.sendReport(scan.token);
      onSent({ report_status: "pending", report_error: null, emailed: false });
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="mt-2 pl-[98px] text-[14px]">
      <p className={`flex items-start gap-1.5 font-medium ${st === "sent" ? "ink-pass" : st === "failed" ? "ink-fail" : "text-2"}`}>
        {st === "sent" ? <MailCheck size={15} className="mt-[2px] shrink-0" aria-hidden="true" /> : st === "failed" ? <MailWarning size={15} className="mt-[2px] shrink-0" aria-hidden="true" /> : <Loader2 size={15} className="spin mt-[2px] shrink-0" aria-hidden="true" />}
        <span>{st === "sent" ? "Report emailed" : st === "failed" ? "Report not delivered yet" : "Report being sent"}</span>
      </p>
      {st === "failed" && scan.report_error ? <p className="text-2 mt-0.5 text-[13px] leading-snug">{scan.report_error}</p> : null}
      {st !== "pending" ? (
        <button type="button" className="link-btn mt-0.5 text-[14px]" onClick={resend} disabled={busy}>
          {busy ? <Loader2 size={15} className="spin" aria-hidden="true" /> : <Send size={15} aria-hidden="true" />}
          {st === "sent" ? "Send it again" : "Try sending again"}
        </button>
      ) : null}
      {err ? <ErrorText>{err}</ErrorText> : null}
    </div>
  );
}


/** Delete this lead with all its scans, after a confirmation. Any staff member can do this. */
function DeleteLead({ lead }: { lead: LeadDetail }) {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const who = lead.business_name || lead.name || lead.email;
  const remove = async () => {
    setBusy(true);
    setError(null);
    try {
      await adminApi.deleteLead(lead.id);
      navigate("/admin", { replace: true, state: { notice: `Deleted ${who}.` } });
    } catch (e) {
      setError((e as ApiError).message);
      setBusy(false);
    }
  };
  return (
    <>
      <button type="button" className="link-btn ink-fail mt-4 px-1 text-[14px]" onClick={() => setOpen(true)}>
        <Trash2 size={15} aria-hidden="true" /> Delete this lead
      </button>
      <Sheet open={open} title="Delete this lead?" onClose={() => !busy && setOpen(false)}>
        <p className="text-2 text-[16px] leading-snug">
          <span className="font-semibold" style={{ color: "var(--label)" }}>{who}</span> and{" "}
          {lead.scans.length === 1 ? "its scan" : `all ${lead.scans.length} of its scans`} will be deleted for good. Their results links stop
          working. This cannot be undone.
        </p>
        {error ? <ErrorText className="mt-3">{error}</ErrorText> : null}
        <div className="mt-5 grid gap-2.5 sm:grid-cols-2">
          <button type="button" className="btn-glass" onClick={() => setOpen(false)} disabled={busy}>
            Keep it
          </button>
          <button type="button" className="btn-danger" onClick={remove} disabled={busy} aria-busy={busy || undefined}>
            {busy ? <Loader2 size={19} className="spin" aria-hidden="true" /> : <Trash2 size={18} aria-hidden="true" />} Delete lead
          </button>
        </div>
      </Sheet>
    </>
  );
}

