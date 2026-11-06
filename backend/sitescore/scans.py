"""Scan lifecycle: run a queued scan, store results as they arrive, rescore, serialise."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .config import Settings, engine_settings, get_settings
from .db import CheckResultRow, Scan, sessionmaker, utcnow
from .engine import ScanError, run_scan
from .engine.checks import CHECKS
from .engine.findings import LANGS, check_name, speed_fix_text, word
from .engine.impact import impact_groups, severity
from .engine.models import Category, CheckResult, Status
from .engine.scoring import agent_band, agent_level, agent_score, band_for, band_label, score_results

log = logging.getLogger("sitescore.scans")

ORDER = {c.key: i for i, c in enumerate(CHECKS)}


def row_from_result(scan_id: int, r: CheckResult) -> CheckResultRow:
    return CheckResultRow(
        scan_id=scan_id, position=ORDER.get(r.key, 99), check_key=r.key, name=r.name,
        category=r.category.value, weight=r.weight, status=r.status.value, points=r.points,
        title=r.title, summary=r.summary, why=r.why, fix=r.fix, offer=r.offer,
        critical=r.critical, evidence=r.evidence, duration_ms=r.duration_ms,
    )


def result_from_row(row: CheckResultRow) -> CheckResult:
    return CheckResult(
        key=row.check_key, name=row.name, category=Category(row.category), weight=row.weight,
        status=Status(row.status), points=row.points, title=row.title, summary=row.summary,
        why=row.why, fix=row.fix, offer=row.offer, critical=row.critical,
        evidence=row.evidence or {}, duration_ms=row.duration_ms,
    )


def apply_score(scan: Scan, rows: list[CheckResultRow]) -> None:
    results = [result_from_row(r) for r in rows]
    score, capped, cats = score_results(results)
    scan.score, scan.capped = score, capped
    scan.band = band_for(score)
    scan.coverage = sum(c.available for c in cats)
    scan.agent_score = agent_score(results)


def agent_json(score: int | None, lang: str = "en") -> dict[str, Any]:
    level, label = agent_level(score)
    if lang == "bn" and level:
        from .engine.findings_bn import AGENT_LABELS_BN

        label = AGENT_LABELS_BN.get(level, label)
    return {"score": score, "level": level, "label": label, "band": agent_band(score)}


def pick_lang(*choices: str | None) -> str:
    """The first supported language among the choices, else English."""
    return next((c for c in choices if c in LANGS), "en")


async def load_scan(session: AsyncSession, *, scan_id: int | None = None, token: str | None = None) -> Scan | None:
    q = select(Scan).options(selectinload(Scan.results), selectinload(Scan.site), selectinload(Scan.lead))
    q = q.where(Scan.id == scan_id) if scan_id is not None else q.where(Scan.token == token)
    return (await session.execute(q)).scalar_one_or_none()


async def run_scan_job(scan_id: int, settings: Settings | None = None) -> None:
    """Run one queued scan. Called by the RQ worker (or inline in development)."""
    settings = settings or get_settings()
    Session = sessionmaker()
    async with Session() as session:
        scan = await load_scan(session, scan_id=scan_id)
        if scan is None or scan.status not in ("queued", "running"):
            return
        scan.status, scan.started_at = "running", utcnow()
        await session.commit()
        target = scan.target

    lock = asyncio.Lock()

    async def store(result: CheckResult) -> None:
        async with lock, Session() as s:
            s.add(row_from_result(scan_id, result))
            await s.commit()

    try:
        report = await run_scan(target, settings=engine_settings(settings), on_result=store)
        error = None
    except ScanError as exc:
        report, error = None, exc
    except Exception as exc:  # noqa: BLE001
        log.exception("scan %s crashed", scan_id)
        report, error = None, ScanError("internal", "Something went wrong on our side. Please try again.")
        _ = exc

    async with Session() as session:
        scan = await load_scan(session, scan_id=scan_id)
        assert scan is not None
        scan.finished_at = utcnow()
        if error is not None:
            scan.status, scan.error_code, scan.error_message = "failed", error.code, error.message[:300]
        else:
            apply_score(scan, list(scan.results))
            scan.engine_version = report.engine_version
            scan.status = "done"
        await session.commit()
    if error is None:
        await after_scan_done(scan_id, settings)


async def after_scan_done(scan_id: int, settings: Settings) -> None:
    """Email the report the moment the scan is done (audits only, at most once)."""
    from .worker import schedule_report

    async with sessionmaker()() as session:
        scan = await load_scan(session, scan_id=scan_id)
        if scan is None or scan.kind != "audit" or scan.emailed_at is not None:
            return
    schedule_report(scan_id, 0, settings)


async def deliver_report(scan_id: int, settings: Settings | None = None) -> bool:
    """Build the PDF and email it. Sends at most once per scan, however often it is called."""
    from . import mailer
    from .report import render_pdf, report_email

    settings = settings or get_settings()
    Session = sessionmaker()
    async with Session() as session:
        claimed = await session.execute(
            update(Scan).where(Scan.id == scan_id, Scan.status == "done", Scan.emailed_at.is_(None))
            .values(emailed_at=utcnow()))
        await session.commit()
        if claimed.rowcount != 1:
            return False
        scan = await load_scan(session, scan_id=scan_id)
        data, to = serialize(scan, settings), scan.lead.email
    try:
        pdf = await asyncio.to_thread(render_pdf, data, settings)
        await mailer.send(settings, report_email(data, settings, to, pdf))
    except Exception as exc:
        log.exception("report for scan %s could not be sent to %s", scan_id, to)
        async with Session() as session:  # release the claim so a retry can send it
            await session.execute(update(Scan).where(Scan.id == scan_id)
                                  .values(emailed_at=None, report_error=describe_send_error(exc)))
            await session.commit()
        raise
    async with Session() as session:
        await session.execute(update(Scan).where(Scan.id == scan_id).values(report_error=None))
        await session.commit()
    log.info("report for scan %s emailed to %s", scan_id, to)
    return True


def describe_send_error(exc: Exception) -> str:
    """A short, staff-readable reason, stored with the scan and shown in the sales dashboard."""
    import aiosmtplib

    if isinstance(exc, aiosmtplib.SMTPAuthenticationError):
        text = "The mail server refused the SMTP username or password."
    elif isinstance(exc, (aiosmtplib.SMTPConnectError, aiosmtplib.SMTPServerDisconnected, ConnectionError, OSError)):
        text = f"Could not connect to the mail server ({type(exc).__name__}: {exc})."
    elif isinstance(exc, aiosmtplib.SMTPRecipientsRefused):
        text = "The mail server refused the visitor's email address."
    elif isinstance(exc, aiosmtplib.SMTPTimeoutError):
        text = "The mail server did not answer in time."
    else:
        text = f"{type(exc).__name__}: {exc}"
    return text[:300]


def report_status(scan: Scan) -> str:
    """'sent', 'failed' (last try failed, retries continue), 'pending', or 'none' for unfinished scans."""
    if scan.emailed_at is not None:
        return "sent"
    if scan.report_error:
        return "failed"
    return "pending" if scan.status == "done" and scan.kind == "audit" else "none"


async def resend_report(session: AsyncSession, scan: Scan, settings: Settings) -> None:
    """Send the report again (sales dashboard and CLI)."""
    from .worker import schedule_report

    scan.emailed_at = None
    scan.report_error = None
    await session.commit()
    schedule_report(scan.id, 0, settings)


def localise(r: CheckResult, lang: str, extra: dict[str, Any]) -> dict[str, str]:
    """The wording for one stored result in `lang`, rebuilt from its reason and evidence.

    Results store the English wording of the day; the reason code and evidence are enough
    to write it again in any language (and with any wording fixes made since).
    """
    reason = (r.evidence or {}).get("reason")
    if not reason:
        return {"name": r.name, "title": r.title, "summary": r.summary, "why": r.why, "fix": r.fix}
    text = word(r.key, r.name, r.status.value, reason, r.evidence, extra, lang)
    return {"name": check_name(r.key, r.name, lang), "title": text["title"], "summary": text["summary"],
            "why": text["why"], "fix": text["fix"]}


# Big or internal evidence the web app does not need.
HIDDEN_EVIDENCE = ("error", "screenshot", "fixes")


def serialize(scan: Scan, settings: Settings | None = None, lang: str | None = None) -> dict[str, Any]:
    lang = pick_lang(lang, scan.lang)
    # Only checks that still exist: older scans also hold results of retired checks (the
    # backup question), which must not show up or count in the area scores.
    rows = sorted((r for r in scan.results if r.check_key in ORDER), key=lambda r: r.position)
    results = [result_from_row(r) for r in rows]
    _, _, cats = score_results(results)
    extra = {"host": scan.site.host, "apex": scan.site.apex}
    if lang == "bn":
        from .engine.findings_bn import BAND_LABELS_BN, CATEGORY_LABELS_BN
    items = []
    speed = next((r for r in results if r.key == "mobile_speed"), None)
    for r in results:
        text = localise(r, lang, extra)
        items.append({
            "key": r.key, "name": text["name"], "category": r.category.value, "weight": r.weight,
            "status": r.status.value, "severity": severity(r.key, r.status.value, (r.evidence or {}).get("reason", ""), r.weight),
            "points": r.points, "title": text["title"], "summary": text["summary"],
            "why": text["why"], "fix": text["fix"], "offer": r.offer, "critical": r.critical,
            "evidence": {k: v for k, v in r.evidence.items() if k not in HIDDEN_EVIDENCE}})
    out: dict[str, Any] = {
        "lang": lang,
        "token": scan.token,
        "status": scan.status,
        "host": scan.site.host,
        "target": scan.target,
        "created_at": scan.created_at.isoformat() if scan.created_at else None,
        "finished_at": scan.finished_at.isoformat() if scan.finished_at else None,
        "progress": {"done": len(rows), "total": len(CHECKS)},
        "score": scan.score,
        "band": scan.band,
        "band_label": (BAND_LABELS_BN.get(scan.band or "") if lang == "bn" else None) or band_label(scan.band),
        "capped": scan.capped,
        "coverage": scan.coverage,
        "agent": agent_json(scan.agent_score, lang),
        "categories": [
            {"key": c.category.value,
             "label": CATEGORY_LABELS_BN.get(c.category.value, c.label) if lang == "bn" else c.label,
             "score": c.score, "earned": c.earned, "available": c.available}
            for c in cats
        ],
        "results": items,
        "impact": impact_groups(items, lang) if items else [],
        # What would make the homepage load faster, and how it looked on the test phone.
        "speed_fixes": speed_fix_text((speed.evidence or {}).get("fixes", []), lang) if speed else [],
        "screenshot": (speed.evidence or {}).get("screenshot") if speed else None,
        "pending": [c.key for c in CHECKS if c.key not in {r.key for r in results}],
    }
    out["report_emailed"] = scan.emailed_at is not None
    out["report_status"] = report_status(scan)
    if scan.status == "failed":
        message = scan.error_message
        if lang == "bn":
            from .messages_bn import to_bangla

            message = to_bangla(message)
        out["error"] = {"code": scan.error_code, "message": message}
    return out


def now() -> datetime:
    return datetime.now(timezone.utc)
