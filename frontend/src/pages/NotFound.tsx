import { SearchX } from "lucide-react";
import { useEffect } from "react";
import { Link } from "react-router-dom";
import Footer from "../components/Footer";
import Header from "../components/Header";
import { useT } from "../i18n";

/** Any address the site does not have. The server also answers these with status 404. */
export default function NotFound() {
  const { t } = useT();
  useEffect(() => {
    document.title = `${t("nf.title")} | SiteScore by MAKTECH`;
  }, [t]);
  return (
    <>
      <Header />
      <main className="shell relative z-10 pb-6">
        <div className="glass rise-enter mx-auto mt-10 max-w-md rounded-glass p-6 text-center sm:p-8">
          <span className="mx-auto flex h-14 w-14 items-center justify-center rounded-full" style={{ background: "var(--tint-brand)" }} aria-hidden="true">
            <SearchX size={26} className="ink-brand" />
          </span>
          <h1 className="balance mt-4 font-display text-[24px] font-bold leading-tight tracking-tight">{t("nf.title")}</h1>
          <p className="text-2 mt-2 text-[16px] leading-snug">{t("nf.text")}</p>
          <Link to="/" className="btn-primary mt-6 w-full">{t("nf.home")}</Link>
        </div>
      </main>
      <Footer />
    </>
  );
}
