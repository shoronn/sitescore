"""API flow tests: sign-up, scan, live progress, limits."""
from __future__ import annotations

import asyncio
import os

os.environ.update({
    "SITESCORE_QUEUE_MODE": "inline",
    "SITESCORE_COOKIE_SECURE": "false",
    "SITESCORE_EMAIL_CHECK_DELIVERABILITY": "false",
    "SITESCORE_DATABASE_URL": "sqlite+aiosqlite://",
    "SITESCORE_REDIS_URL": "",
    "SITESCORE_SECRET_KEY": "test-secret-key-test-secret-key-test-secret-key",
    "SITESCORE_PUBLIC_BASE_URL": "https://sitescore.maktechgroup.com",
})

import httpx  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from sitescore import db, mailer, scans, worker  # noqa: E402
from sitescore.api import create_app  # noqa: E402
from sitescore.config import get_settings  # noqa: E402
from sitescore.engine import guard  # noqa: E402
from sitescore.engine.checks import CHECKS  # noqa: E402
from sitescore.engine.context import ENGINE_VERSION  # noqa: E402
from sitescore.engine.models import CheckResult, Status  # noqa: E402
from sitescore.engine.scoring import points_for  # noqa: E402
from sitescore.ratelimit import RateLimiter  # noqa: E402


async def fake_run_scan(target, settings=None, on_result=None, ctx=None):
    for c in CHECKS:
        status = Status.FAIL if c.key == "dmarc" else Status.PASS
        r = CheckResult(c.key, c.name, c.category, c.weight, status, points_for(status, c.weight),
                        f"{c.name} title", "summary", "why", "fix", "none", False, {"reason": "x"}, 5)
        await asyncio.sleep(0)
        await on_result(r)

    class R:
        engine_version = ENGINE_VERSION
    return R()


@pytest.fixture
async def client(monkeypatch, tmp_path):
    get_settings.cache_clear()
    # A file database with a connection per session, like Postgres in production.
    db.init_engine(f"sqlite+aiosqlite:///{tmp_path}/test.db", poolclass=NullPool, connect_args={"timeout": 30})
    await db.create_tables()
    monkeypatch.setattr(scans, "run_scan", fake_run_scan)
    monkeypatch.setattr(guard, "assert_public_host", lambda host: ["93.184.216.34"])
    mailer.OUTBOX.clear()
    app = create_app()
    app.state.limiter = RateLimiter(None)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c
    await worker.wait_inline()
    await db.get_engine().dispose()


async def sign_in(client, email="owner@business.com", **extra) -> None:
    r = await client.post("/api/auth/start", json={"email": email, **extra})
    assert r.status_code == 200, r.text


async def test_full_flow(client):
    assert (await client.get("/api/me")).status_code == 401
    assert (await client.post("/api/scans", json={"url": "example.com"})).status_code == 401

    r = await client.post("/api/auth/start", json={
        "email": "Owner@Business.com", "name": "  Rahim  Uddin ", "business_name": "Rahim Traders",
        "phone": "+880 1711-000000"})
    assert r.status_code == 200
    # Signed in straight away, and no email is sent for it.
    assert r.json()["lead"] == {"email": "owner@business.com"}
    assert mailer.OUTBOX == []
    assert (await client.get("/api/me")).json() == {"lead": {"email": "owner@business.com"}}
    async with db.sessionmaker()() as s:
        from sqlalchemy import select

        lead = await s.scalar(select(db.Lead).where(db.Lead.email == "owner@business.com"))
        assert (lead.name, lead.business_name, lead.phone) == ("Rahim Uddin", "Rahim Traders", "+8801711000000")
        assert lead.consent_at is not None

    r = await client.post("/api/scans", json={"url": "https://www.Example.com/about"})
    assert r.status_code == 201, r.text
    token = r.json()["token"]
    await worker.wait_inline()

    data = (await client.get(f"/api/scans/{token}")).json()
    assert data["status"] == "done" and data["host"] == "www.example.com"
    assert data["progress"] == {"done": len(CHECKS), "total": len(CHECKS)}
    by_key = {x["key"]: x for x in data["results"]}
    assert "backups" not in by_key and "answers" not in data
    assert by_key["dmarc"]["status"] == "fail"
    w = {c.key: c.weight for c in CHECKS}
    assert data["coverage"] == 100 and data["score"] == 100 - w["dmarc"] and data["band"] == "good"
    # AI agent readiness has its own score (every agent check passes in the fake scan).
    assert data["agent"] == {"score": 100, "level": "ready", "label": "Agent ready", "band": "good"}
    assert {c["key"] for c in data["categories"]} == {"security", "reliability", "email", "performance", "seo"}

    # Same site again within 10 minutes reuses the scan.
    r = await client.post("/api/scans", json={"url": "www.example.com"})
    assert r.json() == {"token": token, "reused": True}

    assert data["is_owner"] is True and data["owner_email"] == "owner@business.com"
    assert (await client.post(f"/api/scans/{token}/callback")).json() == {"ok": True}
    assert (await client.get(f"/api/scans/{token}")).json()["callback_requested"] is True
    client.cookies.clear()
    shared = (await client.get(f"/api/scans/{token}")).json()
    assert shared["is_owner"] is False and shared["owner_email"] is None
    await sign_in(client)
    # Typing an address is not proof of owning it, so the session shows no history for it.
    assert (await client.get("/api/me")).json() == {"lead": {"email": "owner@business.com"}}


async def test_returning_visitor_keeps_one_lead(client):
    await sign_in(client, "back@shop.com", name="Karim", phone="01711000000")
    client.cookies.clear()
    await sign_in(client, "Back@Shop.com", business_name="Karim Store")
    async with db.sessionmaker()() as s:
        from sqlalchemy import select

        leads = (await s.execute(select(db.Lead).where(db.Lead.email == "back@shop.com"))).scalars().all()
        assert len(leads) == 1
        # Details typed earlier are kept; new ones are added.
        assert (leads[0].name, leads[0].business_name, leads[0].phone) == ("Karim", "Karim Store", "01711000000")


async def test_input_rules(client):
    for body, field in (({"email": "not-an-email"}, "email"),
                        ({"email": "two@@company.com"}, "email"),
                        ({"email": "me@mailinator.com"}, "email"),
                        ({"email": "x@company.com", "phone": "abc"}, "phone")):
        r = await client.post("/api/auth/start", json=body)
        assert r.status_code == 422 and r.json()["field"] == field, body
        assert "set-cookie" not in r.headers
    r = await client.post("/api/auth/start", json={"email": "me@mailinator.com"})
    assert "temporary" in r.json()["message"]
    assert (await client.get("/api/me")).status_code == 401


async def test_email_domain_must_accept_mail(client, monkeypatch):
    """With the DNS check on (the default), an address at a domain with no mail server is refused."""
    import email_validator

    from sitescore import security

    def fake_validate(email, check_deliverability=True):
        if check_deliverability and email.endswith("@no-mail.example"):
            raise email_validator.EmailUndeliverableError("The domain name no-mail.example does not accept email.")
        return email_validator.validate_email(email, check_deliverability=False)

    monkeypatch.setattr(security, "validate_email", fake_validate)
    monkeypatch.setattr(get_settings(), "email_check_deliverability", True)
    r = await client.post("/api/auth/start", json={"email": "owner@no-mail.example"})
    assert r.status_code == 422 and r.json()["field"] == "email"
    r = await client.post("/api/auth/start", json={"email": "owner@real-shop.com"})
    assert r.status_code == 200


async def test_signup_rate_limit(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "signups_per_ip_per_hour", 3)
    for i in range(3):
        await sign_in(client, f"c{i}@d-co.com")
    r = await client.post("/api/auth/start", json={"email": "c9@d-co.com"})
    assert r.status_code == 429 and r.json()["error"] == "too_many_signups"


async def test_scan_target_errors_and_daily_limit(client, monkeypatch):
    await sign_in(client)
    r = await client.post("/api/scans", json={"url": "192.168.1.1"})
    assert r.status_code == 422 and r.json()["error"] == "ip_address"

    from sitescore.engine.models import ScanError

    def private(host):
        raise ScanError("private", f"{host} points to a private or reserved address and cannot be scanned.")

    monkeypatch.setattr(guard, "assert_public_host", private)
    r = await client.post("/api/scans", json={"url": "intranet.example.com"})
    assert r.status_code == 422 and r.json()["error"] == "private"
    monkeypatch.setattr(guard, "assert_public_host", lambda host: ["93.184.216.34"])

    for i in range(5):
        assert (await client.post("/api/scans", json={"url": f"site{i}.example.com"})).status_code == 201
    r = await client.post("/api/scans", json={"url": "site9.example.com"})
    assert r.status_code == 429 and r.json()["error"] == "too_many_scans"


async def test_unknown_token(client):
    r = await client.get("/api/scans/nope")
    assert r.status_code == 404 and r.json()["error"] == "not_found"


async def test_stuck_scan_is_reported_failed(client):
    from datetime import timedelta

    from sqlalchemy import update

    await sign_in(client)
    worker_enqueue = worker.enqueue_scan
    import sitescore.api as api_module
    api_module.enqueue_scan = lambda scan_id, settings=None: None  # simulate a dead worker
    try:
        token = (await client.post("/api/scans", json={"url": "stuck.example.com"})).json()["token"]
    finally:
        api_module.enqueue_scan = worker_enqueue
    async with db.sessionmaker()() as s:
        await s.execute(update(db.Scan).values(created_at=db.utcnow() - timedelta(minutes=11)))
        await s.commit()
    data = (await client.get(f"/api/scans/{token}")).json()
    assert data["status"] == "failed" and data["error"]["code"] == "timeout"


def report_mails(to: str):
    return [m for m in mailer.OUTBOX if m.to == to and m.attachments]


async def test_report_emailed_once_with_pdf(client):
    await sign_in(client, "pdf@business.com")
    token = (await client.post("/api/scans", json={"url": "pdf.example.com"})).json()["token"]
    await worker.wait_inline()
    mails = report_mails("pdf@business.com")
    assert len(mails) == 1
    m = mails[0]
    assert m.subject.startswith("pdf.example.com on SiteScore: AI agent readiness ")
    assert m.attachments[0].content[:5] == b"%PDF-"
    assert f"https://sitescore.maktechgroup.com/scan/{token}" in m.text
    assert (await client.get(f"/api/scans/{token}")).json()["report_emailed"] is True
    # Reading the results again never sends a second email.
    await client.get(f"/api/scans/{token}")
    await worker.wait_inline()
    assert len(report_mails("pdf@business.com")) == 1


async def test_report_goes_out_the_moment_the_scan_is_done(client):
    await sign_in(client, "now@business.com")
    token = (await client.post("/api/scans", json={"url": "now.example.com"})).json()["token"]
    await worker.wait_inline()
    assert len(report_mails("now@business.com")) == 1
    assert (await client.get(f"/api/scans/{token}")).json()["report_status"] == "sent"


async def test_anyone_can_check_any_site_without_an_ownership_switch(client):
    """No "I own or manage this website" step: a valid email is all it takes."""
    r = await client.post("/api/auth/start", json={"email": "visitor@agency.com"})
    assert r.status_code == 200
    r = await client.post("/api/scans", json={"url": "someone-elses-site.com"})
    assert r.status_code == 201
    # The removed answers endpoint is gone.
    assert (await client.post(f"/api/scans/{r.json()['token']}/answers", json={"backups": "none"})).status_code in (404, 405)


async def test_pdf_download(client):
    await sign_in(client)
    token = (await client.post("/api/scans", json={"url": "dl.example.com"})).json()["token"]
    await worker.wait_inline()
    r = await client.get(f"/api/scans/{token}/report.pdf")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.content[:5] == b"%PDF-" and "SiteScore-dl.example.com-" in r.headers["content-disposition"]


async def test_cors_allows_web_app_with_cookies(client):
    r = await client.options("/api/auth/start", headers={
        "Origin": "https://sitescore.maktechgroup.com", "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type"})
    assert r.headers["access-control-allow-origin"] == "https://sitescore.maktechgroup.com"
    assert r.headers["access-control-allow-credentials"] == "true"
    r = await client.options("/api/auth/start", headers={
        "Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in r.headers


def test_client_ip_uses_trusted_hop_only():
    from starlette.requests import Request as StarletteRequest

    from sitescore.api import client_ip
    from sitescore.config import Settings

    def req(xff):
        return StarletteRequest({"type": "http", "headers": [(b"x-forwarded-for", xff.encode())],
                                 "client": ("10.0.0.5", 1234)})

    s = Settings()
    # A visitor sends a fake header; the proxy appends the real address at the end.
    assert client_ip(req("1.2.3.4, 203.0.113.9"), s) == "203.0.113.9"
    assert client_ip(req("203.0.113.9"), s) == "203.0.113.9"
    s2 = Settings(client_ip_header="CF-Connecting-IP")
    r = StarletteRequest({"type": "http", "headers": [(b"cf-connecting-ip", b"198.51.100.4")], "client": ("10.0.0.5", 1)})
    assert client_ip(r, s2) == "198.51.100.4"


async def test_cleanup_keeps_recent_and_won_leads(client):
    from datetime import timedelta

    from sqlalchemy import func, select, update

    from sitescore.config import get_settings
    from sitescore.maintenance import cleanup

    await sign_in(client, "old@shop.com")
    await client.post("/api/scans", json={"url": "old.example.com"})
    await sign_in(client, "won@shop.com")
    await client.post("/api/scans", json={"url": "won.example.com"})
    await sign_in(client, "fresh@shop.com")
    await worker.wait_inline()
    long_ago = db.utcnow() - timedelta(days=400)
    async with db.sessionmaker()() as s:
        await s.execute(update(db.Lead).where(db.Lead.email.in_(["old@shop.com", "won@shop.com"]))
                        .values(created_at=long_ago, updated_at=long_ago))
        await s.execute(update(db.Lead).where(db.Lead.email == "won@shop.com").values(sales_status="won"))
        await s.commit()
    result = await cleanup(get_settings())
    assert result == {"leads": 1, "scans": 1}
    async with db.sessionmaker()() as s:
        left = set((await s.execute(select(db.Lead.email))).scalars())
        assert left == {"won@shop.com", "fresh@shop.com"}
        assert await s.scalar(select(func.count()).select_from(db.CheckResultRow)) == len(CHECKS)  # the won lead's one scan


async def test_opted_out_domain_is_refused(client):
    from sitescore.config import get_settings

    settings = get_settings()
    settings.opt_out_domains = "noscan.com"
    try:
        await sign_in(client)
        r = await client.post("/api/scans", json={"url": "https://shop.noscan.com"})
        assert r.status_code == 422 and r.json()["error"] == "opted_out"
    finally:
        settings.opt_out_domains = ""


async def test_config_has_round_prices(client):
    cfg = (await client.get("/api/config")).json()
    assert cfg["prices"] == {"usd": 40, "bdt": 5000}
    assert "code_ttl_minutes" not in cfg
    assert cfg["whatsapp_number"] == cfg["contact_phone"] == "8801897669234"
    assert "backup_options" not in cfg


def test_pdf_shows_prices_from_settings(monkeypatch):
    from sitescore.report import report_context

    settings = get_settings()
    monkeypatch.setattr(settings, "offer_price_usd", 45)
    monkeypatch.setattr(settings, "offer_price_bdt", 5500)
    data = {"token": "t", "host": "a.example", "results": [], "categories": [], "score": None, "band": None,
            "band_label": None, "capped": False, "coverage": None, "finished_at": "2026-10-11T10:00:00+00:00"}
    ctx = report_context(data, settings)
    assert (ctx["price_usd"], ctx["price_bdt"]) == ("$45", "Tk 5,500")


async def test_retired_checks_in_old_scans_are_ignored(client):
    """Scans from before the backup question was removed still hold a "backups" result."""
    from sqlalchemy import select

    await sign_in(client)
    token = (await client.post("/api/scans", json={"url": "old.example.com"})).json()["token"]
    await worker.wait_inline()
    before = (await client.get(f"/api/scans/{token}")).json()
    async with db.sessionmaker()() as s:
        scan = await s.scalar(select(db.Scan).where(db.Scan.token == token))
        s.add(db.CheckResultRow(scan_id=scan.id, position=99, check_key="backups", name="Backups",
                                category="reliability", weight=5, status="fail", points=0, title="No backups",
                                summary="", why="", fix="", offer="cloudcare", critical=False, evidence={}))
        await s.commit()
    after = (await client.get(f"/api/scans/{token}")).json()
    assert "backups" not in {r["key"] for r in after["results"]}
    assert after["categories"] == before["categories"]
    r = await client.get(f"/api/scans/{token}/report.pdf")
    assert r.status_code == 200
