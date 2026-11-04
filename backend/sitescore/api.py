"""Public HTTP API. Served under /api behind Nginx; the web app calls it same-origin."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from . import db
from .config import Settings, get_settings
from .db import Lead, Scan, Site, get_session, utcnow
from .engine import ScanError, guard
from .ratelimit import RateLimiter
from .scans import load_scan, serialize
from .security import (
    InputError, aware, clean_text, make_session, normalize_email, normalize_phone, read_session,
    verify_turnstile,
)
from .worker import enqueue_scan

log = logging.getLogger("sitescore.api")


class ApiError(HTTPException):
    def __init__(self, status: int, code: str, message: str, **extra: Any):
        super().__init__(status_code=status, detail={"error": code, "message": message, **extra})


# ---------------------------------------------------------------- app

@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if db._engine is None:
        db.init_engine(settings.database_url)
    if settings.auto_create_tables:
        await db.create_tables()
    app.state.limiter = RateLimiter(settings.redis_url if settings.queue_mode == "rq" else None)
    yield
    await app.state.limiter.close()


MAX_BODY_BYTES = 64 * 1024

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Resource-Policy": "same-site",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
}


def create_app() -> FastAPI:
    from .config import check_settings
    from .logs import setup_logging

    settings = get_settings()
    setup_logging(settings.log_level)
    check_settings(settings)
    app = FastAPI(title="MAKTECH SiteScore API", version="1.0.0", lifespan=lifespan,
                  docs_url=None if settings.is_production else "/api/docs",
                  openapi_url=None if settings.is_production else "/api/openapi.json", redoc_url=None)
    # The web app runs on its own subdomain and sends the session cookie with each call.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip().rstrip("/") for o in settings.cors_origins.split(",") if o.strip()],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
        max_age=600,
    )

    @app.middleware("http")
    async def guard_requests(request: Request, call_next):
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > MAX_BODY_BYTES:
            return JSONResponse({"error": "too_large", "message": "Request is too large."}, status_code=413)
        response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        if settings.is_production:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        if request.url.path.startswith("/api/") and "cache-control" not in response.headers:
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException):
        detail = exc.detail if isinstance(exc.detail, dict) else {"error": "error", "message": str(exc.detail)}
        return JSONResponse(detail, status_code=exc.status_code, headers=getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        field = str(first.get("loc", ["", ""])[-1])
        return JSONResponse({"error": "invalid", "field": field, "message": "Please check this field."},
                            status_code=422)

    app.include_router(router_factory())
    from .admin import router_factory as admin_router

    app.include_router(admin_router())
    return app


# ---------------------------------------------------------------- dependencies

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def client_ip(request: Request, settings: SettingsDep) -> str:
    """The visitor's IP. Only the entries our own proxies added are trusted, so it cannot be spoofed."""
    if settings.client_ip_header:
        value = request.headers.get(settings.client_ip_header)
        if value:
            return value.strip()[:64]
    if settings.trust_proxy_headers and settings.trusted_proxy_hops > 0:
        chain = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
        if len(chain) >= settings.trusted_proxy_hops:
            return chain[-settings.trusted_proxy_hops][:64]
    return (request.client.host if request.client else "unknown")[:64]


IpDep = Annotated[str, Depends(client_ip)]


async def current_lead(request: Request, session: SessionDep, settings: SettingsDep) -> Lead:
    lead_id = read_session(settings, request.cookies.get(settings.cookie_name))
    lead = await session.get(Lead, lead_id) if lead_id else None
    if lead is None:
        raise ApiError(401, "not_signed_in", "Please enter your email to continue.")
    return lead


LeadDep = Annotated[Lead, Depends(current_lead)]


# ---------------------------------------------------------------- schemas

class SignUp(BaseModel):
    email: str = Field(max_length=254)
    name: str | None = Field(None, max_length=120)
    business_name: str | None = Field(None, max_length=160)
    phone: str | None = Field(None, max_length=40)
    turnstile_token: str | None = Field(None, max_length=4096)


class ScanRequest(BaseModel):
    url: str = Field(max_length=300)


def lead_json(lead: Lead) -> dict[str, Any]:
    # Just the address. Anyone can type any address, so stored contact details stay with the sales team.
    return {"email": lead.email}


# ---------------------------------------------------------------- routes

def router_factory():
    from fastapi import APIRouter

    r = APIRouter(prefix="/api")

    @r.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @r.get("/config")
    async def public_config(settings: SettingsDep) -> dict[str, Any]:
        return {"turnstile_site_key": settings.turnstile_site_key,
                "whatsapp_number": settings.whatsapp_number,
                "contact_phone": settings.contact_phone,
                "prices": {"usd": settings.offer_price_usd, "bdt": settings.offer_price_bdt}}

    # ------------------------------------------------ sign-up (email address checked, no code)

    @r.post("/auth/start")
    async def start(body: SignUp, request: Request, response: Response, session: SessionDep,
                    settings: SettingsDep, ip: IpDep):
        limiter: RateLimiter = request.app.state.limiter
        if not await limiter.hit(f"signup:{ip}", settings.signups_per_ip_per_hour, 3600):
            raise ApiError(429, "too_many_signups", "Too many tries from your network. Please try again in an hour.")
        if not await verify_turnstile(settings, body.turnstile_token, ip):
            raise ApiError(400, "bot_check", "Please complete the security check and try again.")
        try:
            email = await normalize_email(body.email, settings.email_check_deliverability)
            phone = normalize_phone(body.phone)
        except InputError as exc:
            raise ApiError(422, "invalid", exc.message, field=exc.field) from exc

        lead = await session.scalar(select(Lead).where(Lead.email == email))
        if lead is None:
            lead = Lead(email=email, source="sitescore")
            session.add(lead)
        for attr, value in (("name", clean_text(body.name, 120)),
                            ("business_name", clean_text(body.business_name, 160)), ("phone", phone)):
            if value:
                setattr(lead, attr, value)
        # consent_at: when they accepted the privacy notice and terms by submitting the form.
        lead.consent_at, lead.last_ip = utcnow(), ip
        try:
            await session.commit()
        except IntegrityError:
            # Two sign-ups with the same address at the same moment: use the one that won.
            await session.rollback()
            lead = await session.scalar(select(Lead).where(Lead.email == email))
            if lead is None:
                raise
        response.set_cookie(settings.cookie_name, make_session(settings, lead.id),
                            max_age=settings.session_days * 86400, httponly=True,
                            secure=settings.cookie_secure, samesite="lax", path="/")
        return {"ok": True, "lead": lead_json(lead)}

    @r.post("/auth/logout")
    async def logout(response: Response, settings: SettingsDep):
        response.delete_cookie(settings.cookie_name, path="/")
        return {"ok": True}

    @r.get("/me")
    async def me(lead: LeadDep):
        # Only what the visitor typed in themselves: an email address is not proof of identity,
        # so earlier scans and other history for the address are never shown here.
        return {"lead": lead_json(lead)}

    # ------------------------------------------------ scans

    @r.post("/scans", status_code=201)
    async def start_scan(body: ScanRequest, lead: LeadDep, session: SessionDep, settings: SettingsDep, ip: IpDep):
        try:
            host, apex = guard.normalize_target(body.url)
            opted_out = {d.strip().lower().lstrip("*.") for d in settings.opt_out_domains.split(",") if d.strip()}
            if apex in opted_out or host in opted_out:
                raise ScanError("opted_out", "The owner of this website has asked us not to scan it.")
            guard.set_blocked_networks([c for c in settings.blocked_networks.split(",") if c.strip()])
            await asyncio.to_thread(guard.assert_public_host, host)
        except ScanError as exc:
            raise ApiError(422, exc.code, exc.message, field="url") from exc

        recent = await session.scalar(
            select(Scan).join(Site).where(Scan.lead_id == lead.id, Site.host == host,
                                          Scan.status != "failed",
                                          Scan.created_at >= utcnow() - timedelta(minutes=10))
            .order_by(Scan.created_at.desc()).limit(1))
        if recent is not None:
            return {"token": recent.token, "reused": True}

        day_ago = utcnow() - timedelta(days=1)
        by_lead = await session.scalar(select(func.count()).select_from(Scan).where(
            Scan.lead_id == lead.id, Scan.created_at >= day_ago))
        by_ip = await session.scalar(select(func.count()).select_from(Scan).where(
            Scan.ip == ip, Scan.created_at >= day_ago))
        if by_lead >= settings.scans_per_lead_per_day or by_ip >= settings.scans_per_ip_per_day:
            raise ApiError(429, "too_many_scans",
                           "You have reached today's free scan limit. Please try again tomorrow.")

        site = await session.scalar(select(Site).where(Site.host == host))
        if site is None:
            site = Site(host=host, apex=apex)
            session.add(site)
            await session.flush()
        scan = Scan(lead_id=lead.id, site_id=site.id, target=host, ip=ip)
        session.add(scan)
        await session.commit()
        enqueue_scan(scan.id, settings)
        return {"token": scan.token, "reused": False}

    @r.get("/scans/{token}")
    async def get_scan(token: str, request: Request, session: SessionDep, settings: SettingsDep):
        scan = await load_scan(session, token=token[:40])
        if scan is None:
            raise ApiError(404, "not_found", "We could not find that scan.")
        if aware(scan.created_at) < utcnow() - timedelta(days=settings.results_link_days):
            raise ApiError(410, "expired", "This results link has expired. Run a new scan to see fresh results.")
        if scan.status in ("queued", "running") and aware(scan.created_at) < utcnow() - timedelta(minutes=10):
            # The worker died or the queue is stuck: never leave a visitor watching a spinner forever.
            scan.status, scan.finished_at = "failed", utcnow()
            scan.error_code = "timeout"
            scan.error_message = "The scan took too long and was stopped. Please try again."
            await session.commit()
        out = serialize(scan, settings)
        is_owner = read_session(settings, request.cookies.get(settings.cookie_name)) == scan.lead_id
        out["is_owner"] = is_owner
        out["callback_requested"] = bool(is_owner and scan.lead.callback_requested_at)
        out["owner_email"] = scan.lead.email if is_owner else None
        return out

    @r.get("/scans/{token}/report.pdf")
    async def report_pdf(token: str, request: Request, session: SessionDep, settings: SettingsDep, ip: IpDep):
        from .report import render_pdf

        limiter: RateLimiter = request.app.state.limiter
        if not await limiter.hit(f"pdf:{ip}", settings.pdf_downloads_per_ip_per_hour, 3600):
            raise ApiError(429, "too_many_downloads", "Too many downloads. Please try again later.")
        scan = await load_scan(session, token=token[:40])
        if scan is None or scan.status != "done":
            raise ApiError(404, "not_found", "The report is ready once the scan has finished.")
        if aware(scan.created_at) < utcnow() - timedelta(days=settings.results_link_days):
            raise ApiError(410, "expired", "This results link has expired. Run a new scan to see fresh results.")
        pdf = await asyncio.to_thread(render_pdf, serialize(scan, settings), settings)
        day = (scan.finished_at or utcnow()).date().isoformat()
        return Response(pdf, media_type="application/pdf", headers={
            "Content-Disposition": f'attachment; filename="SiteScore-{scan.site.host}-{day}.pdf"',
            "Cache-Control": "private, max-age=300"})

    @r.post("/scans/{token}/callback")
    async def request_callback(token: str, session: SessionDep, lead: LeadDep):
        scan = await load_scan(session, token=token[:40])
        if scan is None or scan.lead_id != lead.id:
            raise ApiError(404, "not_found", "We could not find that scan.")
        if lead.callback_requested_at is None:
            lead.callback_requested_at = utcnow()
        await session.commit()
        return {"ok": True}

    return r


app = create_app()
