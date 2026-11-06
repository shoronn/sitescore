"""Importing this package registers every check, in report order."""
from . import agent, web, exposure, hardening, reliability, email, performance, seo, content  # noqa: F401
from .base import REGISTRY

# Report order: AI agent readiness first (its own score), then the health checks:
# security, reliability, email, performance, search and sharing, content and accessibility.
# The web app lists the same keys in the same order (frontend/src/checks.ts).
AGENT_KEYS = ["robots_txt", "sitemap", "link_headers", "markdown", "ai_rules", "content_signals", "llms_txt"]
ORDER = [
    *AGENT_KEYS,
    "https", "ssl", "headers", "software",
    "exposed_files", "directory_listing", "mixed_content", "cookies", "security_txt", "dnssec",
    "uptime", "domain_expiry", "dns",
    "spf", "dkim", "dmarc", "blacklist", "mta_sts",
    "mobile_speed", "web_vitals",
    "meta_tags", "mobile_viewport", "indexing", "canonical", "structured_data", "error_page", "social_preview",
    "accessibility", "headings", "image_alt", "content_depth", "contact_info", "page_basics",
]
CHECKS = sorted(REGISTRY, key=lambda c: ORDER.index(c.key))
# The health score's 100 points; the agent checks have their own 100.
TOTAL_WEIGHT = sum(c.weight for c in CHECKS if c.key not in AGENT_KEYS)
AGENT_WEIGHT = sum(c.weight for c in CHECKS if c.key in AGENT_KEYS)

__all__ = ["AGENT_KEYS", "AGENT_WEIGHT", "CHECKS", "TOTAL_WEIGHT"]
