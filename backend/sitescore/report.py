"""Branded PDF report and the results email."""
from __future__ import annotations

import base64
import math
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import segno
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .config import Settings
from .engine.checks import AGENT_KEYS, CHECKS
from .engine.findings import bn_digits, nice_date
from .engine.models import CATEGORY_LABELS, HEALTH_CATEGORIES, Category

HERE = Path(__file__).parent
# Bright colours for icons, bars and the ring; "ink" colours for text, readable on white.
STATUS_COLOR = {"pass": "#34C759", "warn": "#F5B400", "fail": "#FF3B30", "not_checked": "#AEAEB2"}
STATUS_INK = {"pass": "#19753A", "warn": "#8F5300", "fail": "#CF0F20", "not_checked": "#55555C"}
STATUS_TINT = {"pass": "#E3F6E8", "warn": "#FDF1CC", "fail": "#FDE4E2", "not_checked": "#EFEFF4"}
STATUS_LABEL = {"pass": "Passed", "warn": "Could be better", "fail": "Needs fixing", "not_checked": "Not checked"}
SEVERITY_STATUS = {"error": "fail", "warning": "warn", "notice": "warn", "good": "pass", "not_checked": "not_checked"}

# Every fixed phrase in the PDF and the email, in English and Bangla.
TEXT: dict[str, dict[str, str]] = {
    "en": {
        "html_lang": "en", "title": "SiteScore report for {host}", "running_head": "SiteScore report",
        "page": "Page", "of": "of", "by": "by MAKTECH", "report_name": "AI readiness and health report",
        "website": "Website", "scanned": "Scanned {when}. {n} checks.", "agent": "AI agent readiness",
        "health": "Website health", "not_checked": "Not checked", "out_of": "out of 100",
        "coverage": "The score covers the {n} of 100 points we could check.",
        "capped": "Held below 50 because of a serious problem.",
        "impact": "What this means for your business", "by_area": "Health by area",
        "passed_of": "{a} of {b} passed", "fix_first": "Health: fix these first", "what_we_do": "What we do:",
        "nothing_urgent": "Nothing urgent",
        "nothing_urgent_text": "Every check we could run passed. Keep it that way with regular updates, backups and monitoring.",
        "phone_view": "Your homepage on a phone", "phone_caption": "As our test phone saw it",
        "speed_fixes": "Top speed fixes", "speed_fixes_text": "The changes that would save the most loading time.",
        "good": "What is already good", "every": "Every check",
        "every_text": "What we saw, why it matters and how it gets fixed. Problems come first in each area.",
        "optional": "Optional, not scored", "why": "Why it matters:", "how": "How MAKTECH fixes it:",
        "next": "Next step", "want_fix": "Want us to fix these?",
        "offer": "With the Fix-It Starter Pack, our engineers make your site ready for AI agents, fix your top 5 health issues, move your site to a MAKTECH server and give you the first month of CloudCare hosting free.",
        "one_time": "one time", "keep": "Keep it this way",
        "keep_text": "CloudCare by MAKTECH monitors your site around the clock, patches it every month and keeps daily off-site backups.",
        "call_page": "Request a call on your results page: {link}", "call_wa": "Call or WhatsApp us on {phone}, or scan the code",
        "call": "Call us on {phone}", "wa": "WhatsApp us on {phone}, or scan the code", "email": "Email {email}",
        "qr_wa": "Chat on WhatsApp", "qr_results": "Open your results",
        "read": "How to read this report", "key_error": "Needs fixing: a real risk or a broken setting",
        "key_warning": "Could be better: worth improving", "key_notice": "Small improvement: nice to have",
        "key_pass": "Passed", "key_nc": "Not checked: left out of the score", "scores": "How the scores work",
        "scores_agent": "AI agent readiness: six checks share 100 points, based on open standards that AI assistants and agents use to find and read sites. llms.txt is shown but not scored.",
        "scores_health": "Website health: each check is worth a share of 100 points, with more for the checks that matter most. A serious problem, such as an exposed password file, holds the score below 50.",
        "scores_public": "SiteScore checks only public information. It is guidance, not a full security audit.",
        "live": "Live results:", "dhaka": "{date} at {time} (Dhaka time)",
        "sev_error": "Needs fixing", "sev_warning": "Could be better", "sev_notice": "Small improvement",
        "sev_good": "Passed", "sev_not_checked": "Not checked",
        "verdict_fail_1": "{n} problem needs fixing", "verdict_fail_n": "{n} problems need fixing",
        "verdict_warn_1": "{n} thing could be better", "verdict_warn_n": "{n} things could be better",
        "verdict_and": " and ", "verdict_ok": "Everything we checked looks good.",
        "not_scored": "not scored", "partial": "partial scan",
        "mail_title": "Your SiteScore for {host}", "mail_agent": "AI agent readiness: {score} ({label}).",
        "mail_health": "Website health: {score} ({band}). {verdict}", "mail_agent_fix": "To get ready for AI agents:",
        "mail_fix_first": "Health: fix these first:", "mail_see": "See every finding: {link}",
        "mail_attached": "The full report is attached as a PDF.",
        "mail_reply": "Want us to fix these? Reply to this email or request a call on the results page.",
        "mail_subject_agent": "{host} on SiteScore: AI agent readiness {agent}, health {score}",
        "mail_subject": "{host} on SiteScore: health {score}",
        "mail_hello": "Here is your SiteScore", "mail_open": "Open your full results", "mail_pdf": "The full PDF report is attached.",
        "mail_questions": "Questions? Reply to this email.",
    },
    "bn": {
        "html_lang": "bn", "title": "{host}-এর SiteScore রিপোর্ট", "running_head": "SiteScore রিপোর্ট",
        "page": "পৃষ্ঠা", "of": "এর", "by": "by MAKTECH", "report_name": "AI প্রস্তুতি আর ওয়েবসাইটের স্বাস্থ্য রিপোর্ট",
        "website": "ওয়েবসাইট", "scanned": "পরীক্ষার সময়: {when}। {n}টি পরীক্ষা।", "agent": "AI এজেন্ট প্রস্তুতি",
        "health": "ওয়েবসাইটের স্বাস্থ্য", "not_checked": "পরীক্ষা করা হয়নি", "out_of": "১০০-এর মধ্যে",
        "coverage": "যে {n} পয়েন্ট আমরা পরীক্ষা করতে পেরেছি (১০০-এর মধ্যে), স্কোর সেগুলোর ভিত্তিতে।",
        "capped": "একটি গুরুতর সমস্যার কারণে স্কোর ৫০-এর নিচে রাখা হয়েছে।",
        "impact": "আপনার ব্যবসার জন্য এর মানে কী", "by_area": "বিভাগ অনুযায়ী স্বাস্থ্য",
        "passed_of": "{b}টির মধ্যে {a}টি পাস", "fix_first": "স্বাস্থ্য: আগে এগুলো ঠিক করুন", "what_we_do": "আমরা যা করব:",
        "nothing_urgent": "জরুরি কিছু নেই",
        "nothing_urgent_text": "আমরা যা পরীক্ষা করতে পেরেছি তার সবই পাস করেছে। নিয়মিত আপডেট, ব্যাকআপ আর নজরদারি দিয়ে এভাবেই রাখুন।",
        "phone_view": "ফোনে আপনার হোমপেজ", "phone_caption": "আমাদের টেস্ট ফোনে যেমন দেখা গেছে",
        "speed_fixes": "গতি বাড়ানোর প্রধান উপায়", "speed_fixes_text": "যে পরিবর্তনগুলো লোড হওয়ার সময় সবচেয়ে বেশি বাঁচাবে।",
        "good": "যা ইতিমধ্যে ভালো আছে", "every": "সব পরীক্ষা",
        "every_text": "আমরা কী দেখেছি, কেন তা গুরুত্বপূর্ণ আর কীভাবে ঠিক হবে। প্রতিটি বিভাগে সমস্যাগুলো আগে।",
        "optional": "ঐচ্ছিক, স্কোরে গোনা হয় না", "why": "কেন গুরুত্বপূর্ণ:", "how": "MAKTECH যেভাবে ঠিক করে:",
        "next": "পরের ধাপ", "want_fix": "আমরা কি এগুলো ঠিক করে দেব?",
        "offer": "Fix-It Starter Pack-এ আমাদের ইঞ্জিনিয়াররা আপনার সাইটকে AI এজেন্টের জন্য প্রস্তুত করবেন, স্বাস্থ্যের প্রধান ৫টি সমস্যা ঠিক করবেন, সাইটটি MAKTECH সার্ভারে সরিয়ে নেবেন এবং প্রথম মাসের CloudCare হোস্টিং ফ্রি দেবেন।",
        "one_time": "এককালীন", "keep": "এভাবেই রাখুন",
        "keep_text": "MAKTECH-এর CloudCare চব্বিশ ঘণ্টা আপনার সাইট নজরে রাখে, প্রতি মাসে আপডেট দেয় আর প্রতিদিন অন্য জায়গায় ব্যাকআপ রাখে।",
        "call_page": "আপনার রেজাল্ট পেজ থেকে কলের অনুরোধ করুন: {link}", "call_wa": "{phone} নম্বরে কল বা WhatsApp করুন, অথবা কোডটি স্ক্যান করুন",
        "call": "{phone} নম্বরে কল করুন", "wa": "{phone} নম্বরে WhatsApp করুন, অথবা কোডটি স্ক্যান করুন", "email": "ইমেইল: {email}",
        "qr_wa": "WhatsApp-এ চ্যাট করুন", "qr_results": "আপনার রেজাল্ট খুলুন",
        "read": "এই রিপোর্ট কীভাবে পড়বেন", "key_error": "ঠিক করা দরকার: আসল ঝুঁকি বা নষ্ট সেটিং",
        "key_warning": "আরও ভালো হতে পারে: উন্নতি করার মতো", "key_notice": "ছোট উন্নতি: থাকলে ভালো",
        "key_pass": "পাস", "key_nc": "পরীক্ষা করা হয়নি: স্কোরে ধরা হয়নি", "scores": "স্কোর কীভাবে হিসাব হয়",
        "scores_agent": "AI এজেন্ট প্রস্তুতি: ছয়টি পরীক্ষা মিলে ১০০ পয়েন্ট, সেই উন্মুক্ত মানদণ্ডের ভিত্তিতে যা দিয়ে AI অ্যাসিস্ট্যান্ট আর এজেন্টরা সাইট খুঁজে পড়ে। llms.txt দেখানো হয়, কিন্তু স্কোরে গোনা হয় না।",
        "scores_health": "ওয়েবসাইটের স্বাস্থ্য: প্রতিটি পরীক্ষার ১০০ পয়েন্টে একটি ভাগ আছে, যেটি বেশি গুরুত্বপূর্ণ তার ভাগ বেশি। খোলা পাসওয়ার্ড ফাইলের মতো গুরুতর সমস্যা থাকলে স্কোর ৫০-এর নিচে থাকে।",
        "scores_public": "SiteScore শুধু পাবলিক তথ্য পরীক্ষা করে। এটি একটি নির্দেশনা, পূর্ণাঙ্গ নিরাপত্তা নিরীক্ষা নয়।",
        "live": "লাইভ রেজাল্ট:", "dhaka": "{date}, {time} (ঢাকার সময়)",
        "sev_error": "ঠিক করা দরকার", "sev_warning": "আরও ভালো হতে পারে", "sev_notice": "ছোট উন্নতি",
        "sev_good": "পাস", "sev_not_checked": "পরীক্ষা করা হয়নি",
        "verdict_fail_1": "{n}টি সমস্যা ঠিক করা দরকার", "verdict_fail_n": "{n}টি সমস্যা ঠিক করা দরকার",
        "verdict_warn_1": "{n}টি বিষয় আরও ভালো হতে পারে", "verdict_warn_n": "{n}টি বিষয় আরও ভালো হতে পারে",
        "verdict_and": ", আর ", "verdict_ok": "আমরা যা পরীক্ষা করেছি তার সবই ভালো দেখাচ্ছে।",
        "not_scored": "স্কোর হয়নি", "partial": "আংশিক পরীক্ষা",
        "mail_title": "{host}-এর SiteScore", "mail_agent": "AI এজেন্ট প্রস্তুতি: {score} ({label})।",
        "mail_health": "ওয়েবসাইটের স্বাস্থ্য: {score} ({band})। {verdict}", "mail_agent_fix": "AI এজেন্টের জন্য প্রস্তুত হতে:",
        "mail_fix_first": "স্বাস্থ্য: আগে এগুলো ঠিক করুন:", "mail_see": "সব ফলাফল দেখুন: {link}",
        "mail_attached": "পুরো রিপোর্ট PDF হিসেবে সংযুক্ত আছে।",
        "mail_reply": "আমরা কি এগুলো ঠিক করে দেব? এই ইমেইলের উত্তর দিন অথবা রেজাল্ট পেজ থেকে কলের অনুরোধ করুন।",
        "mail_subject_agent": "SiteScore-এ {host}: AI এজেন্ট প্রস্তুতি {agent}, স্বাস্থ্য {score}",
        "mail_subject": "SiteScore-এ {host}: স্বাস্থ্য {score}",
        "mail_hello": "এই হলো আপনার SiteScore", "mail_open": "পুরো রেজাল্ট খুলুন", "mail_pdf": "পুরো PDF রিপোর্ট সংযুক্ত আছে।",
        "mail_questions": "কোনো প্রশ্ন? এই ইমেইলের উত্তর দিন।",
    },
}
BAND_COLOR = {"good": "#34C759", "attention": "#F5B400", "risk": "#FF3B30"}
BAND_INK = {"good": "#19753A", "attention": "#8F5300", "risk": "#CF0F20"}
BAND_TINT = {"good": "#E3F6E8", "attention": "#FDF1CC", "risk": "#FDE4E2"}
# Same areas, labels and order as the engine (health areas; AI agent readiness is separate).
CATEGORY_ORDER = [(c.value, CATEGORY_LABELS[c]) for c in HEALTH_CATEGORIES]
HEALTH_CHECKS = [c for c in CHECKS if c.key not in AGENT_KEYS]
AGENT_ORDER = {k: i for i, k in enumerate(AGENT_KEYS)}
STATUS_RANK = {"fail": 0, "warn": 1, "pass": 2, "not_checked": 3}
DHAKA = timezone(timedelta(hours=6))  # Bangladesh has no daylight saving time

_env = Environment(loader=FileSystemLoader(HERE / "templates"), autoescape=select_autoescape(["html"]))


@lru_cache
def logo_data_uri() -> str:
    return "data:image/png;base64," + base64.b64encode((HERE / "assets" / "logo.png").read_bytes()).decode()


def pretty_phone(digits: str | None) -> str | None:
    """8801897669234 -> +880 1897 669234 (Bangladesh mobiles); other numbers -> +digits."""
    if not digits:
        return None
    d = "".join(ch for ch in digits if ch.isdigit())
    if d.startswith("880") and len(d) == 13:
        return f"+880 {d[3:7]} {d[7:]}"
    return f"+{d}"


def results_url(settings: Settings, token: str) -> str:
    return f"{settings.public_base_url.rstrip('/')}/scan/{token}"


def top_issues(results: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    issues = [r for r in results if r["status"] in ("fail", "warn")]
    issues.sort(key=lambda r: (not r["critical"], STATUS_RANK[r["status"]], -r["weight"]))
    return issues[:limit]


def verdict(results: list[dict[str, Any]], lang: str = "en") -> str:
    t = TEXT.get(lang, TEXT["en"])
    num = bn_digits if lang == "bn" else str
    fails = sum(r["status"] == "fail" for r in results)
    warns = sum(r["status"] == "warn" for r in results)
    parts = []
    if fails:
        parts.append(t["verdict_fail_1" if fails == 1 else "verdict_fail_n"].format(n=num(fails)))
    if warns:
        parts.append(t["verdict_warn_1" if warns == 1 else "verdict_warn_n"].format(n=num(warns)))
    if not parts:
        return t["verdict_ok"]
    text = t["verdict_and"].join(parts) + ("।" if lang == "bn" else ".")
    return text[0].upper() + text[1:]


def score_tone(score: int | None) -> str | None:
    if score is None:
        return None
    return "pass" if score >= 80 else "warn" if score >= 50 else "fail"


def ring_svg(results: list[dict[str, Any]], score: int | None, band: str | None, label: str | None, size: int = 220,
             lang: str = "en") -> str:
    """The same ring as the web app (one segment per health check), as inline SVG."""
    by_key = {r["key"]: r["status"] for r in results}
    n, r, c = len(HEALTH_CHECKS), 84, 100
    stroke, gap_units = (8, 3.5) if n > 16 else (10, 5)
    gap = math.degrees((stroke + gap_units) / r)  # keeps round caps from touching
    step = 360 / n
    paths = []
    for i, ch in enumerate(HEALTH_CHECKS):
        a0, a1 = math.radians(i * step + gap / 2 - 90), math.radians((i + 1) * step - gap / 2 - 90)
        x1, y1 = c + r * math.cos(a0), c + r * math.sin(a0)
        x2, y2 = c + r * math.cos(a1), c + r * math.sin(a1)
        color = STATUS_COLOR.get(by_key.get(ch.key, ""), "#E5E5EA")
        paths.append(f'<path d="M {x1:.3f} {y1:.3f} A {r} {r} 0 0 1 {x2:.3f} {y2:.3f}" fill="none" '
                     f'stroke="{color}" stroke-width="{stroke}" stroke-linecap="round"/>')
    number = "" if score is None else (bn_digits(score) if lang == "bn" else str(score))
    out_of = TEXT.get(lang, TEXT["en"])["out_of"] if score is not None else ""
    color = BAND_INK.get(band or "", "#1D1D1F")
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" width="{size}" height="{size}">'
        f'<circle cx="100" cy="100" r="71" fill="#FAFAFC" stroke="#EFEFF4" stroke-width="1"/>' + "".join(paths) +
        f'<text x="100" y="114" text-anchor="middle" font-family="Inter Display, Inter, Noto Sans Bengali, DejaVu Sans, sans-serif" '
        f'font-size="60" font-weight="700" letter-spacing="-2" fill="{color}">{number}</text>'
        f'<text x="100" y="138" text-anchor="middle" font-family="Inter, Noto Sans Bengali, DejaVu Sans, sans-serif" '
        f'font-size="11" font-weight="600" fill="#55555C">{out_of}</text></svg>'
    )


def qr_svg(url: str) -> str:
    qr = segno.make(url, error="m")
    return qr.svg_inline(scale=3, dark="#1D1D1F", light=None, border=1)


def _num(value: Any, lang: str = "en") -> str:
    return bn_digits(value) if lang == "bn" else str(value)


_env.filters["num"] = _num


def _clock(local: datetime, lang: str) -> str:
    """3:45 PM, or বিকেল ৩:৪৫ in Bangla."""
    if lang != "bn":
        return local.strftime("%I:%M %p").lstrip("0")
    h = local.hour
    part = ("রাত" if h < 4 or h >= 20 else "ভোর" if h < 6 else "সকাল" if h < 12 else "দুপুর" if h < 15
            else "বিকেল" if h < 18 else "সন্ধ্যা")
    return f"{part} {bn_digits(local.strftime('%I:%M').lstrip('0'))}"


def report_context(data: dict[str, Any], settings: Settings) -> dict[str, Any]:
    lang = data.get("lang") if data.get("lang") in TEXT else "en"
    t = TEXT[lang]
    everything = data["results"]
    results = [r for r in everything if r["category"] != Category.AGENT.value]
    agent_items = sorted((r for r in everything if r["category"] == Category.AGENT.value),
                         key=lambda r: AGENT_ORDER.get(r["key"], 99))
    agent = data.get("agent") or {}
    agent_tone = score_tone(agent.get("score"))
    labels = {c["key"]: c["label"] for c in data["categories"]}
    groups = []
    for key, label in CATEGORY_ORDER:
        cat = next((c for c in data["categories"] if c["key"] == key), None)
        items = sorted((r for r in results if r["category"] == key),
                       key=lambda r: (STATUS_RANK[r["status"]], -r["weight"]))
        score = cat["score"] if cat else None
        tone = score_tone(score)
        groups.append({
            "key": key, "label": labels.get(key, label), "score": score, "items": items,
            "passed": sum(r["status"] == "pass" for r in items),
            "color": STATUS_COLOR[tone] if tone else "#D1D1D6",
            "ink": STATUS_INK[tone] if tone else "#55555C",
        })
    finished_iso = data.get("finished_at") or datetime.now(timezone.utc).isoformat()
    try:
        finished = datetime.fromisoformat(finished_iso)
        if finished.tzinfo is None:
            finished = finished.replace(tzinfo=timezone.utc)
        local = finished.astimezone(DHAKA)
        scanned = t["dhaka"].format(date=nice_date(local.date().isoformat(), lang), time=_clock(local, lang))
    except ValueError:
        scanned = nice_date(finished_iso, lang)
    link = results_url(settings, data["token"])
    if lang != "en":
        link += f"?lang={lang}"
    contact_url = (f"https://wa.me/{settings.whatsapp_number}" if settings.whatsapp_number else link)
    counts = {k: sum(r["status"] == k for r in results) for k in STATUS_LABEL}
    check_count = sum(1 for r in everything if r["weight"] > 0)  # llms.txt is information only
    sev_label = {k: t[f"sev_{k}"] for k in ("error", "warning", "notice", "good", "not_checked")}
    return {
        "lang": lang,
        "t": t,
        "host": data["host"],
        "date": nice_date(finished_iso, lang),
        "scanned": t["scanned"].format(when=scanned, n=_num(check_count, lang)),
        "check_count": check_count,
        "agent": agent,
        "agent_items": agent_items,
        "agent_scored": [r for r in agent_items if r["weight"] > 0],
        "agent_info": [r for r in agent_items if r["weight"] == 0],
        "agent_ink": STATUS_INK[agent_tone] if agent_tone else "#55555C",
        "agent_color": STATUS_COLOR[agent_tone] if agent_tone else "#D1D1D6",
        "agent_tint": STATUS_TINT[agent_tone] if agent_tone else "#EFEFF4",
        "agent_issues": [r for r in agent_items if r["weight"] > 0 and r["status"] in ("fail", "warn")],
        "counts": counts,
        "score": data["score"],
        "band": data["band"],
        "band_label": data["band_label"],
        "capped": data["capped"],
        "coverage": data["coverage"],
        "verdict": verdict(results, lang),
        "ring": ring_svg(results, data["score"], data["band"], data["band_label"], lang=lang),
        "top": top_issues(results),
        "groups": groups,
        "impact": data.get("impact") or [],
        "speed_fixes": data.get("speed_fixes") or [],
        "screenshot": data.get("screenshot"),
        "good": [r for r in everything if r["status"] == "pass" and r["weight"] > 0],
        "status_color": STATUS_COLOR,
        "status_ink": STATUS_INK,
        "status_tint": STATUS_TINT,
        "status_label": {k: t[f"sev_{v}"] for k, v in
                         {"pass": "good", "warn": "warning", "fail": "error", "not_checked": "not_checked"}.items()},
        "sev_label": sev_label,
        "sev_status": SEVERITY_STATUS,
        "band_color": BAND_COLOR,
        "band_ink": BAND_INK,
        "band_tint": BAND_TINT,
        "logo": logo_data_uri(),
        "logo_url": f"{settings.public_base_url.rstrip('/')}/logo.png",
        "link": link,
        "link_short": link.split("://", 1)[-1],
        "contact_qr": qr_svg(contact_url),
        "contact_is_whatsapp": bool(settings.whatsapp_number),
        "whatsapp": settings.whatsapp_number,
        "whatsapp_pretty": pretty_phone(settings.whatsapp_number),
        "phone_pretty": pretty_phone(settings.contact_phone),
        "has_issues": any(r["status"] in ("fail", "warn") and r["weight"] > 0 for r in everything),
        "price_usd": f"${settings.offer_price_usd:,}",
        "price_bdt": f"Tk {settings.offer_price_bdt:,}" if lang == "en" else f"৳{bn_digits(f'{settings.offer_price_bdt:,}')}",
        "company_address": settings.company_address,
        "contact_email": settings.mail_from.split("<")[-1].rstrip(">").strip(),
    }


def render_pdf(data: dict[str, Any], settings: Settings) -> bytes:
    from weasyprint import HTML  # heavy import, only where needed

    html = _env.get_template("report.html").render(**report_context(data, settings))
    return HTML(string=html, base_url=str(HERE)).write_pdf()


def report_email(data: dict[str, Any], settings: Settings, to: str, pdf: bytes):
    from . import mailer

    ctx = report_context(data, settings)
    t, lang = ctx["t"], ctx["lang"]
    top = ctx["top"][:3]
    score = t["not_scored"] if data["score"] is None else f"{_num(data['score'], lang)}/{_num(100, lang)}"
    agent = data.get("agent") or {}
    agent_text = t["not_scored"] if agent.get("score") is None else f"{_num(agent['score'], lang)}/{_num(100, lang)}"
    lines = [t["mail_title"].format(host=data["host"]), ""]
    if ctx["agent_items"]:
        lines.append(t["mail_agent"].format(score=agent_text, label=agent.get("label") or t["not_checked"]))
    lines += [t["mail_health"].format(score=score, band=data["band_label"] or t["partial"], verdict=ctx["verdict"]), ""]
    if ctx["agent_issues"]:
        lines.append(t["mail_agent_fix"])
        lines += [f"- {r['title']}" for r in ctx["agent_issues"][:3]]
        lines.append("")
    if top:
        lines.append(t["mail_fix_first"])
        lines += [f"- {r['title']}" for r in top]
        lines.append("")
    lines += [t["mail_see"].format(link=ctx["link"]), "", t["mail_attached"], "", t["mail_reply"], "",
              f"MAKTECH, {settings.company_address}"]
    html = _env.get_template("report_email.html").render(**ctx, top3=top, score_text=score, agent_text=agent_text)
    filename = f"SiteScore-{data['host']}-{(data.get('finished_at') or '')[:10] or 'report'}.pdf"
    return mailer.Outgoing(
        to=to,
        subject=(t["mail_subject_agent"].format(host=data["host"], agent=agent_text, score=score) if ctx["agent_items"]
                 else t["mail_subject"].format(host=data["host"], score=score)),
        text="\n".join(lines),
        html=html,
        attachments=[mailer.Attachment(filename, pdf)],
    )
