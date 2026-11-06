import { ArrowRight, Clock, Eye, FileText, Gauge, Globe, Loader2, Mail, MousePointerClick } from "lucide-react";
import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError, type Lead, type PublicConfig } from "../api";
import { AGENT_AREA, AGENT_SCORED, areaBlurb, areaName, CATEGORIES, CHECKS, checkBlurb, checkName } from "../checks";
import { ErrorText } from "../components/Form";
import Footer from "../components/Footer";
import Header from "../components/Header";
import ScoreRing from "../components/ScoreRing";
import { useT } from "../i18n";
import { Reveal, Stagger, StaggerItem } from "../motion";

// The sign-in sheet (dialog and form) loads only when needed; typing an address prefetches it.
const loadSheet = () => {
  // Fetch the results page too, so it opens without a wait once the scan starts.
  void import("./ScanPage");
  return import("./SignInSheet");
};
const SignInSheet = lazy(loadSheet);

const STEPS = [
  { icon: MousePointerClick, title: "home.step1", body: "home.step1_text" },
  { icon: Mail, title: "home.step2", body: "home.step2_text" },
  { icon: Gauge, title: "home.step3", body: "home.step3_text" },
] as const;

// The home ring shows every check: AI agent readiness first, then website health.
const ALL_CHECKS = [...AGENT_SCORED, ...CHECKS];

export default function Home() {
  const navigate = useNavigate();
  const { t, lang } = useT();
  const [config, setConfig] = useState<PublicConfig | null>(null);
  const [lead, setLead] = useState<Lead | null>(null);
  const [url, setUrl] = useState("");
  const [urlError, setUrlError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [sheet, setSheet] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  // Once the sheet has been opened it stays mounted, so closing it can animate and keeps what was typed.
  const [sheetWanted, setSheetWanted] = useState(false);
  useEffect(() => {
    if (sheet) setSheetWanted(true);
  }, [sheet]);

  useEffect(() => {
    api.config().then(setConfig).catch(() => setConfig(null));
    api.me().then((m) => setLead(m.lead)).catch(() => setLead(null));
  }, []);
  useEffect(() => {
    document.title = t("home.title");
  }, [t]);

  const start = useCallback(
    async (target: string) => {
      setStarting(true);
      setUrlError(null);
      try {
        const { token } = await api.startScan(target, lang);
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
    [navigate, lang],
  );

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const value = url.trim();
    if (!value) {
      setUrlError(t("home.empty"));
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
              title={t("home.reports_to", { email: lead.email })}
              aria-label={t("home.reports_to_label", { email: lead.email })}
              onMouseEnter={() => void loadSheet()}
              onFocus={() => void loadSheet()}
              onClick={() => setSheet(true)}
            >
              <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: "var(--pass)" }} aria-hidden="true" />
              <span className="truncate">{lead.email}</span>
              <span className="ink-brand hidden shrink-0 font-semibold sm:inline">{t("home.change")}</span>
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
              {t("home.pill")}
            </p>
            <h1 className="hero-in balance mt-4 font-display text-[40px] font-bold leading-[1.03] tracking-[-0.035em] sm:text-[56px] lg:text-[68px] xl:text-[76px]" style={{ animationDelay: "90ms" }}>
              {t("home.h1")}
            </h1>
            <p className="hero-in text-2 mt-4 max-w-[42ch] text-[18px] leading-[1.45] sm:text-[20px] lg:mt-5 lg:text-[21px]" style={{ animationDelay: "140ms" }}>
              {t("home.lead")}
            </p>

            <div className="hero-in" style={{ animationDelay: "190ms" }}>
              <form onSubmit={onSubmit} className="glass search-pill mt-7 max-w-[620px] rounded-[30px] p-2 transition-shadow sm:flex sm:items-center sm:gap-2 lg:mt-9" noValidate>
                <label className="flex flex-1 cursor-text items-center gap-3 pl-3 pr-2">
                  <Globe size={20} className="text-3 shrink-0" aria-hidden="true" />
                  <span className="sr-only">{t("home.address")}</span>
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
                    placeholder={t("home.placeholder")}
                    className="h-[52px] w-full min-w-0 bg-transparent text-[18px] outline-none placeholder:text-[var(--label-3)]"
                    aria-invalid={urlError ? true : undefined}
                    aria-describedby={urlError ? "url-error" : "url-hint"}
                  />
                </label>
                <button type="submit" className="btn-primary mt-2 w-full sm:mt-0 sm:w-auto" disabled={starting} aria-busy={starting || undefined}>
                  {starting ? <Loader2 className="spin" size={20} aria-hidden="true" /> : null}
                  {starting ? t("home.starting") : t("home.check")}
                  {!starting ? <ArrowRight size={19} strokeWidth={2.4} aria-hidden="true" /> : null}
                </button>
              </form>
              {urlError ? (
                <ErrorText id="url-error" className="mt-3">{urlError}</ErrorText>
              ) : (
                <ul id="url-hint" className="text-2 mt-4 flex flex-wrap gap-x-5 gap-y-2 px-2 text-[14px] font-medium">
                  <li className="inline-flex items-center gap-1.5"><Clock size={16} className="ink-brand" aria-hidden="true" /> {t("home.hint_time")}</li>
                  <li className="inline-flex items-center gap-1.5"><Eye size={16} className="ink-brand" aria-hidden="true" /> {t("home.hint_public")}</li>
                  <li className="inline-flex items-center gap-1.5"><FileText size={16} className="ink-brand" aria-hidden="true" /> {t("home.hint_pdf")}</li>
                </ul>
              )}
            </div>
          </div>

          {/* Two sizes, chosen by CSS rather than script, so the page looks the same before and after it starts. */}
          <div className="hero-ring order-first lg:order-none">
            <div className="lg:hidden">
              <ScoreRing statuses={{}} size={210} checks={ALL_CHECKS} />
            </div>
            <div className="hidden lg:block">
              <ScoreRing statuses={{}} size={360} checks={ALL_CHECKS} />
            </div>
          </div>
        </section>

        {/* ------------------------------------------------------------ what we check */}
        <section className="mt-14 lg:mt-10" aria-labelledby="what-we-check">
          <Reveal className="flex flex-col gap-1 lg:flex-row lg:items-end lg:justify-between lg:gap-8">
            <h2 id="what-we-check" className="font-display text-[26px] font-bold tracking-tight lg:text-[32px]">
              {t("home.what")}
            </h2>
            <p className="text-2 max-w-[52ch] text-[15px] leading-snug lg:text-right lg:text-[16px]">
              {t("home.what_text", { agent: AGENT_SCORED.length, health: CHECKS.length })}
            </p>
          </Reveal>
          {/* AI agent readiness first, across the full width. Then, on wide screens, Security (the
              longest list) runs down the left, four health areas sit two by two beside it, and
              content and accessibility fills the last row. */}
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
                      <span className="block text-[18px] font-semibold leading-tight">{t("area.agent")}</span>
                      <span className="text-3 block text-[13px] font-medium">{t("home.agent_count", { n: AGENT_SCORED.length })}</span>
                    </span>
                  </div>
                  <p className="text-2 mt-3 text-[15px] leading-snug lg:text-[16px]">
                    {t("home.agent_text")}
                  </p>
                </div>
                <ul className="grid gap-x-6 gap-y-3 sm:grid-cols-2 xl:grid-cols-3">
                  {AGENT_SCORED.map((ch) => (
                    <li key={ch.key} className="flex gap-2.5">
                      <span className="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: "var(--brand)" }} aria-hidden="true" />
                      <span>
                        <span className="block text-[15px] font-semibold leading-snug">{t(checkName(ch.key))}</span>
                        <span className="text-2 block text-[14px] leading-snug">{t(checkBlurb(ch.key))}</span>
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            </StaggerItem>
            {CATEGORIES.map((c) => {
              const checks = CHECKS.filter((ch) => ch.category === c.key);
              const big = c.key === "security";
              const wide = c.key === "content";
              return (
                <StaggerItem
                  as="li"
                  key={c.key}
                  className={`glass flex flex-col rounded-[26px] p-5 ${big ? "sm:col-span-2 lg:col-span-1 lg:row-span-3" : ""} ${wide ? "sm:col-span-2" : ""}`}
                >
                  <div className="flex items-center gap-3">
                    <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-[13px]" style={{ background: "var(--tint-brand)" }}>
                      <c.icon size={22} className="ink-brand" aria-hidden="true" />
                    </span>
                    <span>
                      <span className="block text-[18px] font-semibold leading-tight">{t(areaName(c.key))}</span>
                      <span className="text-3 block text-[13px] font-medium">{t("home.checks_n", { n: checks.length })}</span>
                    </span>
                  </div>
                  <p className="text-2 mt-3 text-[15px] leading-snug lg:hidden">{t(areaBlurb(c.key))}</p>
                  <ul className={`mt-4 hidden gap-y-2.5 lg:grid ${big ? "lg:mt-5 lg:gap-y-3" : ""} ${wide ? "lg:grid-cols-2 lg:gap-x-6" : ""}`}>
                    {checks.map((ch) => (
                      <li key={ch.key} className="text-2 flex items-center gap-2.5 text-[15px]">
                        <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: "var(--brand)" }} aria-hidden="true" />
                        {t(checkName(ch.key))}
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
              {t("home.how")}
            </h2>
          </Reveal>
          <Stagger as="ul" className="mt-5 grid gap-3 md:grid-cols-3 lg:gap-4">
            {STEPS.map((st, i) => (
              <StaggerItem as="li" key={st.title} className="glass relative flex gap-4 rounded-[26px] p-5 md:flex-col md:gap-0 lg:p-6">
                <span className="relative flex h-11 w-11 shrink-0 items-center justify-center rounded-[13px]" style={{ background: "var(--tint-brand)" }}>
                  <st.icon size={21} className="ink-brand" aria-hidden="true" />
                </span>
                <span className="md:mt-4">
                  <span className="text-3 block text-[13px] font-semibold uppercase tracking-[0.06em]">{t("home.step", { n: i + 1 })}</span>
                  <span className="mt-0.5 block text-[18px] font-semibold leading-snug">{t(st.title)}</span>
                  <span className="text-2 mt-1 block text-[15px] leading-snug">{t(st.body)}</span>
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
            <h2 className="balance font-display text-[26px] font-bold leading-tight tracking-tight lg:text-[32px]">{t("home.cta")}</h2>
            <p className="text-2 mt-2 max-w-[56ch] text-[15px] leading-snug lg:text-[16px]">
              {t("home.cta_text")}
            </p>
          </div>
          <button type="button" className="btn-primary relative mt-5 w-full shrink-0 sm:w-auto lg:mt-0" onClick={backToTop}>
            {t("home.check")} <ArrowRight size={19} strokeWidth={2.4} aria-hidden="true" />
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
        submitLabel={url.trim() ? t("home.start_scan") : t("home.save_email")}
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


