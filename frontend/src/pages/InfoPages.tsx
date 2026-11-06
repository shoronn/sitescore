import { Info, Mail as MailIcon, ScrollText, ShieldCheck } from "lucide-react";
import { useEffect } from "react";
import { Link, useLocation } from "react-router-dom";
import Footer from "../components/Footer";
import Header from "../components/Header";
import { translate, useT, type MessageKey } from "../i18n";

const CONTACT = "sitescore@maktechgroup.com";
const ADDRESS = "8th Floor, A, Majid Tower, Ka-24 Progati Sarani Rd, Dhaka 1229, Bangladesh";
const MAP = "https://maps.google.com/?q=Majid+Tower,+Ka-24+Progati+Sarani+Rd,+Dhaka+1229";
const PHONE = "+880 1897 669234";
const PHONE_TEL = "+8801897669234";
const UPDATED = "31 October 2026";

const PAGES: { to: string; label: MessageKey; icon: typeof Info }[] = [
  { to: "/about", label: "info.about", icon: Info },
  { to: "/privacy", label: "info.privacy", icon: ShieldCheck },
  { to: "/terms", label: "info.terms", icon: ScrollText },
];

/** englishOnly: the legal pages stay in English; Bangla visitors see a note saying so. */
function Page({ title, children, englishOnly }: { title: string; children: React.ReactNode; englishOnly?: boolean }) {
  const { pathname } = useLocation();
  const { t, lang } = useT();
  useEffect(() => {
    document.title = `${title} | SiteScore by MAKTECH`;
  }, [title]);
  return (
    <>
      <Header />
      <main className="shell relative z-10 pt-8 lg:pt-12">
        <div className="lg:grid lg:grid-cols-[240px_minmax(0,1fr)] lg:gap-10 xl:grid-cols-[260px_minmax(0,820px)] xl:justify-center xl:gap-14">
          <nav aria-label={t("info.nav")} className="mb-4 lg:mb-0">
            <ul className="-mx-5 flex gap-2 overflow-x-auto px-5 pb-1 [scrollbar-width:none] lg:sticky lg:top-8 lg:mx-0 lg:flex-col lg:gap-1 lg:overflow-visible lg:px-0">
              {PAGES.map((pg) => {
                const active = pathname === pg.to;
                return (
                  <li key={pg.to} className="shrink-0">
                    <Link
                      to={pg.to}
                      aria-current={active ? "page" : undefined}
                      className={`relative flex min-h-[44px] items-center gap-2.5 rounded-capsule px-4 text-[15px] font-semibold lg:rounded-2xl ${active ? "" : "glass row-btn lg:border-transparent lg:bg-none lg:shadow-none"}`}
                      style={active ? { background: "var(--label)", color: "var(--bg)" } : { color: "var(--label-2)" }}
                    >
                      <pg.icon size={17} aria-hidden="true" />
                      {t(pg.label)}
                    </Link>
                  </li>
                );
              })}
              <li className="shrink-0 lg:mt-3">
                <a
                  href={`mailto:${CONTACT}`}
                  className="glass flex min-h-[44px] items-center gap-2.5 rounded-capsule px-4 text-[15px] font-semibold lg:rounded-2xl lg:border-transparent lg:bg-none lg:shadow-none"
                  style={{ color: "var(--label-2)" }}
                >
                  <MailIcon size={17} aria-hidden="true" /> {t("info.contact")}
                </a>
              </li>
            </ul>
          </nav>
          <article className="glass rise-enter rounded-glass px-5 py-7 sm:px-10 sm:py-10">
            <h1 className="balance font-display text-[32px] font-bold leading-tight tracking-tight sm:text-[40px]">{title}</h1>
            {englishOnly && lang === "bn" ? (
              <p className="mt-4 rounded-2xl px-4 py-3 text-[15px] leading-snug" style={{ background: "var(--tint-brand)" }} lang="bn">
                {t("info.english_only")}
              </p>
            ) : null}
            <div className="info-prose mt-5" lang={englishOnly ? "en" : undefined}>{children}</div>
          </article>
        </div>
      </main>
      <Footer />
    </>
  );
}

const Mail = () => <a href={`mailto:${CONTACT}`}>{CONTACT}</a>;

/** english: on the English-only legal pages this part stays in English too. */
function WhoWeAre({ english }: { english?: boolean }) {
  const { t: local } = useT();
  const t = (key: MessageKey) => (english ? translate("en", key) : local(key));
  return (
    <>
      <h2>{t("about.who")}</h2>
      <p>
        {t("about.who_text1")} <a href={MAP} target="_blank" rel="noreferrer">{ADDRESS}</a>. {t("about.who_email")} <Mail />.{" "}
        {t("about.who_phone")} <a href={`tel:${PHONE_TEL}`}>{PHONE}</a>.
      </p>
    </>
  );
}

export function AboutPage() {
  const { t } = useT();
  return (
    <Page title={t("info.about")}>
      <p>{t("about.intro")}</p>

      <h2>{t("about.does")}</h2>
      <ul>
        {(["about.does1", "about.does2", "about.does3", "about.does4", "about.does5", "about.does6", "about.does7"] as const).map((k) => (
          <li key={k}>{t(k)}</li>
        ))}
      </ul>

      <h2>{t("about.never")}</h2>
      <ul>
        <li>{t("about.never1")}</li>
        <li>{t("about.never2")}</li>
        <li>{t("about.never3")}</li>
      </ul>

      <h2>{t("about.logs")}</h2>
      <p>
        {t("about.logs_text1")} <code>MAKTECH-SiteScore/1.0 (+https://sitescore.maktechgroup.com/about)</code>.{" "}
        {t("about.logs_text2")} <code>Chrome-Lighthouse</code>. {t("about.logs_text3")} <Mail /> {t("about.logs_text4")}
      </p>

      <h2>{t("about.help")}</h2>
      <p>
        {t("about.help_text1")} <a href={`tel:${PHONE_TEL}`}>{PHONE}</a>, {t("about.help_text2")} <Mail />.
      </p>
      <WhoWeAre />
      <p><Link to="/">{t("about.check")}</Link></p>
    </Page>
  );
}

export function PrivacyPage() {
  return (
    <Page title="Privacy" englishOnly>
      <p className="text-2">Last updated {UPDATED}</p>
      <p>
        This page explains what SiteScore collects, why, and how long we keep it. Questions or requests: <Mail />.
      </p>
      <WhoWeAre english />

      <h2>What we collect</h2>
      <ul>
        <li><strong>Your email address</strong>, to send your report.</li>
        <li><strong>Your name, business name and phone number</strong>, only if you give them.</li>
        <li><strong>The websites you scan and their results.</strong></li>
        <li><strong>Your IP address and the time you started a scan</strong>, to enforce fair-use limits and prevent misuse.</li>
      </ul>

      <h2>How we use it</h2>
      <ul>
        <li>To run your scan, show your results and email your report.</li>
        <li>So a MAKTECH advisor can contact you about your results, as the form explains. You can ask us to stop at any time.</li>
        <li>To enforce fair-use limits and stop abuse.</li>
      </ul>
      <p>We do not sell your information or use advertising trackers.</p>

      <h2>Who else sees it</h2>
      <ul>
        <li>Our own email server sends your reports.</li>
        <li>
          The speed test runs on our own server. Only when our test browser cannot load a site (for example because of bot
          protection) do we ask Google PageSpeed Insights instead, which receives the website's address and nothing about you.
        </li>
      </ul>

      <h2>Cookies</h2>
      <p>
        One cookie remembers your email address for 30 days, so you do not need to type it again for every scan. There are no analytics
        or advertising cookies.
      </p>

      <h2>How long we keep it</h2>
      <ul>
        <li>Results links: stop working after 30 days.</li>
        <li>Your details and scans: deleted after 12 months, unless you become a MAKTECH customer.</li>
      </ul>

      <h2>Your choices</h2>
      <p>
        Email <Mail /> to get a copy of your information, correct it, have it deleted, or stop us contacting you. We reply within 7 working days.
      </p>
    </Page>
  );
}

export function TermsPage() {
  return (
    <Page title="Terms of use" englishOnly>
      <p className="text-2">Last updated {UPDATED}</p>
      <p>By using SiteScore you agree to these terms. Questions: <Mail />.</p>
      <WhoWeAre english />

      <h2>Which sites you can check</h2>
      <p>
        You can check any public website: yours, a client's or a competitor's. SiteScore only looks at what any visitor or search
        engine can already see, and never logs in, fills in forms or tries to break anything. A site's owner can ask us never to scan
        it by emailing <Mail />.
      </p>

      <h2>What the results are</h2>
      <p>
        SiteScore runs automated checks of public information. The results are guidance, not a full security audit, and they can miss
        problems or be affected by temporary network conditions. A good score is not a guarantee that a site is secure.
      </p>

      <h2>Fair use</h2>
      <ul>
        <li>SiteScore is free, with a limit of 5 scans per person per day.</li>
        <li>Do not automate requests, try to get around the limits, or use SiteScore to harm any website.</li>
        <li>We may block access that breaks these rules.</li>
      </ul>

      <h2>Our responsibility</h2>
      <p>
        SiteScore is provided as it is, without warranties. As far as the law allows, MAKTECH is not liable for losses arising from
        the use of SiteScore or its results. Any work you hire MAKTECH to do is covered by its own agreement.
      </p>

      <h2>Changes</h2>
      <p>We may update these terms. The date at the top shows the latest version.</p>
    </Page>
  );
}
