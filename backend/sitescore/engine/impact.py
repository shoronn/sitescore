"""How serious each finding is, and what it means for the business.

Severity: "error" (a failed check), "warning" (worth fixing), "notice" (a small
improvement), "good" (passed) or "not_checked". Impact groups put the checks under the
outcome a business owner cares about, such as "Emails may land in spam".
"""
from __future__ import annotations

from typing import Any

# Warnings that are small improvements rather than real problems.
NOTICES = {
    ("headings", "many_h1"), ("headings", "skipped"), ("canonical", "missing"),
    ("mta_sts", "missing"), ("mta_sts", "no_tlsrpt"), ("mta_sts", "no_sts"),
    ("error_page", "redirects"), ("social_preview", "no_favicon"), ("social_preview", "partial"),
    ("content_depth", "needs_scripts"), ("contact_info", "contact_page_only"),
    ("security_txt", "missing"), ("dnssec", "off"), ("spf", "near_limit"),
    ("structured_data", "no_business"), ("structured_data", "incomplete"), ("page_basics", "missing"),
    ("meta_tags", "title_length"), ("meta_tags", "description_length"), ("dkim", "not_found"),
}


def severity(key: str, status: str, reason: str, weight: int) -> str:
    if status == "pass":
        return "good"
    if status == "fail":
        return "error"
    if status == "warn":
        return "notice" if weight == 0 or (key, reason) in NOTICES else "warning"
    return "not_checked"


# (key, {lang: (label when all is well, label when something needs fixing, plain name)}, checks)
GROUPS: list[tuple[str, dict[str, tuple[str, str, str]], list[str]]] = [
    ("ai", {"en": ("AI assistants can read your site", "AI assistants struggle to read your site", "AI assistants"),
            "bn": ("AI অ্যাসিস্ট্যান্টরা আপনার সাইট পড়তে পারে", "AI অ্যাসিস্ট্যান্টরা আপনার সাইট পড়তে হিমশিম খায়", "AI অ্যাসিস্ট্যান্ট")},
     ["robots_txt", "sitemap", "link_headers", "markdown", "ai_rules", "content_signals", "llms_txt"]),
    ("google", {"en": ("Easy to find on Google", "Harder to find on Google", "Google search"),
                "bn": ("Google-এ সহজেই খুঁজে পাওয়া যায়", "Google-এ খুঁজে পাওয়া কঠিন", "Google সার্চ")},
     ["meta_tags", "indexing", "canonical", "structured_data", "error_page", "headings", "content_depth",
      "mobile_viewport", "social_preview"]),
    ("speed", {"en": ("Pages load fast", "Slow pages lose visitors", "Page speed"),
               "bn": ("পেজ দ্রুত লোড হয়", "ধীর পেজে ভিজিটর হারায়", "পেজের গতি")},
     ["mobile_speed", "web_vitals"]),
    ("email", {"en": ("Your emails reach the inbox", "Your emails may land in spam", "Email delivery"),
               "bn": ("আপনার ইমেইল ইনবক্সে পৌঁছায়", "আপনার ইমেইল স্প্যামে যেতে পারে", "ইমেইল ডেলিভারি")},
     ["spf", "dkim", "dmarc", "blacklist", "mta_sts"]),
    ("security", {"en": ("Protected against common attacks", "Open to common attacks", "Security"),
                  "bn": ("সাধারণ আক্রমণ থেকে সুরক্ষিত", "সাধারণ আক্রমণের ঝুঁকিতে", "নিরাপত্তা")},
     ["https", "ssl", "headers", "software", "exposed_files", "directory_listing", "mixed_content", "cookies",
      "security_txt", "dnssec"]),
    ("online", {"en": ("Stays online", "Risk of going offline", "Staying online"),
                "bn": ("সাইট চালু থাকে", "সাইট বন্ধ হয়ে যাওয়ার ঝুঁকি", "সাইট চালু থাকা")},
     ["uptime", "domain_expiry", "dns"]),
    ("visitors", {"en": ("Easy for every visitor", "Some visitors will struggle", "Visitor experience"),
                  "bn": ("সব ভিজিটরের জন্য সহজ", "কিছু ভিজিটরের অসুবিধা হবে", "ভিজিটরের অভিজ্ঞতা")},
     ["accessibility", "image_alt", "contact_info", "page_basics"]),
]

PROBLEMS = {"en": ("{n} problem", "{n} problems", "{n} small improvement", "{n} small improvements", "All good",
                   "Not checked"),
            "bn": ("{n}টি সমস্যা", "{n}টি সমস্যা", "{n}টি ছোট উন্নতি", "{n}টি ছোট উন্নতি", "সব ঠিক আছে",
                   "পরীক্ষা করা হয়নি")}


def impact_groups(results: list[dict[str, Any]], lang: str = "en") -> list[dict[str, Any]]:
    """One summary per business outcome, from serialised results (each with key, severity, title)."""
    from .findings import bn_digits

    by_key = {r["key"]: r for r in results}
    one, many, note1, notes, good, unchecked = PROBLEMS.get(lang, PROBLEMS["en"])
    out = []
    for key, labels, checks in GROUPS:
        rs = [by_key[k] for k in checks if k in by_key]
        if not rs:
            continue
        errors = [r for r in rs if r["severity"] == "error"]
        warnings = [r for r in rs if r["severity"] == "warning"]
        small = [r for r in rs if r["severity"] == "notice"]
        checked = [r for r in rs if r["severity"] != "not_checked"]
        problems = errors + warnings
        status = "error" if errors else "warning" if warnings else "good" if checked else "not_checked"
        ok_label, bad_label, plain = labels.get(lang, labels["en"])
        n = len(problems)
        num = bn_digits(n) if lang == "bn" else n
        if problems:
            count = (one if n == 1 else many).format(n=num)
        elif small:
            m = bn_digits(len(small)) if lang == "bn" else len(small)
            count = (note1 if len(small) == 1 else notes).format(n=m)
        else:
            count = good if checked else unchecked
        out.append({
            "key": key, "status": status,
            "label": bad_label if problems else ok_label if checked else plain,
            "count": count, "problems": n, "notices": len(small),
            "top": [r["title"] for r in (errors + warnings)[:2]],
            "checks": [r["key"] for r in rs],
        })
    return out
