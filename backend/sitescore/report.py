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
from .engine.findings import nice_date
from .engine.models import CATEGORY_LABELS, HEALTH_CATEGORIES, Category

HERE = Path(__file__).parent
# Bright colours for icons, bars and the ring; "ink" colours for text, readable on white.
STATUS_COLOR = {"pass": "#34C759", "warn": "#F5B400", "fail": "#FF3B30", "not_checked": "#AEAEB2"}
STATUS_INK = {"pass": "#19753A", "warn": "#8F5300", "fail": "#CF0F20", "not_checked": "#55555C"}
STATUS_TINT = {"pass": "#E3F6E8", "warn": "#FDF1CC", "fail": "#FDE4E2", "not_checked": "#EFEFF4"}
STATUS_LABEL = {"pass": "Passed", "warn": "Could be better", "fail": "Needs fixing", "not_checked": "Not checked"}
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


def verdict(results: list[dict[str, Any]]) -> str:
    fails = sum(r["status"] == "fail" for r in results)
    warns = sum(r["status"] == "warn" for r in results)
    parts = []
    if fails:
        parts.append(f"{fails} {'problem needs' if fails == 1 else 'problems need'} fixing")
    if warns:
        parts.append(f"{warns} {'thing' if warns == 1 else 'things'} could be better")
    return (" and ".join(parts) + ".").capitalize() if parts else "Everything we checked looks good."


def score_tone(score: int | None) -> str | None:
    if score is None:
        return None
    return "pass" if score >= 80 else "warn" if score >= 50 else "fail"


def ring_svg(results: list[dict[str, Any]], score: int | None, band: str | None, label: str | None, size: int = 220) -> str:
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
    number = "" if score is None else str(score)
    color = BAND_INK.get(band or "", "#1D1D1F")
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" width="{size}" height="{size}">'
        f'<circle cx="100" cy="100" r="71" fill="#FAFAFC" stroke="#EFEFF4" stroke-width="1"/>' + "".join(paths) +
        f'<text x="100" y="114" text-anchor="middle" font-family="Inter Display, Inter, DejaVu Sans, sans-serif" '
        f'font-size="60" font-weight="700" letter-spacing="-2" fill="{color}">{number}</text>'
        f'<text x="100" y="138" text-anchor="middle" font-family="Inter, DejaVu Sans, sans-serif" '
        f'font-size="11" font-weight="600" fill="#55555C">{"out of 100" if score is not None else ""}</text></svg>'
    )


def qr_svg(url: str) -> str:
    qr = segno.make(url, error="m")
    return qr.svg_inline(scale=3, dark="#1D1D1F", light=None, border=1)


def report_context(data: dict[str, Any], settings: Settings) -> dict[str, Any]:
    everything = data["results"]
    results = [r for r in everything if r["category"] != Category.AGENT.value]
    agent_items = sorted((r for r in everything if r["category"] == Category.AGENT.value),
                         key=lambda r: AGENT_ORDER.get(r["key"], 99))
    agent = data.get("agent") or {}
    agent_tone = score_tone(agent.get("score"))
    groups = []
    for key, label in CATEGORY_ORDER:
        cat = next((c for c in data["categories"] if c["key"] == key), None)
        items = sorted((r for r in results if r["category"] == key),
                       key=lambda r: (STATUS_RANK[r["status"]], -r["weight"]))
        score = cat["score"] if cat else None
        tone = score_tone(score)
        groups.append({
            "key": key, "label": label, "score": score, "items": items,
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
        scanned = f"{nice_date(local.date().isoformat())} at {local.strftime('%I:%M %p').lstrip('0')} (Dhaka time)"
    except ValueError:
        scanned = nice_date(finished_iso)
    link = results_url(settings, data["token"])
    contact_url = (f"https://wa.me/{settings.whatsapp_number}" if settings.whatsapp_number else link)
    counts = {k: sum(r["status"] == k for r in results) for k in STATUS_LABEL}
    return {
        "host": data["host"],
        "date": nice_date(finished_iso),
        "scanned": scanned,
        "check_count": sum(1 for r in everything if r["weight"] > 0),  # llms.txt is information only
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
        "verdict": verdict(results),
        "ring": ring_svg(results, data["score"], data["band"], data["band_label"]),
        "top": top_issues(results),
        "groups": groups,
        "status_color": STATUS_COLOR,
        "status_ink": STATUS_INK,
        "status_tint": STATUS_TINT,
        "status_label": STATUS_LABEL,
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
        "price_bdt": f"Tk {settings.offer_price_bdt:,}",
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
    top = ctx["top"][:3]
    score = "not scored" if data["score"] is None else f"{data['score']}/100"
    agent = data.get("agent") or {}
    agent_text = "not scored" if agent.get("score") is None else f"{agent['score']}/100"
    lines = [f"Your SiteScore for {data['host']}", ""]
    if ctx["agent_items"]:
        lines.append(f"AI agent readiness: {agent_text} ({agent.get('label') or 'not checked'}).")
    lines += [f"Website health: {score} ({data['band_label'] or 'partial scan'}). {ctx['verdict']}", ""]
    if ctx["agent_issues"]:
        lines.append("To get ready for AI agents:")
        lines += [f"- {r['title']}" for r in ctx["agent_issues"][:3]]
        lines.append("")
    if top:
        lines.append("Health: fix these first:")
        lines += [f"- {r['title']}" for r in top]
        lines.append("")
    lines += [f"See every finding: {ctx['link']}", "", "The full report is attached as a PDF.", "",
              "Want us to fix these? Reply to this email or request a call on the results page.", "",
              f"MAKTECH, {settings.company_address}"]
    html = _env.get_template("report_email.html").render(**ctx, top3=top)
    filename = f"SiteScore-{data['host']}-{(data.get('finished_at') or '')[:10] or 'report'}.pdf"
    return mailer.Outgoing(
        to=to,
        subject=(f"{data['host']} on SiteScore: AI agent readiness {agent_text}, health {score}" if ctx["agent_items"]
                 else f"{data['host']} on SiteScore: health {score}"),
        text="\n".join(lines),
        html=html,
        attachments=[mailer.Attachment(filename, pdf)],
    )
