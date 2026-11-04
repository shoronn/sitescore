"""Sales dashboard API under /api/admin. Staff only: password plus authenticator code."""
from __future__ import annotations

import csv
import io
import logging
from datetime import timedelta
from typing import Annotated, Any, Literal

import segno
from fastapi import APIRouter, Depends, Query, Request, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .config import Settings, get_settings
from .db import Lead, Scan, Site, Staff, get_session, utcnow
from .ratelimit import RateLimiter
from .maintenance import delete_leads
from .scans import report_status, resend_report
from .staff_auth import hash_password, new_totp_secret, otpauth_uri, verify_password, verify_totp

# Compared against when the email is unknown, so sign-in takes the same time either way.
_DUMMY_HASH = hash_password("not-a-real-password-just-for-timing")


def speed_error(scan: Scan) -> str | None:
    """Why the speed test did not give a result, for staff (visitors see plain wording)."""
    row = next((r for r in scan.results if r.check_key == "mobile_speed"), None)
    if row is None or row.status != "not_checked":
        return None
    ev = row.evidence or {}
    return f"{ev.get('error') or ev.get('reason') or 'unknown'} {ev.get('detail') or ''}".strip()[:300]


def csv_safe(value: Any) -> str:
    """Stop spreadsheet formula injection: a cell starting with = + - @ is shown as text."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text

SALES_STATUSES = ("new", "contacted", "interested", "won", "lost")

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
log = logging.getLogger("sitescore.admin")


def _api_error(status: int, code: str, message: str, **extra: Any):
    from .api import ApiError

    return ApiError(status, code, message, **extra)


def _signer(settings: Settings, salt: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.secret_key, salt=salt)


async def current_staff(request: Request, session: SessionDep, settings: SettingsDep) -> Staff:
    token = request.cookies.get(settings.staff_cookie_name)
    staff_id = None
    if token:
        try:
            data = _signer(settings, "sitescore-staff").loads(token, max_age=settings.staff_session_hours * 3600)
            staff_id = data.get("staff") if isinstance(data, dict) else None
        except (BadSignature, SignatureExpired):
            staff_id = None
    staff = await session.get(Staff, staff_id) if isinstance(staff_id, int) else None
    if staff is None or not staff.is_active or not staff.totp_secret:
        raise _api_error(401, "not_signed_in", "Please sign in.")
    return staff


StaffDep = Annotated[Staff, Depends(current_staff)]


def _client_ip(request: Request, settings: SettingsDep) -> str:
    from .api import client_ip

    return client_ip(request, settings)


IpDep = Annotated[str, Depends(_client_ip)]


def _set_staff_cookie(response: Response, settings: Settings, staff: Staff) -> None:
    response.set_cookie(
        settings.staff_cookie_name, _signer(settings, "sitescore-staff").dumps({"staff": staff.id}),
        max_age=settings.staff_session_hours * 3600, httponly=True, secure=settings.cookie_secure,
        samesite="strict", path="/api/admin")


def staff_json(s: Staff) -> dict[str, Any]:
    return {"id": s.id, "email": s.email, "name": s.name, "role": s.role}


class Login(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=200)
    code: str | None = Field(None, max_length=8)


class Enroll(BaseModel):
    enroll_token: str = Field(max_length=500)
    code: str = Field(max_length=8)


class ClearLeads(BaseModel):
    confirm: str = Field(max_length=40)


class LeadUpdate(BaseModel):
    sales_status: Literal["new", "contacted", "interested", "won", "lost"] | None = None
    sales_owner: str | None = Field(None, max_length=120)
    notes: str | None = Field(None, max_length=5000)


def router_factory() -> APIRouter:
    r = APIRouter(prefix="/api/admin")

    # ------------------------------------------------ sign-in

    @r.post("/login")
    async def login(body: Login, request: Request, response: Response, session: SessionDep,
                    settings: SettingsDep, ip: IpDep):
        limiter: RateLimiter = request.app.state.limiter
        email = body.email.strip().lower()
        if not (await limiter.hit(f"staff-ip:{ip}", settings.staff_logins_per_ip_per_hour, 3600)
                and await limiter.hit(f"staff-email:{email}", 10, 3600)):
            raise _api_error(429, "too_many_attempts", "Too many sign-in attempts. Please wait an hour.")
        staff = await session.scalar(select(Staff).where(Staff.email == email))
        password_ok = verify_password(body.password, staff.password_hash if staff else _DUMMY_HASH)
        if staff is None or not staff.is_active or not password_ok:
            raise _api_error(401, "wrong_password", "Email or password is not right.")
        if not staff.totp_secret:
            secret = new_totp_secret()
            uri = otpauth_uri(secret, staff.email)
            token = _signer(settings, "sitescore-enroll").dumps({"staff": staff.id, "secret": secret})
            return {"step": "enroll", "enroll_token": token, "secret": secret,
                    "qr_svg": segno.make(uri, error="m").svg_inline(scale=5, border=2, omitsize=True)}
        if not body.code:
            return {"step": "code"}
        if not verify_totp(staff.totp_secret, body.code):
            raise _api_error(401, "wrong_code", "That code is not right. Check your authenticator app.")
        staff.last_login_at = utcnow()
        await session.commit()
        _set_staff_cookie(response, settings, staff)
        return {"step": "done", "staff": staff_json(staff)}

    @r.post("/enroll")
    async def enroll(body: Enroll, request: Request, response: Response, session: SessionDep,
                     settings: SettingsDep, ip: IpDep):
        limiter: RateLimiter = request.app.state.limiter
        if not (await limiter.hit(f"enroll-ip:{ip}", 20, 3600)
                and await limiter.hit(f"enroll:{body.enroll_token[-24:]}", 5, 900)):
            raise _api_error(429, "too_many_attempts", "Too many tries. Please sign in again in a while.")
        try:
            data = _signer(settings, "sitescore-enroll").loads(body.enroll_token, max_age=900)
        except (BadSignature, SignatureExpired):
            raise _api_error(400, "expired", "Setup took too long. Please sign in again.") from None
        staff = await session.get(Staff, data.get("staff"))
        if staff is None or not staff.is_active or staff.totp_secret:
            raise _api_error(400, "expired", "Please sign in again.")
        if not verify_totp(data["secret"], body.code):
            raise _api_error(401, "wrong_code", "That code is not right. Check your authenticator app.")
        staff.totp_secret, staff.last_login_at = data["secret"], utcnow()
        await session.commit()
        _set_staff_cookie(response, settings, staff)
        return {"step": "done", "staff": staff_json(staff)}

    @r.post("/logout")
    async def logout(response: Response, settings: SettingsDep):
        response.delete_cookie(settings.staff_cookie_name, path="/api/admin")
        return {"ok": True}

    @r.get("/me")
    async def me(staff: StaffDep):
        return {"staff": staff_json(staff)}

    # ------------------------------------------------ leads

    def lead_filters(q: str | None, status: str | None, callback: bool):
        conds = []
        if status in SALES_STATUSES:
            conds.append(Lead.sales_status == status)
        if callback:
            conds.append(Lead.callback_requested_at.is_not(None))
            conds.append(Lead.sales_status == "new")
        if q:
            like = f"%{q.strip().lower()[:80]}%"
            sites = select(Scan.lead_id).join(Site).where(Site.host.ilike(like))
            conds.append(or_(func.lower(Lead.email).like(like), func.lower(Lead.name).like(like),
                             func.lower(Lead.business_name).like(like), Lead.phone.like(like),
                             Lead.id.in_(sites)))
        return conds

    async def leads_page(session: AsyncSession, conds, limit: int, offset: int):
        base = select(Lead).where(*conds)
        total = await session.scalar(select(func.count()).select_from(base.subquery()))
        rows = (await session.execute(
            base.options(selectinload(Lead.scans).selectinload(Scan.site))
            .order_by(Lead.callback_requested_at.is_(None), Lead.callback_requested_at.desc(),
                      Lead.updated_at.desc())
            .limit(limit).offset(offset))).scalars().all()
        return total, rows

    def lead_row(lead: Lead) -> dict[str, Any]:
        scans = sorted(lead.scans, key=lambda s: s.created_at, reverse=True)
        latest = scans[0] if scans else None
        return {
            "id": lead.id, "email": lead.email, "name": lead.name, "business_name": lead.business_name,
            "phone": lead.phone, "sales_status": lead.sales_status, "sales_owner": lead.sales_owner,
            "callback_requested_at": lead.callback_requested_at.isoformat() if lead.callback_requested_at else None,
            "created_at": lead.created_at.isoformat(),
            "scan_count": len(scans),
            "latest_scan": None if latest is None else {
                "token": latest.token, "host": latest.site.host, "score": latest.score, "band": latest.band,
                "agent_score": latest.agent_score,
                "status": latest.status, "created_at": latest.created_at.isoformat()},
        }

    @r.get("/stats")
    async def stats(_: StaffDep, session: SessionDep):
        now = utcnow()
        count = lambda *c: session.scalar(select(func.count()).select_from(Lead).where(*c))  # noqa: E731
        return {
            "leads_7d": await count(Lead.created_at >= now - timedelta(days=7)),
            "callbacks_waiting": await count(Lead.callback_requested_at.is_not(None), Lead.sales_status == "new"),
            "scans_today": await session.scalar(select(func.count()).select_from(Scan).where(
                Scan.created_at >= now - timedelta(days=1))),
            "won_30d": await count(Lead.sales_status == "won", Lead.updated_at >= now - timedelta(days=30)),
            "by_status": {s: await count(Lead.sales_status == s) for s in SALES_STATUSES},
        }

    @r.get("/leads")
    async def leads(_: StaffDep, session: SessionDep, q: str | None = None, status: str | None = None,
                    callback: bool = False, page: int = Query(1, ge=1), per_page: int = Query(25, ge=1, le=100)):
        total, rows = await leads_page(session, lead_filters(q, status, callback), per_page, (page - 1) * per_page)
        return {"total": total, "page": page, "per_page": per_page, "leads": [lead_row(x) for x in rows]}

    @r.get("/leads.csv")
    async def leads_csv(_: StaffDep, session: SessionDep, settings: SettingsDep, q: str | None = None,
                        status: str | None = None, callback: bool = False):
        _, rows = await leads_page(session, lead_filters(q, status, callback), 10_000, 0)
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["Email", "Name", "Business", "Phone", "Sales status", "Owner", "Call requested",
                    "Latest site", "Health score", "AI agent score", "Scans", "Signed up", "Results link"])
        for lead in rows:
            row = lead_row(lead)
            ls = row["latest_scan"] or {}
            link = f"{settings.public_base_url.rstrip('/')}/scan/{ls['token']}" if ls else ""
            w.writerow([csv_safe(x) for x in (
                row["email"], row["name"], row["business_name"], row["phone"], row["sales_status"],
                row["sales_owner"], (row["callback_requested_at"] or "")[:16].replace("T", " "),
                ls.get("host", ""), ls.get("score"), ls.get("agent_score"), row["scan_count"], row["created_at"][:10], link)])
        day = utcnow().date().isoformat()
        return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="sitescore-leads-{day}.csv"'})

    @r.get("/leads/{lead_id}")
    async def lead_detail(lead_id: int, _: StaffDep, session: SessionDep):
        lead = await session.scalar(select(Lead).where(Lead.id == lead_id).options(
            selectinload(Lead.scans).selectinload(Scan.site),
            selectinload(Lead.scans).selectinload(Scan.results)))
        if lead is None:
            raise _api_error(404, "not_found", "Lead not found.")
        out = lead_row(lead)
        out["notes"] = lead.notes
        out["consent_at"] = lead.consent_at.isoformat() if lead.consent_at else None
        out["scans"] = [
            {"token": s.token, "host": s.site.host, "status": s.status, "score": s.score, "band": s.band,
             "agent_score": s.agent_score,
             "created_at": s.created_at.isoformat(),
             "emailed": s.emailed_at is not None, "report_status": report_status(s),
             "report_error": s.report_error, "speed_error": speed_error(s)}
            for s in sorted(lead.scans, key=lambda s: s.created_at, reverse=True)]
        return out

    @r.post("/scans/{token}/send-report")
    async def send_report_again(token: str, staff: StaffDep, session: SessionDep, settings: SettingsDep):
        """Email the PDF report to the lead again, for example after fixing SMTP settings."""
        scan = await session.scalar(select(Scan).where(Scan.token == token[:40]))
        if scan is None:
            raise _api_error(404, "not_found", "Scan not found.")
        if scan.status != "done" or scan.kind != "audit":
            raise _api_error(409, "not_ready", "The report can be sent once the scan has finished.")
        log.info("staff %s asked to resend the report for scan %s", staff.email, scan.id)
        await resend_report(session, scan, settings)
        return {"ok": True}

    @r.delete("/leads/{lead_id}")
    async def delete_lead(lead_id: int, staff: StaffDep, session: SessionDep):
        """Delete one lead with all its scans. Cannot be undone."""
        lead = await session.get(Lead, lead_id)
        if lead is None:
            raise _api_error(404, "not_found", "Lead not found.")
        email = lead.email
        scans = await delete_leads(session, [lead_id])
        await session.commit()
        log.warning("staff %s deleted lead %s (%s) with %d scans", staff.email, lead_id, email, scans)
        return {"ok": True, "scans": scans}

    @r.post("/leads/clear")
    async def clear_leads(body: ClearLeads, staff: StaffDep, session: SessionDep):
        """Delete every lead and scan. Admins only, and only with the typed confirmation."""
        if staff.role != "admin":
            raise _api_error(403, "admins_only", "Only an admin account can clear all leads.")
        if body.confirm.strip().upper() != "DELETE ALL":
            raise _api_error(422, "invalid", "Type DELETE ALL to confirm.", field="confirm")
        total = await session.scalar(select(func.count()).select_from(Lead))
        scans = await delete_leads(session, select(Lead.id))
        await session.commit()
        log.warning("staff %s cleared all leads: %d leads, %d scans", staff.email, total, scans)
        return {"ok": True, "leads": total, "scans": scans}

    @r.patch("/leads/{lead_id}")
    async def update_lead(lead_id: int, body: LeadUpdate, staff: StaffDep, session: SessionDep):
        lead = await session.get(Lead, lead_id)
        if lead is None:
            raise _api_error(404, "not_found", "Lead not found.")
        changes = body.model_dump(exclude_unset=True)
        for field, value in changes.items():
            setattr(lead, field, value.strip() if isinstance(value, str) and field != "notes" else value)
        if "sales_status" in changes and changes["sales_status"] != "new" and not lead.sales_owner:
            lead.sales_owner = staff.name
        await session.commit()
        return {"ok": True, "sales_status": lead.sales_status, "sales_owner": lead.sales_owner, "notes": lead.notes}

    return r
