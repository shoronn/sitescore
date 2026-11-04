import { Activity, Bot, Gauge, Mail, Search, ShieldCheck, type LucideIcon } from "lucide-react";

export interface CheckInfo {
  key: string;
  name: string;
  category: CategoryKey;
}

export type CategoryKey = "security" | "reliability" | "email" | "performance" | "seo";

export interface AgentCheckInfo {
  key: string;
  name: string;
  /** One line for the home page: what it looks for. */
  blurb: string;
  /** Shown for information, not scored (llms.txt). */
  optional?: boolean;
}

// AI agent readiness: scored on its own, out of 100. Same keys and order as the engine
// (AGENT_KEYS in backend/sitescore/engine/checks/__init__.py).
export const AGENT_CHECKS: AgentCheckInfo[] = [
  { key: "robots_txt", name: "robots.txt", blurb: "The first file AI agents and search engines read" },
  { key: "sitemap", name: "Sitemap", blurb: "A map of every page, so agents miss nothing" },
  { key: "link_headers", name: "Link headers", blurb: "Point agents to machine-readable content" },
  { key: "markdown", name: "Markdown for agents", blurb: "Clean text for agents instead of the full web page" },
  { key: "ai_rules", name: "AI crawler rules", blurb: "Whether ChatGPT, Claude and others may read your site" },
  { key: "content_signals", name: "Content Signals", blurb: "How AI may use your content: search, answers, training" },
  { key: "llms_txt", name: "llms.txt", blurb: "A short guide for AI tools", optional: true },
];
export const AGENT_SCORED = AGENT_CHECKS.filter((c) => !c.optional);
export const AGENT_AREA = {
  label: "AI agent readiness",
  icon: Bot,
  blurb: "Can ChatGPT, Claude and other AI agents find, read and recommend your site?",
};

// The website health checks. Same keys and order as the engine, so ring segments line
// up with the list.
export const CHECKS: CheckInfo[] = [
  { key: "https", name: "HTTPS", category: "security" },
  { key: "ssl", name: "SSL certificate", category: "security" },
  { key: "headers", name: "Security headers", category: "security" },
  { key: "software", name: "Software versions", category: "security" },
  { key: "exposed_files", name: "Exposed files", category: "security" },
  { key: "directory_listing", name: "Open folders", category: "security" },
  { key: "mixed_content", name: "Secure page content", category: "security" },
  { key: "cookies", name: "Cookie safety", category: "security" },
  { key: "security_txt", name: "Security contact", category: "security" },
  { key: "dnssec", name: "DNSSEC", category: "security" },
  { key: "uptime", name: "Uptime and response time", category: "reliability" },
  { key: "domain_expiry", name: "Domain expiry", category: "reliability" },
  { key: "dns", name: "DNS health", category: "reliability" },
  { key: "spf", name: "SPF", category: "email" },
  { key: "dkim", name: "DKIM", category: "email" },
  { key: "dmarc", name: "DMARC", category: "email" },
  { key: "blacklist", name: "Blocklists", category: "email" },
  { key: "mobile_speed", name: "Mobile speed score", category: "performance" },
  { key: "web_vitals", name: "Core Web Vitals", category: "performance" },
  { key: "meta_tags", name: "Title and description", category: "seo" },
  { key: "mobile_viewport", name: "Mobile-friendly setup", category: "seo" },
  { key: "indexing", name: "Search engine access", category: "seo" },
  { key: "social_preview", name: "Sharing preview", category: "seo" },
];

/** Every check in a scan, for progress: agent checks first, then health. */
export const ALL_CHECK_KEYS: string[] = [...AGENT_CHECKS.map((c) => c.key), ...CHECKS.map((c) => c.key)];

export const CATEGORIES: { key: CategoryKey; label: string; icon: LucideIcon; blurb: string }[] = [
  { key: "security", label: "Security", icon: ShieldCheck, blurb: "HTTPS, SSL, security headers, outdated software, exposed files and more" },
  { key: "reliability", label: "Reliability", icon: Activity, blurb: "Uptime, response time, domain expiry and DNS" },
  { key: "email", label: "Email", icon: Mail, blurb: "SPF, DKIM, DMARC and spam blocklists" },
  { key: "performance", label: "Performance", icon: Gauge, blurb: "Mobile speed score and Core Web Vitals, measured in a real browser" },
  { key: "seo", label: "Search and sharing", icon: Search, blurb: "Google listing, mobile setup, sitemap and sharing preview" },
];
