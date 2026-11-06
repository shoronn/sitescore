import { Link } from "react-router-dom";
import { useT } from "../i18n";
import { ThemeSegmented } from "./ThemeToggle";

export default function Footer() {
  const { t, n } = useT();
  return (
    <footer className="shell relative z-10 mt-auto pb-[max(24px,env(safe-area-inset-bottom))] pt-10">
      <div className="hairline flex flex-col gap-4 border-t pt-5 md:flex-row md:items-center md:justify-between">
        <nav className="text-2 -ml-2 flex flex-wrap text-[14px] font-medium" aria-label={t("footer.nav")}>
          <Link to="/about" className="footer-link">{t("footer.about")}</Link>
          <Link to="/privacy" className="footer-link">{t("footer.privacy")}</Link>
          <Link to="/terms" className="footer-link">{t("footer.terms")}</Link>
          <a href="mailto:sitescore@maktechgroup.com" className="footer-link">{t("footer.contact")}</a>
        </nav>
        <div className="self-start md:self-auto">
          <ThemeSegmented />
        </div>
      </div>
      <div className="text-3 mt-3 flex flex-col gap-1 text-[13px] sm:flex-row sm:items-center sm:justify-between">
        <p>&copy; {n(new Date().getFullYear())} MAKTECH. {t("footer.free")}</p>
        <p>
          {t("footer.dev")} <span className="font-semibold" style={{ color: "var(--label-2)" }}>SHORON</span>
        </p>
      </div>
    </footer>
  );
}
