import { AlertTriangle, Check, ChevronDown, Download, Link2Off, Loader2, MailCheck, MessageCircle, Minus, Phone, PhoneCall, RotateCcw, SearchX, Share2 } from "lucide-react";
import { AnimatePresence, m } from "motion/react";
import { useCallback, useEffect, useId, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, ApiError, type CheckResult, type PublicConfig, type Scan, type Status } from "../api";
import { AGENT_AREA, AGENT_CHECKS, ALL_CHECK_KEYS, CATEGORIES, CHECKS } from "../checks";
import { DEFAULT_PRICES, formatPrice, useCurrency, type Currency } from "../currency";
import AgentReadiness from "../components/AgentReadiness";
import Footer from "../components/Footer";
import { ErrorText } from "../components/Form";
import Header from "../components/Header";
import ScoreRing from "../components/ScoreRing";
import StatusIcon from "../components/StatusIcon";
import { EASE_OUT, Reveal } from "../motion";

const POLL_MS = 1200;
const STATUS_RANK: Record<Status, number> = { fail: 0, warn: 1, not_checked: 3, pass: 2 };

export default function ScanPage() {
  const { token = "" } = useParams();
  const [scan, setScan] = useState<Scan | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [config, setConfig] = useState<PublicConfig | null>(null);

  useEffect(() => {
    api.config().then(setConfig).catch(() => undefined);
  }, []);

  useEffect(() => {
    let stop = false;
    let timer: ReturnType<typeof setTimeout>;
    const startedAt = Date.now();
    const tick = async () => {
      try {
        const s = await api.scan(token);
        if (stop) return;
        setScan(s);
        if (s.status === "queued" || s.status === "running") timer = setTimeout(tick, POLL_MS);
        // After the scan, keep checking for a short while until the report email has gone out.
        else if (s.status === "done" && s.is_owner && s.report_status === "pending" && Date.now() - startedAt < 4 * 60_000)
          timer = setTimeout(tick, 3000);
      } catch (e) {
        if (stop) return;
        const err = e as ApiError;
        if (err.status === 0) timer = setTimeout(tick, POLL_MS * 3);
        else setError(err);
      }
    };
    tick();
    return () => {
      stop = true;
      clearTimeout(timer);
    };
  }, [token]);

  if (error) {
    const expired = error.status === 410;
    return (
      <Shell>
        <Notice
          icon={expired ? Link2Off : SearchX}
          title={expired ? "This link has expired" : "Scan not found"}
          body={expired ? error.message : "This results link doesn't match any scan. Check that it was copied in full, or run a new scan."}
          action={<Link to="/" className="btn-primary mt-6 w-full">Scan a website</Link>}
        />
      </Shell>
    );
  }
  if (!scan) {
    return (
      <Shell>
        <div className="mt-24 flex flex-col items-center gap-3" role="status">
          <Loader2 className="spin text-3" size={30} aria-hidden="true" />
          <span className="text-2 text-[15px]">Loading results</span>
        </div>
      </Shell>
    );
  }
  return <ScanView scan={scan} config={config} />;
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <>
      <Header />
      <main className="shell relative z-10 pb-6">{children}</main>
      <Footer />
    </>
  );
}

function Notice({ icon: Icon, title, body, action, tone = "neutral" }: { icon: typeof SearchX; title: string; body?: string; action?: React.ReactNode; tone?: "neutral" | "fail" }) {
  return (
    <div className="glass rise-enter mx-auto mt-10 max-w-md rounded-glass p-6 text-center sm:p-8">
      <span
        className="mx-auto flex h-14 w-14 items-center justify-center rounded-full"
        style={{ background: tone === "fail" ? "var(--tint-fail)" : "var(--tint-brand)" }}
        aria-hidden="true"
      >
        <Icon size={26} className={tone === "fail" ? "ink-fail" : "ink-brand"} />
      </span>
      <h1 className="balance mt-4 font-display text-[24px] font-bold leading-tight tracking-tight">{title}</h1>
      {body ? <p className="text-2 mt-2 text-[16px] leading-snug">{body}</p> : null}
      {action}
    </div>
  );
}

function ScanView({ scan, config }: { scan: Scan; config: PublicConfig | null }) {
  useEffect(() => {
    const agentPart = scan.agent.score !== null ? `AI agent ready ${scan.agent.score}/100, ` : "";
    document.title =
      scan.status === "done"
        ? `${scan.host}: ${agentPart}health ${scan.score ?? "--"}/100 | SiteScore`
        : `Checking ${scan.host} | SiteScore`;
  }, [scan.status, scan.score, scan.agent.score, scan.host]);
  const running = scan.status === "queued" || scan.status === "running";
  const done = scan.status === "done";
  const byKey = useMemo(() => Object.fromEntries(scan.results.map((r) => [r.key, r])), [scan.results]);
  const statuses = useMemo(
    () => Object.fromEntries(scan.results.map((r) => [r.key, r.status])) as Record<string, Status>,
    [scan.results],
  );

  // "Fix these first", the verdict and the offer are about website health; AI agent
  // readiness has its own card with its own score.
  // Only today's health checks: older scans may also hold results of checks since removed.
  const health = scan.results.filter((r) => HEALTH_KEYS.has(r.key));
  // Scans from before AI agent readiness existed have no agent results: leave that part out.
  const hasAgent = scan.results.some((r) => r.category === "agent");
  const fails = health.filter((r) => r.status === "fail");
  const warns = health.filter((r) => r.status === "warn");
  const topIssues = [...fails, ...warns]
    .sort((a, b) => Number(b.critical) - Number(a.critical) || STATUS_RANK[a.status] - STATUS_RANK[b.status] || b.weight - a.weight)
    .slice(0, 5);

  if (scan.status === "failed") {
    return (
      <Shell>
        <Notice
          icon={AlertTriangle}
          tone="fail"
          title={`We couldn't scan ${scan.host}`}
          body={scan.error?.message}
          action={<Link to="/" className="btn-primary mt-6 w-full">Try another address</Link>}
        />
      </Shell>
    );
  }

  return (
    <Shell>
      {/* The site, with the actions on wide screens */}
      <div className="flex flex-col items-center gap-4 pt-6 text-center lg:flex-row lg:items-end lg:justify-between lg:pt-10 lg:text-left">
        <div className="min-w-0">
          <p className="text-2 text-[15px] font-medium">{running ? "Checking" : "Results for"}</p>
          <h1 className="mt-0.5 break-all font-display text-[26px] font-bold leading-tight tracking-tight lg:text-[34px]">{scan.host}</h1>
        </div>
        {done ? (
          <div className="hidden shrink-0 gap-3 lg:flex">
            <ResultActions scan={scan} />
          </div>
        ) : null}
      </div>

      {done && hasAgent ? (
        <div className="mt-6 lg:mt-7">
          <AgentReadiness scan={scan} byKey={byKey} />
        </div>
      ) : null}

      <div className="mt-7 grid gap-7 lg:mt-8 lg:grid-cols-[minmax(0,380px)_minmax(0,1fr)] lg:gap-10 xl:grid-cols-[minmax(0,400px)_minmax(0,1fr)] xl:gap-14">
        {/* Left: the health ring and the call to action */}
        <div className="lg:sticky lg:top-6 lg:self-start">
          {done ? (
            <h2 className="text-2 text-center text-[13px] font-semibold uppercase tracking-[0.06em]">Website health</h2>
          ) : null}
          <div className={done ? "mt-4" : ""}>
            <ScoreRing
              statuses={statuses}
              running={running}
              score={done ? scan.score : undefined}
              band={scan.band}
              caption={done ? scan.band_label ?? undefined : undefined}
            />
          </div>
          {done ? (
            <Verdict scan={scan} fails={fails.length} warns={warns.length} />
          ) : (
            <PhaseLine scan={scan} />
          )}
          {done ? (
            <div className="hidden lg:block">
              <OfferCard scan={scan} issues={fails.length + warns.length} config={config} />
            </div>
          ) : null}
        </div>

        {/* Right: progress while checking; priorities and all checks when done */}
        <div className="min-w-0 space-y-7">
          {running ? <ScanProgress scan={scan} /> : null}

          {done && topIssues.length ? (
            <section aria-labelledby="fix-first" className="rise-enter">
              <SectionTitle id="fix-first">Health: fix these first</SectionTitle>
              <ul className="glass mt-3 overflow-hidden rounded-glass">
                {topIssues.map((r, i) => (
                  <ResultRow key={r.key} result={r} first={i === 0} />
                ))}
              </ul>
            </section>
          ) : null}

          {done ? (
            <div className="lg:hidden">
              <OfferCard scan={scan} issues={fails.length + warns.length} config={config} />
            </div>
          ) : null}

          {done ? (
            <Reveal>
              <CategoryTiles scan={scan} />
            </Reveal>
          ) : null}

          {done ? (
          <section aria-labelledby="all-checks" className="rise-enter">
            <SectionTitle id="all-checks">Every check</SectionTitle>
            {/* Two flowing columns on wide screens, so the long Security list does not leave gaps. */}
            <div className="mt-3 gap-5 xl:columns-2">
              {hasAgent ? (
              <div className="mb-5 break-inside-avoid">
                <h3 className="text-2 mb-2 flex items-center gap-1.5 px-1 text-[13px] font-semibold uppercase tracking-[0.06em]">
                  <AGENT_AREA.icon size={14} aria-hidden="true" /> {AGENT_AREA.label}
                </h3>
                <ul className="glass overflow-hidden rounded-glass">
                  {AGENT_CHECKS.map((ch, i) => (
                    <ResultRow key={ch.key} result={byKey[ch.key]} pendingName={ch.name} first={i === 0} optional={ch.optional} />
                  ))}
                </ul>
              </div>
              ) : null}
              {CATEGORIES.map((c) => (
                <div key={c.key} className="mb-5 break-inside-avoid">
                  <h3 className="text-2 mb-2 flex items-center gap-1.5 px-1 text-[13px] font-semibold uppercase tracking-[0.06em]">
                    <c.icon size={14} aria-hidden="true" /> {c.label}
                  </h3>
                  <ul className="glass overflow-hidden rounded-glass">
                    {CHECKS.filter((ch) => ch.category === c.key).map((ch, i) => (
                      <ResultRow key={ch.key} result={byKey[ch.key]} pendingName={ch.name} first={i === 0} />
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </section>
          ) : null}

          {done ? (
            <div className="grid gap-2.5 sm:flex sm:flex-wrap sm:gap-3 lg:hidden">
              <ResultActions scan={scan} />
            </div>
          ) : null}
        </div>
      </div>
    </Shell>
  );
}

function ResultActions({ scan }: { scan: Scan }) {
  return (
    <>
      <a href={api.reportUrl(scan.token)} className="btn-glass" download>
        <Download size={18} aria-hidden="true" /> Download PDF
      </a>
      <ShareButton host={scan.host} />
      <Link to="/" className="btn-glass">
        <RotateCcw size={18} aria-hidden="true" /> Scan another site
      </Link>
    </>
  );
}

const SPEED_KEYS = new Set(CHECKS.filter((c) => c.category === "performance").map((c) => c.key));
const HEALTH_KEYS = new Set(CHECKS.map((c) => c.key));

/** Checks that count as finished for the progress display. */
function settledKeys(scan: Scan): Set<string> {
  return new Set(scan.results.map((r) => r.key));
}

/** One plain sentence about what is happening now, read out to screen readers as it changes. */
function PhaseLine({ scan }: { scan: Scan }) {
  const doneKeys = settledKeys(scan);
  const left = ALL_CHECK_KEYS.filter((k) => !doneKeys.has(k));
  const onlySpeed = left.length > 0 && left.every((k) => SPEED_KEYS.has(k));
  const text =
    scan.status === "queued"
      ? "Starting your scan..."
      : onlySpeed
        ? "Almost done. We're loading your site in a real phone browser to test its speed, which can take a minute or two."
        : "Checking your site. Your results appear here as soon as every check is done.";
  return (
    <p className="text-2 mx-auto mt-5 max-w-[32ch] text-center text-[15px] leading-snug" aria-live="polite">
      {text}
    </p>
  );
}

function useElapsed(since: string): string {
  const start = useMemo(() => Math.min(Date.parse(since) || Date.now(), Date.now()), [since]);
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  const secs = Math.max(0, Math.floor((now - start) / 1000));
  return `${Math.floor(secs / 60)}:${String(secs % 60).padStart(2, "0")}`;
}

/** Shown while the scan runs: overall progress and where each area is up to. No findings yet. */
function ScanProgress({ scan }: { scan: Scan }) {
  const doneKeys = settledKeys(scan);
  const total = ALL_CHECK_KEYS.length;
  const finished = ALL_CHECK_KEYS.filter((k) => doneKeys.has(k)).length;
  const pct = Math.round((finished / total) * 100);
  const elapsed = useElapsed(scan.created_at);
  const queued = scan.status === "queued";
  return (
    <section className="glass rise-enter rounded-glass p-5 sm:p-6" aria-labelledby="progress-title">
      <div className="flex items-baseline justify-between gap-4">
        <h2 id="progress-title" className="font-display text-[20px] font-bold tracking-tight">
          {queued ? "Getting ready" : "Scanning"}
        </h2>
        <span className="text-2 tabular text-[14px] font-medium" aria-label={`Time so far ${elapsed}`}>{elapsed}</span>
      </div>
      <div
        className="mt-3 h-2 overflow-hidden rounded-full"
        style={{ background: "var(--track)" }}
        role="progressbar"
        aria-label="Scan progress"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <m.div
          className="h-full rounded-full"
          style={{ background: "linear-gradient(90deg, var(--brand-deep), var(--brand))" }}
          initial={false}
          animate={{ width: `${Math.max(pct, queued ? 2 : 6)}%` }}
          transition={{ duration: 0.6, ease: EASE_OUT }}
        />
      </div>
      <p className="text-2 tabular mt-2 text-[14px]">{finished} of {total} checks done</p>

      <ul className="mt-4 space-y-1">
        {[{ key: "agent", label: AGENT_AREA.label, icon: AGENT_AREA.icon }, ...CATEGORIES].map((c) => {
          const checks = c.key === "agent" ? AGENT_CHECKS : CHECKS.filter((ch) => ch.category === c.key);
          const n = checks.filter((ch) => doneKeys.has(ch.key)).length;
          const state = queued ? "waiting" : n === checks.length ? "done" : "running";
          const speed = c.key === "performance";
          return (
            <li key={c.key} className="flex items-center gap-3 rounded-2xl py-2.5">
              <span
                className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px]"
                style={{ background: state === "done" ? "var(--tint-pass)" : "var(--tint-brand)" }}
              >
                <c.icon size={19} className={state === "done" ? "ink-pass" : "ink-brand"} aria-hidden="true" />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-[16px] font-semibold leading-tight">{c.label}</span>
                <span className="text-2 block text-[14px] leading-snug">
                  {state === "done"
                    ? "Done"
                    : state === "waiting"
                      ? "Waiting to start"
                      : speed
                        ? "Speed test in a real phone browser, can take a minute or two"
                        : `${n} of ${checks.length} checked`}
                </span>
              </span>
              <span className="flex h-7 w-7 shrink-0 items-center justify-center" aria-hidden="true">
                {state === "done" ? (
                  <m.span initial={{ scale: 0.4, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={{ type: "spring", stiffness: 500, damping: 24 }}>
                    <Check size={20} strokeWidth={2.8} className="ink-pass" />
                  </m.span>
                ) : state === "running" ? (
                  <Loader2 size={19} className="spin text-3" />
                ) : (
                  <span className="h-2 w-2 rounded-full" style={{ background: "var(--neutral)" }} />
                )}
              </span>
            </li>
          );
        })}
      </ul>
      <p className="text-3 mt-3 text-[13px] leading-snug">
        You can keep this page open. Scans usually take a minute or two, and we email the PDF report when it is done.
      </p>
    </section>
  );
}

function SectionTitle({ id, children }: { id: string; children: React.ReactNode }) {
  return (
    <h2 id={id} className="px-1 font-display text-[22px] font-bold tracking-tight">
      {children}
    </h2>
  );
}

function Verdict({ scan, fails, warns }: { scan: Scan; fails: number; warns: number }) {
  const parts: string[] = [];
  if (fails) parts.push(`${fails} ${fails === 1 ? "problem needs" : "problems need"} fixing`);
  if (warns) parts.push(`${warns} ${warns === 1 ? "thing" : "things"} could be better`);
  const sentence = parts.length ? `${parts.join(" and ")}.` : "Everything we checked looks good.";
  return (
    <div className="mx-auto mt-5 max-w-[34ch] text-center">
      <p className="balance text-[17px] font-semibold leading-snug">{sentence}</p>
      {scan.capped ? <p className="text-2 mt-1.5 text-[14px] leading-snug">Score held below 50 because of a serious problem.</p> : null}
      {scan.coverage !== null && scan.coverage < 70 ? (
        <p className="text-2 mt-1.5 text-[14px] leading-snug">We could check {scan.coverage} of 100 points. The score covers only those.</p>
      ) : null}
    </div>
  );
}

function ResultRow({ result, pendingName, first, optional }: { result?: CheckResult; pendingName?: string; first?: boolean; optional?: boolean }) {
  const [open, setOpen] = useState(false);
  const border = first ? "" : "border-t hairline";
  if (!result) {
    return (
      <li className={`flex min-h-[60px] items-center gap-3 px-4 ${border}`}>
        <StatusIcon />
        <span className="text-2 text-[16px]">{pendingName}</span>
      </li>
    );
  }
  const expandable = Boolean(result.why || (result.fix && result.status !== "pass"));
  const panelId = `detail-${result.key}`;
  const content = (
    <>
      <m.span
        key={result.status}
        className="pt-0.5"
        initial={{ scale: 0.5, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ type: "spring", stiffness: 520, damping: 26 }}
      >
        {/* Optional checks never show red: they are information, not a problem. */}
        <StatusIcon status={optional && result.status !== "pass" ? "not_checked" : result.status} />
      </m.span>
      <span className="min-w-0 flex-1">
        <span className="block text-[16px] font-semibold leading-snug">
          {result.title}
          {optional ? (
            <span className="text-2 ml-2 inline-block rounded-capsule px-2 py-0.5 align-[2px] text-[11px] font-semibold uppercase tracking-[0.04em]" style={{ background: "var(--field-fill)" }}>
              Not scored
            </span>
          ) : null}
        </span>
        <span className="text-2 mt-0.5 block text-[15px] leading-snug">{result.summary}</span>
      </span>
      {expandable ? (
        <ChevronDown
          size={20}
          className="text-3 mt-0.5 shrink-0 transition-transform duration-200"
          style={{ transform: open ? "rotate(180deg)" : "none" }}
          aria-hidden="true"
        />
      ) : null}
    </>
  );
  return (
    <li className={`${border} rise-enter`}>
      {expandable ? (
        <button
          className="row-btn flex w-full items-start gap-3 px-4 py-3.5 text-left"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          aria-controls={panelId}
        >
          {content}
        </button>
      ) : (
        <div className="flex w-full items-start gap-3 px-4 py-3.5">{content}</div>
      )}
      <AnimatePresence initial={false}>
      {open && expandable ? (
        <m.div
          id={panelId}
          key="detail"
          className="overflow-hidden"
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: "auto", opacity: 1 }}
          exit={{ height: 0, opacity: 0 }}
          transition={{ duration: 0.3, ease: EASE_OUT }}
        >
        <div className="space-y-3 px-4 pb-4 pl-[54px] text-[15px] leading-snug">
          {result.why ? (
            <div>
              <p className="text-3 text-[12px] font-semibold uppercase tracking-[0.06em]">Why it matters</p>
              <p className="text-2 mt-1">{result.why}</p>
            </div>
          ) : null}
          {result.fix && result.status !== "pass" ? (
            <div>
              <p className="text-3 text-[12px] font-semibold uppercase tracking-[0.06em]">How MAKTECH fixes it</p>
              <p className="text-2 mt-1">{result.fix}</p>
            </div>
          ) : null}
        </div>
        </m.div>
      ) : null}
      </AnimatePresence>
    </li>
  );
}

function CategoryTiles({ scan }: { scan: Scan }) {
  return (
    <section aria-labelledby="by-category">
      <SectionTitle id="by-category">Health by area</SectionTitle>
      <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5 [&>*:last-child]:col-span-2 sm:[&>*:last-child]:col-span-1">
        {CATEGORIES.map((c) => {
          const cat = scan.categories.find((x) => x.key === c.key);
          const score = cat?.score ?? null;
          const tone = score === null ? null : score >= 80 ? "pass" : score >= 50 ? "warn" : "fail";
          return (
            <div key={c.key} className="glass rounded-[24px] p-4">
              <div className="flex items-center gap-2">
                <span className="flex h-7 w-7 items-center justify-center rounded-[9px]" style={{ background: "var(--tint-brand)" }}>
                  <c.icon size={16} className="ink-brand" aria-hidden="true" />
                </span>
                <span className="text-[15px] font-semibold">{c.label}</span>
              </div>
              {tone ? (
                <>
                  <div className="tabular mt-3 font-display text-[32px] font-bold leading-none tracking-tight" style={{ color: `var(--${tone}-ink)` }}>
                    {score}
                    <span className="text-3 ml-0.5 text-[15px] font-semibold tracking-normal">/100</span>
                  </div>
                  <div
                    className="mt-3 h-1.5 overflow-hidden rounded-full"
                    style={{ background: "var(--track)" }}
                    role="progressbar"
                    aria-label={`${c.label} score`}
                    aria-valuenow={score ?? 0}
                    aria-valuemin={0}
                    aria-valuemax={100}
                  >
                    <m.div
                      className="h-full rounded-full"
                      style={{ background: `var(--${tone})` }}
                      initial={{ width: 0 }}
                      whileInView={{ width: `${Math.max(score ?? 0, 3)}%` }}
                      viewport={{ once: true }}
                      transition={{ duration: 0.9, ease: EASE_OUT, delay: 0.1 }}
                    />
                  </div>
                </>
              ) : (
                <>
                  <div className="text-3 mt-3 flex h-8 items-center gap-1.5 text-[15px] font-semibold">
                    <Minus size={16} aria-hidden="true" /> Not checked
                  </div>
                  <div className="mt-3 h-1.5 rounded-full" style={{ background: "var(--track)" }} aria-hidden="true" />
                </>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}

function OfferCard({ scan, issues, config }: { scan: Scan; issues: number; config: PublicConfig | null }) {
  const [requested, setRequested] = useState(scan.callback_requested);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const link = typeof window !== "undefined" ? window.location.href : "";
  const phone = config?.contact_phone ?? null;
  const wa = config?.whatsapp_number
    ? `https://wa.me/${config.whatsapp_number}?text=${encodeURIComponent(
        `Hi MAKTECH, I checked ${scan.host} on SiteScore (AI agent readiness ${scan.agent.score ?? "--"}/100, health ${scan.score ?? "--"}/100) and would like help fixing it. ${link}`,
      )}`
    : null;

  const callMe = useCallback(async () => {
    setBusy(true);
    setErr(null);
    try {
      await api.requestCallback(scan.token);
      setRequested(true);
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  }, [scan.token]);

  const agentReady = (scan.agent.score ?? 100) >= 100;
  const healthy = issues === 0 && agentReady;
  return (
    <section className="glass relative overflow-hidden rounded-glass p-5 lg:mt-7" aria-labelledby="offer-title">
      <div
        className="pointer-events-none absolute -right-16 -top-16 h-48 w-48 rounded-full opacity-60 blur-2xl"
        style={{ background: "radial-gradient(circle, rgba(248,98,45,.35), transparent 70%)" }}
        aria-hidden="true"
      />
      <h2 id="offer-title" className="relative font-display text-[21px] font-bold leading-snug tracking-tight">
        {healthy ? "Keep it this way" : "Want us to fix these?"}
      </h2>
      {healthy ? (
        <p className="text-2 relative mt-1.5 text-[15px] leading-snug">
          CloudCare by MAKTECH monitors your site around the clock, patches it every month and keeps daily off-site backups.
        </p>
      ) : (
        <>
          <p className="text-2 relative mt-1.5 text-[15px] leading-snug">
            With the Fix-It Starter Pack, our engineers make your site ready for AI agents, fix your top 5 health issues, move your site to a MAKTECH server and give you the first month of CloudCare hosting free.
          </p>
          <Price config={config} />
        </>
      )}
      <div className="relative mt-4 space-y-2.5">
        {scan.is_owner ? (
          requested ? (
            <p className="flex items-center gap-2.5 rounded-2xl px-4 py-3 text-[15px] font-semibold" style={{ background: "var(--tint-pass)" }} role="status">
              <Check size={18} strokeWidth={2.6} className="ink-pass shrink-0" aria-hidden="true" /> Thanks. Our team will call you soon.
            </p>
          ) : (
            <button className="btn-primary w-full" onClick={callMe} disabled={busy} aria-busy={busy || undefined}>
              {busy ? <Loader2 size={20} className="spin" aria-hidden="true" /> : <Phone size={18} aria-hidden="true" />}
              Request a call
            </button>
          )
        ) : null}
        {phone || wa ? (
          <div className={`grid gap-2.5 ${phone && wa ? "grid-cols-2" : ""}`}>
            {phone ? (
              <a href={`tel:+${phone}`} className="btn-glass w-full px-3" aria-label={`Call MAKTECH on ${prettyPhone(phone)}`}>
                <PhoneCall size={18} className="ink-brand" aria-hidden="true" /> Call us
              </a>
            ) : null}
            {wa ? (
              <a href={wa} target="_blank" rel="noreferrer" className="btn-glass w-full px-3">
                <MessageCircle size={18} className="ink-pass" aria-hidden="true" /> WhatsApp
              </a>
            ) : null}
          </div>
        ) : null}
        {phone ? <p className="text-2 tabular text-center text-[13px] font-medium">{prettyPhone(phone)}</p> : null}
        {err ? <ErrorText>{err}</ErrorText> : null}
      </div>
      {scan.owner_email ? <ReportNote scan={scan} /> : null}
    </section>
  );
}

/** 8801897669234 -> +880 1897 669234 (Bangladesh mobiles); other numbers -> +digits. */
function prettyPhone(digits: string): string {
  const d = digits.replace(/\D/g, "");
  return d.startsWith("880") && d.length === 13 ? `+880 ${d.slice(3, 7)} ${d.slice(7)}` : `+${d}`;
}

/** The offer price, with a USD / BDT switch. The choice is remembered on this device. */
function Price({ config }: { config: PublicConfig | null }) {
  const [currency, setCurrency] = useCurrency();
  const prices = config?.prices ?? DEFAULT_PRICES;
  const id = useId();
  const options: { value: Currency; label: string }[] = [
    { value: "usd", label: "USD" },
    { value: "bdt", label: "BDT" },
  ];
  const onKey = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (!["ArrowLeft", "ArrowRight"].includes(e.key)) return;
    e.preventDefault();
    const next: Currency = currency === "usd" ? "bdt" : "usd";
    setCurrency(next);
    e.currentTarget.querySelector<HTMLButtonElement>(`[data-value="${next}"]`)?.focus();
  };
  return (
    <div className="relative mt-4 flex items-center justify-between gap-3">
      <p className="min-w-0" aria-live="polite">
        <span className="ink-brand tabular block whitespace-nowrap font-display text-[30px] font-bold leading-none tracking-tight">
          {formatPrice(prices[currency], currency)}
        </span>
        <span className="text-2 mt-1 block text-[13px] font-medium">one time</span>
      </p>
      <div role="radiogroup" aria-label="Currency" className="segmented shrink-0" onKeyDown={onKey}>
        {options.map((o) => {
          const on = currency === o.value;
          return (
            <button
              key={o.value}
              type="button"
              role="radio"
              aria-checked={on}
              tabIndex={on ? 0 : -1}
              data-value={o.value}
              className="segmented-item relative min-w-[52px] justify-center font-semibold"
              onClick={() => setCurrency(o.value)}
            >
              {on ? <m.span layoutId={`currency-${id}`} className="segmented-thumb absolute inset-0 rounded-capsule" transition={{ type: "spring", stiffness: 500, damping: 38 }} /> : null}
              <span className="relative">{o.label}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

/** Where the PDF report is: being sent, sent, or delayed (with the download as a fallback). */
function ReportNote({ scan }: { scan: Scan }) {
  const st = scan.report_status;
  const Icon = st === "sent" ? MailCheck : st === "failed" ? AlertTriangle : Loader2;
  const email = <span className="font-semibold [overflow-wrap:anywhere]" style={{ color: "var(--label)" }}>{scan.owner_email}</span>;
  return (
    <p className="text-2 relative mt-3.5 flex gap-2 text-[13px] leading-snug" role="status" aria-live="polite">
      <Icon
        size={15}
        className={`mt-[1px] shrink-0 ${st === "sent" ? "ink-pass" : st === "failed" ? "ink-warn" : "spin text-3"}`}
        aria-hidden="true"
      />
      <span>
        {st === "sent" ? (
          <>We've emailed the full PDF report to {email}.</>
        ) : st === "failed" ? (
          <>We're having trouble emailing your report to {email}. We'll keep trying, and you can download it below.</>
        ) : (
          <>Sending the full PDF report to {email}...</>
        )}
      </span>
    </p>
  );
}

function ShareButton({ host }: { host: string }) {
  const [copied, setCopied] = useState(false);
  const share = async () => {
    const url = window.location.href;
    if (navigator.share) {
      try {
        await navigator.share({ title: `SiteScore for ${host}`, url });
        return;
      } catch (e) {
        if ((e as DOMException)?.name === "AbortError") return; // the visitor closed the share sheet
      }
    }
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      window.prompt("Copy this link:", url);
    }
  };
  return (
    <button className="btn-glass" onClick={share}>
      {copied ? <Check size={18} className="ink-pass" aria-hidden="true" /> : <Share2 size={18} aria-hidden="true" />}
      <span aria-live="polite">{copied ? "Link copied" : "Share results"}</span>
    </button>
  );
}
