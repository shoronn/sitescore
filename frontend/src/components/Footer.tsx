import { Link } from "react-router-dom";
import { ThemeSegmented } from "./ThemeToggle";

export default function Footer() {
  return (
    <footer className="shell relative z-10 mt-auto pb-[max(24px,env(safe-area-inset-bottom))] pt-10">
      <div className="hairline flex flex-col gap-4 border-t pt-5 md:flex-row md:items-center md:justify-between">
        <nav className="text-2 -ml-2 flex flex-wrap text-[14px] font-medium" aria-label="About SiteScore">
          <Link to="/about" className="footer-link">About</Link>
          <Link to="/privacy" className="footer-link">Privacy</Link>
          <Link to="/terms" className="footer-link">Terms</Link>
          <a href="mailto:sitescore@maktechgroup.com" className="footer-link">Contact</a>
        </nav>
        <div className="self-start md:self-auto">
          <ThemeSegmented />
        </div>
      </div>
      <div className="text-3 mt-3 flex flex-col gap-1 text-[13px] sm:flex-row sm:items-center sm:justify-between">
        <p>&copy; {new Date().getFullYear()} MAKTECH. SiteScore is free to use.</p>
        <p>
          Developed by <span className="font-semibold" style={{ color: "var(--label-2)" }}>SHORON</span>
        </p>
      </div>
    </footer>
  );
}
