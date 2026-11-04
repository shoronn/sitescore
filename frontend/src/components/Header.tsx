import { Link } from "react-router-dom";
import { ThemeMenu } from "./ThemeToggle";

export function Brand({ to = "/", sub = "by MAKTECH", label = "SiteScore by MAKTECH, home" }: { to?: string; sub?: string; label?: string }) {
  return (
    <Link to={to} className="glass flex shrink-0 items-center gap-2.5 rounded-capsule py-1.5 pl-1.5 pr-4 transition-transform active:scale-[0.97]" aria-label={label}>
      <img src="/logo-64.png" alt="" width={32} height={32} className="h-8 w-8" decoding="async" />
      <span className="flex flex-col leading-none">
        <span className="font-display text-[17px] font-bold tracking-tight">SiteScore</span>
        <span className="text-2 mt-[3px] text-[11px] font-semibold">{sub}</span>
      </span>
    </Link>
  );
}

export default function Header({ right }: { right?: React.ReactNode }) {
  return (
    <header className="shell relative z-20 flex items-center justify-between gap-3 pt-[max(16px,env(safe-area-inset-top))]">
      <Brand />
      <div className="flex min-w-0 items-center gap-2">
        {right}
        <ThemeMenu />
      </div>
    </header>
  );
}
