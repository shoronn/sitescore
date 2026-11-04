"""All settings come from environment variables (or a .env file). See .env.example."""
from __future__ import annotations

import os
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_SECRET = "change-me-in-production-please-use-64-random-chars"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="SITESCORE_", extra="ignore")

    # Core
    env: str = "development"  # development | production
    secret_key: str = Field(DEFAULT_SECRET)
    log_level: str = "INFO"
    public_base_url: str = "https://sitescore.maktechgroup.com"  # the web app, used in email links
    cors_origins: str = "https://sitescore.maktechgroup.com"  # comma-separated web app origins
    auto_create_tables: bool = False  # development shortcut; production uses Alembic migrations
    database_url: str = "postgresql+asyncpg://sitescore:sitescore@localhost:5432/sitescore"
    redis_url: str | None = "redis://localhost:6379/0"
    queue_mode: str = "rq"  # rq | inline (inline runs scans inside the API process; dev/tests only)
    trust_proxy_headers: bool = True  # read the client IP from X-Forwarded-For (behind Coolify's proxy)
    trusted_proxy_hops: int = 1  # proxies in front of the API that append to X-Forwarded-For
    client_ip_header: str | None = None  # e.g. CF-Connecting-IP when Cloudflare proxies the API

    # Session cookies
    staff_cookie_name: str = "ss_staff"
    staff_session_hours: int = 12
    staff_logins_per_ip_per_hour: int = 20
    cookie_name: str = "ss_session"
    cookie_secure: bool = True
    session_days: int = 30

    # Email address check at sign-up: format, a domain that accepts mail (DNS lookup) and no
    # throwaway providers. There is no code by email.
    email_check_deliverability: bool = True

    # Rate limits
    signups_per_ip_per_hour: int = 20
    scans_per_lead_per_day: int = 5
    scans_per_ip_per_day: int = 10
    results_link_days: int = 30
    lead_retention_days: int = 365  # leads not marked "won" are deleted after this
    pdf_downloads_per_ip_per_hour: int = 30

    # Email delivery (empty host = print emails to the log; development only)
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_starttls: bool = True
    mail_from: str = "MAKTECH SiteScore <sitescore@maktechgroup.com>"  # sends and receives replies
    company_address: str = "8th Floor, A, Majid Tower, Ka-24 Progati Sarani Rd, Dhaka 1229, Bangladesh"

    # Shown on the results page as "Chat on WhatsApp" when set, e.g. 8801700000000
    whatsapp_number: str | None = "8801897669234"
    # Shown as "Call us" on the results page and in the PDF. Country code first, digits only.
    contact_phone: str | None = "8801897669234"
    # Fix-It Starter Pack, one-time price shown on the results page and in the PDF.
    # Whole round numbers in each currency; visitors switch between USD and BDT.
    offer_price_usd: int = 40
    offer_price_bdt: int = 5000

    # Bot protection (empty = off; development only)
    turnstile_secret: str | None = None
    turnstile_site_key: str | None = None

    # Scan engine
    # Built-in speed test (Lighthouse in headless Chromium, installed in the Docker image).
    # Slots: how many tests may run at once in the worker container. Each needs about one
    # CPU core and 500 MB of memory; running too many at once makes every score worse.
    speed_test_slots: int = 2
    speed_test_timeout: int = 240  # seconds, including waiting for a free slot and one retry
    # A test starts only with this much memory free (MB), so a busy server never runs out.
    speed_test_min_free_mb: int = 600
    lighthouse_cmd: str = "lighthouse"
    chrome_path: str | None = None  # found automatically in the Docker image
    speed_test_ignore_cert_errors: bool = False  # development only
    # Optional backup for the speed test: a Google PageSpeed Insights API key. Used only when
    # our own browser cannot test a page (bot protection, a firewall, a busy server).
    psi_api_key: str | None = None
    blocked_networks: str = ""  # comma-separated CIDRs to refuse besides private ranges
    opt_out_domains: str = ""  # comma-separated domains whose owners asked us never to scan them
    dnsbl_zones: str = "bl.spamcop.net,psbl.surriel.com,b.barracudacentral.org"
    user_agent: str = "MAKTECH-SiteScore/1.0 (+https://sitescore.maktechgroup.com/about)"

    @field_validator("secret_key", mode="before")
    @classmethod
    def _blank_secret_means_unset(cls, v):
        # An empty value gets the clear start-up message instead of a validation trace.
        return v if isinstance(v, str) and v.strip() else DEFAULT_SECRET

    @field_validator("database_url", mode="before")
    @classmethod
    def _asyncpg_driver(cls, v):
        # Coolify and most hosts hand out postgres:// or postgresql:// URLs. The app
        # talks to Postgres through asyncpg, so any plain Postgres URL is switched to it.
        if not isinstance(v, str):
            return v
        v = v.strip().strip("'\"")
        scheme, sep, rest = v.partition("://")
        scheme = scheme.lower()
        if sep and (scheme in ("postgres", "postgresql") or scheme.startswith("postgresql+")):
            return "postgresql+asyncpg://" + rest
        return v

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    def production_problems(self) -> list[str]:
        """Settings that would make a production deploy unsafe or broken. Empty = fine."""
        if not self.is_production:
            return []
        problems = []
        if self.secret_key == DEFAULT_SECRET or len(self.secret_key) < 40:
            problems.append("SITESCORE_SECRET_KEY must be set to a long random value (40+ characters).")
        if any(p in self.database_url for p in ("localhost", "CHANGE_ME", "USER:PASSWORD@HOST")):
            problems.append("SITESCORE_DATABASE_URL still points at the development default.")
        if not self.database_url.startswith("postgresql+asyncpg://"):
            problems.append("SITESCORE_DATABASE_URL must be a PostgreSQL URL, for example postgres://USER:PASS@HOST:5432/DB.")
        if self.queue_mode != "rq" or not self.redis_url:
            problems.append("SITESCORE_REDIS_URL must be set (and SITESCORE_QUEUE_MODE must be rq).")
        if not self.smtp_host or not self.smtp_user or not self.smtp_password:
            problems.append("SITESCORE_SMTP_HOST, SITESCORE_SMTP_USER and SITESCORE_SMTP_PASSWORD must be set.")
        if not self.public_base_url.startswith("https://"):
            problems.append("SITESCORE_PUBLIC_BASE_URL must be an https:// address.")
        origins = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        if not origins or any(not o.startswith("https://") for o in origins):
            problems.append("SITESCORE_CORS_ORIGINS must list the web app's https:// address.")
        if not self.cookie_secure:
            problems.append("SITESCORE_COOKIE_SECURE must be true in production.")
        return problems

    def production_warnings(self) -> list[str]:
        if not self.is_production:
            return []
        warnings = []
        if os.environ.get("SITESCORE_ROLE") == "worker":
            from .engine.speedtest import tools_problem

            problem = tools_problem(self.lighthouse_cmd, self.chrome_path)
            if problem:
                warnings.append(f"The speed test cannot run: {problem} Performance checks will say 'not checked'.")
            if not self.psi_api_key:
                warnings.append("SITESCORE_PSI_API_KEY is not set: sites our test browser cannot load "
                                "(bot protection, firewalls) will show the speed checks as 'not checked'.")
        if not self.turnstile_secret:
            warnings.append("Turnstile is off: sign-ups and scans rely on rate limits only.")
        return warnings


class ConfigError(RuntimeError):
    pass


def check_settings(settings: "Settings") -> None:
    """Raise ConfigError listing every problem, so a bad deploy stops at start-up with a clear message."""
    import logging

    problems = settings.production_problems()
    if problems:
        raise ConfigError("SiteScore cannot start in production:\n- " + "\n- ".join(problems))
    for w in settings.production_warnings():
        logging.getLogger("sitescore.config").warning(w)


@lru_cache
def get_settings() -> Settings:
    return Settings()


def engine_settings(s: Settings | None = None):
    from .engine import EngineSettings

    s = s or get_settings()
    return EngineSettings(
        user_agent=s.user_agent,
        speed_timeout=float(s.speed_test_timeout),
        speed_slots=s.speed_test_slots,
        speed_min_free_mb=s.speed_test_min_free_mb,
        lighthouse_cmd=s.lighthouse_cmd,
        psi_api_key=s.psi_api_key or None,
        chrome_path=s.chrome_path,
        speed_ignore_cert_errors=s.speed_test_ignore_cert_errors and not s.is_production,
        blocked_networks=tuple(x for x in s.blocked_networks.split(",") if x.strip()),
        dnsbl_ip_zones=tuple(x.strip() for x in s.dnsbl_zones.split(",") if x.strip()),
    )
