"""Data clean-up, run daily (Coolify scheduled task: python -m sitescore cleanup)."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import Settings
from .db import CheckResultRow, Lead, Scan, sessionmaker, utcnow


async def delete_leads(session: AsyncSession, lead_ids) -> int:
    """Delete leads with their scans and results; returns how many scans went. No commit.

    `lead_ids` is a list of ids or a select() of them. check_results go with their scans
    (ON DELETE CASCADE in Postgres); they are deleted explicitly too, for SQLite.
    """
    scan_ids = select(Scan.id).where(Scan.lead_id.in_(lead_ids))
    await session.execute(delete(CheckResultRow).where(CheckResultRow.scan_id.in_(scan_ids)))
    scans = (await session.execute(delete(Scan).where(Scan.lead_id.in_(lead_ids)))).rowcount
    await session.execute(delete(Lead).where(Lead.id.in_(lead_ids)))
    return scans


async def cleanup(settings: Settings) -> dict[str, int]:
    """Deletes leads (and their scans) past the retention period, unless they were won."""
    cutoff = utcnow() - timedelta(days=settings.lead_retention_days)
    async with sessionmaker()() as session:
        old = select(Lead.id).where(Lead.created_at < cutoff, Lead.updated_at < cutoff,
                                   Lead.sales_status != "won")
        old_ids = list((await session.execute(old)).scalars())
        scans = await delete_leads(session, old_ids) if old_ids else 0
        await session.commit()
    return {"leads": len(old_ids), "scans": scans}
