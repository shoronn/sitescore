import { ArrowRight, Clock, Eye, FileText, Gauge, Globe, Loader2, Mail, MousePointerClick } from "lucide-react";
import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError, type Lead, type PublicConfig } from "../api";
import { AGENT_AREA, AGENT_SCORED, CATEGORIES, CHECKS } from "../checks";
import { ErrorText, useMediaQuery } from "../components/Form";
import Footer from "../components/Footer";
import Header from "../components/Header";
import ScoreRing from "../components/ScoreRing";
import { Reveal, Stagger, StaggerItem } from "../motion";

// The sign-in sheet (dialog and form) loads only when needed; typing an address prefetches it.
const loadSheet = () => {
  // Fetch the results page too, so it opens without a wait once the scan starts.
  void import("./ScanPage");
  return import("./SignInSheet");
};
const SignInSheet = lazy(loadSheet);

const STEPS = [
  { icon: MousePointerClick, title: "Enter your website", body: "Type your address. We only look at what anyone on the internet can already see." },
  { icon: Mail, title: "Add your email", body: "So we know where to send your PDF report. No password, nothing to confirm." },
  { icon: Gauge, title: "Get your scores", body: "Your AI agent readiness and website health scores appear in a minute or two. The PDF report follows by email." },
];

// The home ring shows every check: AI agent readiness first, then website health.
const ALL_CHECKS = [...AGENT_SCORED, ...CHECKS];

export default function Home() {
  const navigate = useNavigate();
  const [config, setConfig] = useState<PublicConfig | null>(null);
  const [lead, setLead] = useState<Lead | null>(null);
  const [url, setUrl] = useState("");
  const [urlError, setUrlError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [sheet, setSheet] = useState(false);
  const wide = useMediaQuery("(min-width: 1024px)");
  const input = useRef<HTMLInputElement>(null);
  // Once the sheet has been opened it stays mounted, so closing it can animate and keeps what was typed.
  const [sheetWanted, setSheetWanted] = useState(false);
  useEffect(() => {
    if (sheet) setSheetWanted(true);
  }, [sheet]);

  useEffect(() => {
    document.title = "SiteScore by MAKTECH: is your website AI agent ready?";
    api.config().then(setConfig).catch(() => setConfig(null));
    api.me().then((m) => setLead(m.lead)).catch(() => setLead(null));
  }, []);

  const start = useCallback(
    async (target: string) => {
      setStarting(true);
      setUrlError(null);
      try {
        const { token } = await api.startScan(target);
        navigate(`/scan/${token}`);
      } catch (e) {
        const err = e as ApiError;
        if (err.status === 401) {
          setLead(null);
          setSheet(true);
        } else {
          setUrlError(err.message);
        }
      } finally {
        setStarting(false);
      }
    },
    [navigate],
  );

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const value = url.trim();
    if (!value) {
      setUrlError("Enter your website address, for example yourbusiness.com");
      input.current?.focus();
      return;
    }
    if (lead) start(value);
    else setSheet(true);
  };

  /** The closing call to action brings the visitor back up to the address box. */
  const backToTop = () => {
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    window.scrollTo({ top: 0, behavior: reduce ? "auto" : "smooth" });
    window.setTimeout(() => input.current?.focus({ preventScroll: true }), reduce ? 0 : 450);
  };

  return (
    <>
      <Header
        right={
          lead ? (
            <button
              type="button"
              className="glass text-2 inline-flex min-h-[44px] min-w-0 max-w-[calc(100vw-250px)] items-center gap-1.5 rounded-capsule px-3.5 py-2 text-[13px] font-medium sm:max-w-[340px]"
              title={`Reports go to ${lead.email}. Click to change.`}
              aria-label={`Reports go to ${lead.email}. Change email`}
              onMouseEnter={() => void loadSheet()}
              onFocus={() => void loadSheet()}
              onClick={() => setSheet(true)}
            >
              <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: "var(--pass)" }} aria-hidden="true" />
              <span className="truncate">{lead.email}</span>
              <span className="ink-brand hidden shrink-0 font-semibold sm:inline">Change</span>
            </button>
          ) : null
        }
      />
      <main className="shell relative z-10 pb-6">
        {/* ------------------------------------------------------------ hero */}
        <section className="grid items-center gap-8 pt-7 lg:min-h-[min(640px,calc(100dvh-150px))] lg:grid-cols-[minmax(0,1fr)_minmax(0,500px)] lg:gap-10 lg:pt-6 xl:gap-16">
          <div>
            <p className="glass hero-in inline-flex items-center gap-2 rounded-capsule px-3.5 py-1.5 text-[13px] font-semibold" style={{ animationDelay: "40ms" }}>
              <span className="h-2 w-2 rounded-full" style={{ background: "var(--brand)" }} aria-hidden="true" />
              Free AI agent and website check
            </p>
            <h1 className="hero-in balance mt-4 font-display text-[40px] font-bold leading-[1.03] tracking-[-0.035em] sm:text-[56px] lg:text-[68px] xl:text-[76px]" style={{ animationDelay: "90ms" }}>
              Is your website AI Agent Ready?
            </h1>
            <p className="hero-in text-2 mt-4 max-w-[42ch] text-[18px] leading-[1.45] sm:text-[20px] lg:mt-5 lg:text-[21px]" style={{ animationDelay: "140ms" }}>
              See if ChatGPT, Claude and other AI agents can find, read and recommend your site, plus a full health check of its security, speed and email.
            </p>

            <div className="hero-in" style={{ animationDelay: "190ms" }}>
              <form onSubmit={onSubmit} className="glass search-pill mt-7 max-w-[620px] rounded-[30px] p-2 transition-shadow sm:flex sm:items-center sm:gap-2 lg:mt-9" noValidate>
                <label className="flex flex-1 cursor-text items-center gap-3 pl-3 pr-2">
                  <Globe size={20} className="text-3 shrink-0" aria-hidden="true" />
                  <span className="sr-only">Website address</span>
                  <input
                    ref={input}
                    value={url}
                    onChange={(e) => {
                      setUrl(e.target.value);
                      setUrlError(null);
                    }}
                    onFocus={() => void loadSheet()}
                    type="text"
                    inputMode="url"
                    enterKeyHint="go"
                    autoCapitalize="none"
                    autoCorrect="off"
                    autoComplete="url"
                    spellCheck={false}
                    placeholder="yourbusiness.com"
                    className="h-[52px] w-full min-w-0 bg-transparent text-[18px] outline-none placeholder:text-[var(--label-3)]"
                    aria-invalid={urlError ? true : undefined}
                    aria-describedby={urlError ? "url-error" : "url-hint"}
                  />
                </label>
                <button type="submit" className="btn-primary mt-2 w-full sm:mt-0 sm:w-auto" disabled={starting} aria-busy={starting || undefined}>
                  {starting ? <Loader2 className="spin" size={20} aria-hidden="true" /> : null}
                  {starting ? "Starting..." : "Check my site"}
                  {!starting ? <ArrowRight size={19} strokeWidth={2.4} aria-hidden="true" /> : null}
                </button>
              </form>
              {urlError ? (
                <ErrorText id="url-error" className="mt-3">{urlError}</ErrorText>
              ) : (
                <ul id="url-hint" className="text-2 mt-4 flex flex-wrap gap-x-5 gap-y-2 px-2 text-[14px] font-medium">
                  <li className="inline-flex items-center gap-1.5"><Clock size={16} className="ink-brand" aria-hidden="true" /> A minute or two</li>
                  <li className="inline-flex items-center gap-1.5"><Eye size={16} className="ink-brand" aria-hidden="true" /> Only public information</li>
                  <li className="inline-flex items-center gap-1.5"><FileText size={16} className="ink-brand" aria-hidden="true" /> PDF report by email</li>
                </ul>
              )}
            </div>
          </div>

          <div className="hero-ring order-first lg:order-none">
            <ScoreRing statuses={{}} size={wide ? 360 : 210} checks={ALL_CHECKS} />
          </div>
        </section>

        {/* ------------------------------------------------------------ what we check */}
        <section className="mt-14 lg:mt-10" aria-labelledby="what-we-check">
          <Reveal className="flex flex-col gap-1 lg:flex-row lg:items-end lg:justify-between lg:gap-8">
            <h2 id="what-we-check" className="font-display text-[26px] font-bold tracking-tight lg:text-[32px]">
              What we check
            </h2>
            <p className="text-2 max-w-[52ch] text-[15px] leading-snug lg:text-right lg:text-[16px]">
              {AGENT_SCORED.length} AI agent checks and {CHECKS.length} website health checks, each explained in plain language with what to do about it.
            </p>
          </Reveal>
          {/* AI agent readiness first, across the full width. Then, on wide screens, Security (the
              longest list) runs down the left and the other four health areas sit two by two. */}
          <Stagger as="ul" className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3 lg:gap-4">
            <StaggerItem as="li" className="glass relative overflow-hidden rounded-[26px] p-5 sm:col-span-2 lg:col-span-3 lg:p-7">
              <div
                className="pointer-events-none absolute -right-20 -top-24 h-72 w-72 rounded-full opacity-60 blur-3xl"
                style={{ background: "radial-gradient(circle, rgba(248,98,45,.30), transparent 70%)" }}
                aria-hidden="true"
              />
              <div className="relative grid gap-5 lg:grid-cols-[minmax(0,300px)_minmax(0,1fr)] lg:gap-10">
                <div>
                  <div className="flex items-center gap-3">
                    <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-[13px]" style={{ background: "var(--tint-brand)" }}>
                      <AGENT_AREA.icon size={22} className="ink-brand" aria-hidden="true" />
                    </span>
                    <span>
                      <span className="block text-[18px] font-semibold leading-tight">{AGENT_AREA.label}</span>
                      <span className="text-3 block text-[13px] font-medium">{AGENT_SCORED.length} checks, its own score out of 100</span>
                    </span>
                  </div>
                  <p className="text-2 mt-3 text-[15px] leading-snug lg:text-[16px]">
                    More people now ask AI assistants instead of searching. We check the open standards those assistants use to find and read websites.
                  </p>
                </div>
                <ul className="grid gap-x-6 gap-y-3 sm:grid-cols-2 xl:grid-cols-3">
                  {AGENT_SCORED.map((ch) => (
                    <li key={ch.key} className="flex gap-2.5">
                      <span className="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: "var(--brand)" }} aria-hidden="true" />
                      <span>
                        <span className="block text-[15px] font-semibold leading-snug">{ch.name}</span>
                        <span className="text-2 block text-[14px] leading-snug">{ch.blurb}</span>
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            </StaggerItem>
            {CATEGORIES.map((c) => {
              const checks = CHECKS.filter((ch) => ch.category === c.key);
              const big = c.key === "security";
              return (
                <StaggerItem as="li" key={c.key} className={`glass flex flex-col rounded-[26px] p-5 ${big ? "sm:col-span-2 lg:col-span-1 lg:row-span-2" : ""}`}>
                  <div className="flex items-center gap-3">
                    <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-[13px]" style={{ background: "var(--tint-brand)" }}>
                      <c.icon size={22} className="ink-brand" aria-hidden="true" />
                    </span>
                    <span>
                      <span className="block text-[18px] font-semibold leading-tight">{c.label}</span>
                      <span className="text-3 block text-[13px] font-medium">{checks.length} checks</span>
                    </span>
                  </div>
                  <p className="text-2 mt-3 text-[15px] leading-snug lg:hidden">{c.blurb}</p>
                  <ul className={`mt-4 hidden gap-y-2.5 lg:grid ${big ? "lg:mt-5 lg:gap-y-3" : ""}`}>
                    {checks.map((ch) => (
                      <li key={ch.key} className="text-2 flex items-center gap-2.5 text-[15px]">
                        <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: "var(--brand)" }} aria-hidden="true" />
                        {ch.name}
                      </li>
                    ))}
                  </ul>
                </StaggerItem>
              );
            })}
          </Stagger>
        </section>

        {/* ------------------------------------------------------------ how it works */}
        <section className="mt-14 lg:mt-20" aria-labelledby="how-it-works">
          <Reveal>
            <h2 id="how-it-works" className="font-display text-[26px] font-bold tracking-tight lg:text-[32px]">
              How it works
            </h2>
          </Reveal>
          <Stagger as="ul" className="mt-5 grid gap-3 md:grid-cols-3 lg:gap-4">
            {STEPS.map((st, i) => (
              <StaggerItem as="li" key={st.title} className="glass relative flex gap-4 rounded-[26px] p-5 md:flex-col md:gap-0 lg:p-6">
                <span className="relative flex h-11 w-11 shrink-0 items-center justify-center rounded-[13px]" style={{ background: "var(--tint-brand)" }}>
                  <st.icon size={21} className="ink-brand" aria-hidden="true" />
                </span>
                <span className="md:mt-4">
                  <span className="text-3 block text-[13px] font-semibold uppercase tracking-[0.06em]">Step {i + 1}</span>
                  <span className="mt-0.5 block text-[18px] font-semibold leading-snug">{st.title}</span>
                  <span className="text-2 mt-1 block text-[15px] leading-snug">{st.body}</span>
                </span>
              </StaggerItem>
            ))}
          </Stagger>
        </section>

        {/* ------------------------------------------------------------ closing call to action */}
        <Reveal as="section" className="glass relative mt-14 overflow-hidden rounded-[30px] p-6 sm:p-8 lg:mt-20 lg:flex lg:items-center lg:justify-between lg:gap-10 lg:p-10">
          <div
            className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full opacity-70 blur-3xl"
            style={{ background: "radial-gradient(circle, rgba(248,98,45,.32), transparent 70%)" }}
            aria-hidden="true"
          />
          <div className="relative">
            <h2 className="balance font-display text-[26px] font-bold leading-tight tracking-tight lg:text-[32px]">See how ready your website is</h2>
            <p className="text-2 mt-2 max-w-[56ch] text-[15px] leading-snug lg:text-[16px]">
              Free and done in a minute or two. Made by MAKTECH, the team that builds and hosts websites and apps for businesses across Bangladesh.
            </p>
          </div>
          <button type="button" className="btn-primary relative mt-5 w-full shrink-0 sm:w-auto lg:mt-0" onClick={backToTop}>
            Check my site <ArrowRight size={19} strokeWidth={2.4} aria-hidden="true" />
          </button>
        </Reveal>
      </main>
      <Footer />

      <Suspense fallback={null}>
      {sheet || sheetWanted ? (
      <SignInSheet
        open={sheet}
        onClose={() => setSheet(false)}
        config={config}
        initialEmail={lead?.email}
        submitLabel={url.trim() ? "Start my free scan" : "Save email"}
        onSignedIn={(l) => {
          setLead(l);
          setSheet(false);
          if (url.trim()) start(url.trim());
        }}
      />
      ) : null}
      </Suspense>
    </>
  );
}


