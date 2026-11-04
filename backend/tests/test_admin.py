"""Sales dashboard: staff sign-in with authenticator codes, leads, updates, CSV."""
from __future__ import annotations

import csv
import io

from test_api import client, sign_in  # noqa: F401  (shared fixture and helper)

from sitescore import db, worker
from sitescore.staff_auth import hash_password, totp_now, verify_password, verify_totp


def test_password_and_totp_helpers():
    h = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", h) and not verify_password("wrong", h)
    secret = "JBSWY3DPEHPK3PXP"
    assert verify_totp(secret, totp_now(secret, at=1_000_000), at=1_000_000)
    assert verify_totp(secret, totp_now(secret, at=1_000_000 - 30), at=1_000_000)  # one step of drift
    assert not verify_totp(secret, totp_now(secret, at=1_000_000 - 120), at=1_000_000)
    # RFC 6238 test vector (SHA1, T=59): 94287082 -> last 6 digits
    rfc_secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
    assert totp_now(rfc_secret, at=59) == "287082"


async def add_staff(email="sales@maktech.test", password="a-long-password-123", role="sales"):
    async with db.sessionmaker()() as s:
        s.add(db.Staff(email=email, name="Nadia", role=role, password_hash=hash_password(password)))
        await s.commit()


async def staff_sign_in(client, email="sales@maktech.test", password="a-long-password-123"):
    r = await client.post("/api/admin/login", json={"email": email, "password": password})
    data = r.json()
    if data["step"] == "enroll":
        assert "<svg" in data["qr_svg"]
        r = await client.post("/api/admin/enroll", json={"enroll_token": data["enroll_token"],
                                                         "code": totp_now(data["secret"])})
        assert r.json()["step"] == "done"
        return data["secret"]
    return None


async def test_staff_sign_in_flow(client):
    await add_staff()
    assert (await client.get("/api/admin/leads")).status_code == 401
    r = await client.post("/api/admin/login", json={"email": "sales@maktech.test", "password": "nope"})
    assert r.status_code == 401 and r.json()["error"] == "wrong_password"

    secret = await staff_sign_in(client)
    assert (await client.get("/api/admin/me")).json()["staff"]["name"] == "Nadia"
    await client.post("/api/admin/logout")
    assert (await client.get("/api/admin/me")).status_code == 401

    # Second sign-in asks for the code instead of enrolling again.
    r = await client.post("/api/admin/login", json={"email": "sales@maktech.test", "password": "a-long-password-123"})
    assert r.json() == {"step": "code"}
    r = await client.post("/api/admin/login", json={"email": "sales@maktech.test",
                                                    "password": "a-long-password-123", "code": "000000"})
    assert r.status_code == 401 or totp_now(secret) == "000000"
    r = await client.post("/api/admin/login", json={"email": "sales@maktech.test",
                                                    "password": "a-long-password-123", "code": totp_now(secret)})
    assert r.json()["step"] == "done"


async def test_visitor_session_is_not_staff(client):
    await sign_in(client)
    assert (await client.get("/api/admin/leads")).status_code == 401


async def test_leads_callback_update_and_csv(client):
    # Two visitors scan; one asks for a call.
    await sign_in(client, "first@shop.com", name="Karim", business_name="Karim Shop", phone="01711000000")
    t1 = (await client.post("/api/scans", json={"url": "karimshop.com"})).json()["token"]
    await worker.wait_inline()
    await client.post(f"/api/scans/{t1}/callback")
    await sign_in(client, "second@cafe.com")
    await client.post("/api/scans", json={"url": "cafe.com"})
    await worker.wait_inline()
    client.cookies.clear()

    await add_staff()
    await staff_sign_in(client)

    stats = (await client.get("/api/admin/stats")).json()
    assert stats["leads_7d"] == 2 and stats["callbacks_waiting"] == 1 and stats["scans_today"] == 2

    data = (await client.get("/api/admin/leads")).json()
    assert data["total"] == 2 and data["leads"][0]["email"] == "first@shop.com"  # call requests first
    assert data["leads"][0]["latest_scan"]["host"] == "karimshop.com"
    assert (await client.get("/api/admin/leads", params={"callback": True})).json()["total"] == 1
    assert (await client.get("/api/admin/leads", params={"q": "cafe"})).json()["leads"][0]["email"] == "second@cafe.com"

    lead_id = data["leads"][0]["id"]
    detail = (await client.get(f"/api/admin/leads/{lead_id}")).json()
    assert detail["scans"][0]["token"] == t1 and detail["phone"] == "01711000000"

    r = await client.patch(f"/api/admin/leads/{lead_id}", json={"sales_status": "contacted", "notes": "Called, wants a quote"})
    assert r.json()["sales_owner"] == "Nadia"
    assert (await client.get("/api/admin/stats")).json()["callbacks_waiting"] == 0
    r = await client.patch(f"/api/admin/leads/{lead_id}", json={"sales_status": "maybe"})
    assert r.status_code == 422

    r = await client.get("/api/admin/leads.csv")
    assert r.headers["content-type"].startswith("text/csv")
    rows = list(csv.reader(io.StringIO(r.text.lstrip("﻿"))))
    assert rows[0][0] == "Email" and len(rows) == 3
    karim = next(x for x in rows if x[0] == "first@shop.com")
    assert karim[1:5] == ["Karim", "Karim Shop", "01711000000", "contacted"]
    assert karim[-1] == f"https://sitescore.maktechgroup.com/scan/{t1}"
    header = rows[0]
    assert header[header.index("Health score") + 1] == "AI agent score"
    assert karim[header.index("AI agent score")] == "100"


# ---------------------------------------------------------------- report delivery problems

async def test_failed_report_is_shown_and_can_be_sent_again(client, monkeypatch):
    from sitescore import mailer, worker

    real_send = mailer.send

    async def broken_send(settings, msg):
        if msg.attachments:
            raise ConnectionRefusedError("mail server down")
        return await real_send(settings, msg)

    monkeypatch.setattr(mailer, "send", broken_send)
    await sign_in(client, "fail@business.com")
    token = (await client.post("/api/scans", json={"url": "fail.example.com"})).json()["token"]
    await worker.wait_inline()
    scan = (await client.get(f"/api/scans/{token}")).json()
    assert scan["report_status"] == "failed" and scan["report_emailed"] is False

    await add_staff()
    await staff_sign_in(client)
    leads = (await client.get("/api/admin/leads")).json()["leads"]
    lead_id = next(l["id"] for l in leads if l["email"] == "fail@business.com")
    detail = (await client.get(f"/api/admin/leads/{lead_id}")).json()
    s = detail["scans"][0]
    assert s["report_status"] == "failed" and "connect to the mail server" in s["report_error"]

    # The mail server is back: staff send it again from the dashboard.
    monkeypatch.setattr(mailer, "send", real_send)
    r = await client.post(f"/api/admin/scans/{token}/send-report")
    assert r.status_code == 200
    await worker.wait_inline()
    detail = (await client.get(f"/api/admin/leads/{lead_id}")).json()
    assert detail["scans"][0]["report_status"] == "sent" and detail["scans"][0]["report_error"] is None
    assert [m for m in mailer.OUTBOX if m.to == "fail@business.com" and m.attachments]


async def test_send_report_needs_staff_and_a_finished_scan(client):
    from sitescore import worker

    await sign_in(client, "who@business.com")
    token = (await client.post("/api/scans", json={"url": "who.example.com"})).json()["token"]
    await worker.wait_inline()
    assert (await client.post(f"/api/admin/scans/{token}/send-report")).status_code == 401
    await add_staff()
    await staff_sign_in(client)
    assert (await client.post("/api/admin/scans/nope/send-report")).status_code == 404


# ---------------------------------------------------------------- deleting leads

async def _two_leads_with_scans(client):
    await sign_in(client, "one@shop.com")
    await client.post("/api/scans", json={"url": "one.example.com"})
    await sign_in(client, "two@shop.com")
    await client.post("/api/scans", json={"url": "two.example.com"})
    await worker.wait_inline()
    client.cookies.clear()
    async with db.sessionmaker()() as s:
        from sqlalchemy import select

        return {lead.email: lead.id for lead in (await s.execute(select(db.Lead))).scalars()}


async def _counts():
    from sqlalchemy import func, select

    async with db.sessionmaker()() as s:
        return tuple([await s.scalar(select(func.count()).select_from(t)) for t in (db.Lead, db.Scan, db.CheckResultRow)])


async def test_staff_can_delete_one_lead_with_its_scans(client):
    ids = await _two_leads_with_scans(client)
    leads, scans, results = await _counts()
    assert (leads, scans) == (2, 2) and results > 0
    assert (await client.delete(f"/api/admin/leads/{ids['one@shop.com']}")).status_code == 401  # staff only
    await add_staff()
    await staff_sign_in(client)
    r = await client.delete(f"/api/admin/leads/{ids['one@shop.com']}")
    assert r.json() == {"ok": True, "scans": 1}
    assert (await client.get(f"/api/admin/leads/{ids['one@shop.com']}")).status_code == 404
    leads, scans, results_after = await _counts()
    assert (leads, scans) == (1, 1) and results_after == results // 2
    assert (await client.delete(f"/api/admin/leads/{ids['one@shop.com']}")).status_code == 404


async def test_only_admins_can_clear_all_leads_and_must_confirm(client):
    await _two_leads_with_scans(client)
    await add_staff()
    await staff_sign_in(client)
    r = await client.post("/api/admin/leads/clear", json={"confirm": "DELETE ALL"})
    assert r.status_code == 403 and r.json()["error"] == "admins_only"
    await client.post("/api/admin/logout")

    await add_staff("boss@maktech.test", role="admin")
    await staff_sign_in(client, "boss@maktech.test")
    r = await client.post("/api/admin/leads/clear", json={"confirm": "yes"})
    assert r.status_code == 422 and await _counts() != (0, 0, 0)
    r = await client.post("/api/admin/leads/clear", json={"confirm": "delete all"})
    assert r.json() == {"ok": True, "leads": 2, "scans": 2}
    assert await _counts() == (0, 0, 0)
    assert (await client.get("/api/admin/leads")).json()["total"] == 0
