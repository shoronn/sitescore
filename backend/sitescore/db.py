"""Database engine, session factory and table definitions."""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from sqlalchemy import (
    JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

JSONType = JSON().with_variant(JSONB(), "postgresql")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Lead(Base):
    __tablename__ = "leads"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(120))
    business_name: Mapped[str | None] = mapped_column(String(160))
    phone: Mapped[str | None] = mapped_column(String(32))
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[str | None] = mapped_column(String(80))
    sales_status: Mapped[str] = mapped_column(String(20), default="new", index=True)
    sales_owner: Mapped[str | None] = mapped_column(String(120))
    callback_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    last_ip: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    scans: Mapped[list["Scan"]] = relationship(back_populates="lead")


class Site(Base):
    __tablename__ = "sites"
    id: Mapped[int] = mapped_column(primary_key=True)
    host: Mapped[str] = mapped_column(String(253), unique=True, index=True)
    apex: Mapped[str] = mapped_column(String(253), index=True)
    verify_token: Mapped[str] = mapped_column(String(48), default=lambda: secrets.token_hex(12))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Scan(Base):
    __tablename__ = "scans"
    id: Mapped[int] = mapped_column(primary_key=True)
    token: Mapped[str] = mapped_column(String(32), unique=True, index=True,
                                       default=lambda: secrets.token_urlsafe(16))
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"), index=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16), default="audit")  # audit | after_fix | monthly
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)  # queued|running|done|failed
    target: Mapped[str] = mapped_column(String(300))
    score: Mapped[int | None] = mapped_column(Integer)
    band: Mapped[str | None] = mapped_column(String(16))
    capped: Mapped[bool] = mapped_column(Boolean, default=False)
    coverage: Mapped[int | None] = mapped_column(Integer)
    # AI agent readiness, out of 100, scored separately from the health score.
    agent_score: Mapped[int | None] = mapped_column(Integer)
    # The visitor's language when they started the scan ("en" or "bn"): the report email and PDF use it.
    lang: Mapped[str] = mapped_column(String(5), default="en", server_default="en")
    error_code: Mapped[str | None] = mapped_column(String(32))
    error_message: Mapped[str | None] = mapped_column(String(300))
    engine_version: Mapped[str | None] = mapped_column(String(16))
    ip: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    emailed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Why the last attempt to email the report failed (cleared once it is sent).
    report_error: Mapped[str | None] = mapped_column(String(300))

    lead: Mapped[Lead] = relationship(back_populates="scans")
    site: Mapped[Site] = relationship()
    results: Mapped[list["CheckResultRow"]] = relationship(
        back_populates="scan", cascade="all, delete-orphan", order_by="CheckResultRow.position")


class CheckResultRow(Base):
    __tablename__ = "check_results"
    __table_args__ = (UniqueConstraint("scan_id", "check_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    scan_id: Mapped[int] = mapped_column(ForeignKey("scans.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    check_key: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(80))
    category: Mapped[str] = mapped_column(String(16))
    weight: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16))
    points: Mapped[float] = mapped_column(Float)
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(Text)
    why: Mapped[str] = mapped_column(Text)
    fix: Mapped[str] = mapped_column(Text)
    offer: Mapped[str] = mapped_column(String(24))
    critical: Mapped[bool] = mapped_column(Boolean, default=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    scan: Mapped[Scan] = relationship(back_populates="results")


class Staff(Base):
    """People who use the sales dashboard. Created from the command line, never by sign-up."""
    __tablename__ = "staff"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(16), default="sales")  # sales | admin
    password_hash: Mapped[str] = mapped_column(String(200))
    totp_secret: Mapped[str | None] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ---------------------------------------------------------------- engine/session

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def init_engine(url: str, **kwargs: Any) -> AsyncEngine:
    global _engine, _sessionmaker
    _engine = create_async_engine(url, pool_pre_ping=True, **kwargs)
    _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_engine() -> AsyncEngine:
    if _engine is None:
        from .config import get_settings
        init_engine(get_settings().database_url)
    return _engine  # type: ignore[return-value]


def sessionmaker() -> async_sessionmaker[AsyncSession]:
    get_engine()
    return _sessionmaker  # type: ignore[return-value]


async def create_tables() -> None:
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with sessionmaker()() as session:
        yield session


_ = func  # re-exported for queries elsewhere
