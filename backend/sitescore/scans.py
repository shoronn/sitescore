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


def agent_json(score: int | None) -> dict[str, Any]:
    level, label = agent_level(score)
    return {"score": score, "level": level, "label": label, "band": agent_band(score)}


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


def serialize(scan: Scan, settings: Settings | None = None) -> dict[str, Any]:
    # Only checks that still exist: older scans also hold results of retired checks (the
    # backup question), which must not show up or count in the area scores.
    rows = sorted((r for r in scan.results if r.check_key in ORDER), key=lambda r: r.position)
    results = [result_from_row(r) for r in rows]
    _, _, cats = score_results(results)
    out: dict[str, Any] = {
        "token": scan.token,
        "status": scan.status,
        "host": scan.site.host,
        "target": scan.target,
        "created_at": scan.created_at.isoformat() if scan.created_at else None,
        "finished_at": scan.finished_at.isoformat() if scan.finished_at else None,
        "progress": {"done": len(rows), "total": len(CHECKS)},
        "score": scan.score,
        "band": scan.band,
        "band_label": band_label(scan.band),
        "capped": scan.capped,
        "coverage": scan.coverage,
        "agent": agent_json(scan.agent_score),
        "categories": [
            {"key": c.category.value, "label": c.label, "score": c.score,
             "earned": c.earned, "available": c.available}
            for c in cats
        ],
        "results": [
            {"key": r.key, "name": r.name, "category": r.category.value, "weight": r.weight,
             "status": r.status.value, "points": r.points, "title": r.title, "summary": r.summary,
             "why": r.why, "fix": r.fix, "offer": r.offer, "critical": r.critical,
             "evidence": {k: v for k, v in r.evidence.items() if k not in ("error",)}}
            for r in results
        ],
        "pending": [c.key for c in CHECKS if c.key not in {r.key for r in results}],
    }
    out["report_emailed"] = scan.emailed_at is not None
    out["report_status"] = report_status(scan)
    if scan.status == "failed":
        out["error"] = {"code": scan.error_code, "message": scan.error_message}
    return out


def now() -> datetime:
    return datetime.now(timezone.utc)
