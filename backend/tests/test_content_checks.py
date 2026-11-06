"""The content, search and email checks added with the business-impact view, and the Bangla wording."""
from __future__ import annotations

import string

import httpx
import pytest

from sitescore.engine import findings
from sitescore.engine.checks import CHECKS, content, email, seo, web
from sitescore.engine.findings import FINDINGS, NOT_CHECKED, word
from sitescore.engine.findings_bn import CHECK_NAMES_BN, FINDINGS_BN, NOT_CHECKED_BN
from sitescore.engine.html import parse_page
from sitescore.engine.impact import GROUPS, impact_groups, severity
from sitescore.engine.models import Status
from sitescore.engine.speedtest import accessibility, final_screenshot, speed_fixes
from test_engine import FakeDNS, make_ctx

WORDS = " ".join(["word"] * 260)


def page(body: str = "", head: str = "", lang: str = "en", doctype: bool = True) -> str:
    return (("<!doctype html>" if doctype else "") + f'<html lang="{lang}"><head><meta charset="utf-8">{head}</head>'
            f"<body>{body}</body></html>")


def site(home: str, paths: dict | None = None, missing_status: int = 404):
    paths = paths or {}

    def handler(req: httpx.Request):
        if req.url.scheme == "http":
            return httpx.Response(301, headers={"location": f"https://{req.url.host}/"})
        if req.url.path == "/":
            return httpx.Response(200, text=home, headers={"content-type": "text/html; charset=utf-8"})
        if req.url.path in paths:
            status, body = paths[req.url.path]
            return httpx.Response(status, text=body)
        return httpx.Response(missing_status, text="Not found")

    return handler


def ctx(home: str = page(), dns=None, **kw):
    return make_ctx(dns, handler=site(home, **kw))


# ---------------------------------------------------------------- HTML reader


def test_reader_collects_headings_images_text_and_structured_data():
    info = parse_page(page(
        "<h1>Rahim <b>Traders</b></h1><p>Rice and lentils.</p><script>var hidden = 1</script>"
        '<img src="/a.png"><img src="/b.png" alt=""><h3>Prices</h3><a href="tel:+8801711000000">Call</a>',
        head='<script type="application/ld+json">{"@type": "LocalBusiness"}</script><style>.x{}</style>'))
    assert info.doctype and info.h1s == ["Rahim Traders"] and [h[0] for h in info.headings] == [1, 3]
    assert info.text == "Rahim Traders Rice and lentils. Prices Call" and info.words == 7
    assert len(info.images) == 2 and info.jsonld == ['{"@type": "LocalBusiness"}']
    assert info.anchors == ["tel:+8801711000000"] and info.scripts == 2


# ---------------------------------------------------------------- content checks


@pytest.mark.parametrize("body,reason", [
    (f"<h1>One</h1><h2>Two</h2><p>{WORDS}</p>", "ok"),
    ("<h2>No main heading</h2>", "no_h1"),
    ("<h1>One</h1><h1>Two</h1>", "many_h1"),
    ("<h1>One</h1><h3>Skipped two</h3>", "skipped"),
])
async def test_headings(body, reason):
    out = await content.check_headings(ctx(page(body)))
    assert out.reason == reason and out.status == (Status.PASS if reason == "ok" else Status.WARN)


async def test_image_descriptions():
    some = "".join(f'<img src="/p{i}.jpg" alt="Photo {i}">' for i in range(4)) + '<img src="/x.jpg">'
    most = '<img src="/a.jpg"><img src="/b.jpg"><img src="/c.jpg"><img src="/d.jpg" alt="d">'
    pixel = '<img src="/track.gif" width="1" height="1">'
    assert (await content.check_image_alt(ctx(page(some)))).reason == "some_missing"
    out = await content.check_image_alt(ctx(page(most)))
    assert (out.status, out.reason, out.evidence["missing_count"]) == (Status.FAIL, "most_missing", 3)
    assert (await content.check_image_alt(ctx(page(pixel)))).reason == "no_images"


async def test_amount_of_text():
    assert (await content.check_content_depth(ctx(page(f"<p>{WORDS}</p>")))).status == Status.PASS
    assert (await content.check_content_depth(ctx(page("<p>" + "word " * 120 + "</p>")))).reason == "thin"
    assert (await content.check_content_depth(ctx(page("<p>Hello</p>")))).status == Status.FAIL


async def test_script_built_page_is_read_after_rendering(monkeypatch):
    """A React or Vue homepage arrives empty; the content checks read the rendered page instead."""
    from sitescore.engine import speedtest
    from sitescore.engine import EngineSettings

    async def fake_render(url, **kw):
        return page(f"<h1>Built by React</h1><p>{WORDS}</p>")

    monkeypatch.setattr(speedtest, "render_dom", fake_render)
    c = make_ctx(handler=site(page('<div id="root"></div><script src="/app.js"></script>')),
                 settings=EngineSettings(skip_speed_test=True, render_pages=True))
    headings = await content.check_headings(c)
    assert headings.status == Status.PASS and headings.evidence["rendered"] is True
    depth = await content.check_content_depth(c)
    assert (depth.reason, depth.evidence["raw_words"]) == ("needs_scripts", 0)

    async def no_browser(url, **kw):
        return None

    monkeypatch.setattr(speedtest, "render_dom", no_browser)
    c = make_ctx(handler=site(page('<div id="root"></div><script src="/app.js"></script>')),
                 settings=EngineSettings(skip_speed_test=True, render_pages=True))
    assert (await content.check_content_depth(c)).reason == "script_only"


@pytest.mark.parametrize("body,found", [
    ('<a href="tel:+8801711000000">Call</a>', ["phone"]),
    ("<p>Call 01711-000000 today</p>", ["phone"]),
    ("<p>ফোন: ০১৭১১-০০০০০০</p>", ["phone"]),
    ("<p>Write to sales@rahim.com.bd</p>", ["email"]),
    ('<a href="https://wa.me/8801711000000">WhatsApp</a>', ["WhatsApp"]),
    ("<p>Founded in 1998, 2500 customers</p>", []),
])
def test_contact_details_are_recognised(body, found):
    assert content.find_contacts(parse_page(page(body))) == found


async def test_contact_check():
    assert (await content.check_contact_info(ctx(page('<a href="/contact">Contact us</a>')))).reason == "contact_page_only"
    assert (await content.check_contact_info(ctx(page("<p>Nothing here</p>")))).reason == "none"
    assert (await content.check_contact_info(ctx(page("<p>+880 1897 669234</p>")))).status == Status.PASS


async def test_page_basics():
    assert (await content.check_page_basics(ctx(page("<p>x</p>")))).status == Status.PASS
    bare = "<html><head></head><body>x</body></html>"
    out = await content.check_page_basics(make_ctx(handler=lambda req: httpx.Response(
        200, text=bare, headers={"content-type": "text/html"})))
    assert out.evidence["missing"] == ["language", "character set", "doctype"]


async def test_accessibility_from_the_speed_test():
    c = make_ctx()

    async def fake_speed():
        return {"lhr": {"categories": {"accessibility": {"score": 0.78, "auditRefs": [
            {"id": "color-contrast", "weight": 7}, {"id": "image-alt", "weight": 10}, {"id": "list", "weight": 3}]}},
            "audits": {"color-contrast": {"score": 0}, "image-alt": {"score": 0}, "list": {"score": 1}}}}

    c.speed_test = fake_speed
    out = await content.check_accessibility(c)
    assert (out.status, out.reason, out.evidence["issues"]) == (Status.WARN, "some_issues", ["image-alt", "color-contrast"])
    text = word("accessibility", "Accessibility", "warn", out.reason, out.evidence, {})
    assert "images without a description, text with too little contrast" in text["summary"]


# ---------------------------------------------------------------- search checks


async def test_canonical():
    def with_link(href):
        return page(head=f'<link rel="canonical" href="{href}">')

    assert (await seo.check_canonical(ctx(with_link("https://www.example.com/")))).status == Status.PASS
    assert (await seo.check_canonical(ctx(with_link("/")))).status == Status.PASS
    assert (await seo.check_canonical(ctx(with_link("https://other.com/")))).reason == "other_site"
    assert (await seo.check_canonical(ctx(with_link("http://example.com/")))).reason == "insecure"
    assert (await seo.check_canonical(ctx(page()))).reason == "missing"


def ld(data: str) -> str:
    return page(head=f'<script type="application/ld+json">{data}</script>')


@pytest.mark.parametrize("home,reason", [
    (ld('{"@context":"https://schema.org","@type":"LocalBusiness","name":"Rahim Traders","telephone":"+880"}'), "ok"),
    (ld('{"@graph":[{"@type":"WebSite"},{"@type":"Restaurant","name":"Kacchi","address":{"@type":"PostalAddress"}}]}'), "ok"),
    (ld('{"@type":"Organization","name":"MAKTECH"}'), "incomplete"),
    (ld('{"@type":"WebSite","name":"x"}'), "no_business"),
    (ld("{not json"), "invalid"),
    (page(), "missing"),
    (page('<div itemscope itemtype="https://schema.org/LocalBusiness">x</div>'), "ok"),
])
async def test_structured_data(home, reason):
    out = await seo.check_structured_data(ctx(home))
    assert out.reason == reason


async def test_missing_page_handling():
    assert (await seo.check_error_page(ctx(page()))).status == Status.PASS
    assert (await seo.check_error_page(ctx(page(), missing_status=200))).reason == "soft_404"
    assert (await seo.check_error_page(ctx(page(), missing_status=302))).reason == "redirects"
    assert (await seo.check_error_page(ctx(page(), missing_status=500))).reason == "server_error"


# ---------------------------------------------------------------- email and TLS


async def test_mta_sts():
    base = {("example.com", "MX"): [(10, "mx.example.com")]}
    policy = {"/.well-known/mta-sts.txt": (200, "version: STSv1\nmode: enforce\nmx: mx.example.com\nmax_age: 86400")}
    no_mx = await email.check_mta_sts(make_ctx(FakeDNS({})))
    assert (no_mx.status, no_mx.reason) == (Status.NOT_CHECKED, "no_mx")
    assert (await email.check_mta_sts(make_ctx(FakeDNS(base)))).reason == "missing"
    both = FakeDNS({**base, ("_mta-sts.example.com", "TXT"): ["v=STSv1; id=1"],
                    ("_smtp._tls.example.com", "TXT"): ["v=TLSRPTv1; rua=mailto:t@example.com"]})
    out = await email.check_mta_sts(make_ctx(both, handler=site(page(), policy)))
    assert (out.status, out.evidence["mode"]) == (Status.PASS, "enforce")
    assert (await email.check_mta_sts(make_ctx(both, handler=site(page())))).reason == "broken_policy"
    rpt_only = FakeDNS({**base, ("_smtp._tls.example.com", "TXT"): ["v=TLSRPTv1; rua=mailto:t@example.com"]})
    assert (await email.check_mta_sts(make_ctx(rpt_only))).reason == "no_sts"


async def test_spf_close_to_the_lookup_limit():
    records = {("example.com", "TXT"): ["v=spf1 " + " ".join(f"include:s{i}.test" for i in range(9)) + " -all"]}
    records.update({(f"s{i}.test", "TXT"): ["v=spf1 -all"] for i in range(9)})
    out = await email.check_spf(make_ctx(FakeDNS(records)))
    assert (out.status, out.reason, out.evidence["lookups"]) == (Status.WARN, "near_limit", 9)


async def test_incomplete_certificate_chain_is_its_own_finding(monkeypatch):
    monkeypatch.setattr(web, "_probe_tls", lambda *a: {"verified": False, "days_left": 80,
                                                       "verify_error": "unable to get local issuer certificate"})
    monkeypatch.setattr(web, "_legacy_tls", lambda *a: False)
    out = await web.check_ssl(make_ctx())
    assert (out.status, out.reason, out.critical) == (Status.FAIL, "incomplete_chain", False)


# ---------------------------------------------------------------- speed test extras


LHR = {
    "categories": {"accessibility": {"score": 0.92, "auditRefs": [{"id": "link-name", "weight": 7}]}},
    "audits": {
        "unused-javascript": {"score": 0, "details": {"type": "opportunity", "overallSavingsMs": 2900}},
        "render-blocking-insight": {"score": 0, "metricSavings": {"FCP": 950, "LCP": 0}},
        "render-blocking-resources": {"score": 0, "details": {"overallSavingsMs": 400}},
        "cache-insight": {"score": 0, "metricSavings": {"LCP": 100}},
        "server-response-time": {"score": 1, "details": {"overallSavingsMs": 900}},
        "link-name": {"score": 0},
        "final-screenshot": {"details": {"type": "screenshot", "data": "data:image/jpeg;base64,AAAA"}},
    },
}


def test_speed_fixes_accessibility_and_screenshot_from_lighthouse():
    # Biggest saving first; the same fix under its old name counts once; passed audits and
    # tiny savings are left out.
    assert speed_fixes(LHR) == [{"id": "unused-javascript", "ms": 2900}, {"id": "render-blocking-insight", "ms": 950}]
    assert accessibility(LHR) == {"score": 92, "issues": ["link-name"], "issue_total": 1}
    assert final_screenshot(LHR) == "data:image/jpeg;base64,AAAA"
    assert final_screenshot({"audits": {}}) is None
    fixes = findings.speed_fix_text(speed_fixes(LHR), "bn")
    assert fixes[0]["title"] == "অব্যবহৃত JavaScript সরান" and fixes[0]["saving"] == "প্রায় ২.৯ সেকেন্ড বাঁচবে"


# ---------------------------------------------------------------- Bangla wording


DASH = chr(0x2014)  # the long dash, which SiteScore never uses


def _fields(text: str) -> set[str]:
    return {f for _, f, _, _ in string.Formatter().parse(text) if f}


def test_every_finding_has_bangla_wording_with_the_same_placeholders():
    for key, reasons in FINDINGS.items():
        for reason, en in reasons.items():
            bn = FINDINGS_BN[key][reason]
            for field in ("title", "summary", "why", "fix"):
                assert _fields(en[field]) == _fields(bn[field]), (key, reason, field)
                assert DASH not in bn[field] and DASH not in en[field]
    assert set(NOT_CHECKED_BN) == set(NOT_CHECKED)
    assert set(CHECK_NAMES_BN) == {c.key for c in CHECKS}


def test_bangla_digits_dates_and_not_checked():
    extra = {"host": "example.com", "apex": "example.com"}
    out = word("domain_expiry", "Domain expiry", "warn", "soon", {"days_left": 12, "expires": "2026-12-20"}, extra, "bn")
    assert out["title"] == "ডোমেইনের মেয়াদ ১২ দিনে শেষ হবে"
    assert out["summary"] == "আপনার ডোমেইনের নিবন্ধন শেষ হবে ২০ ডিসেম্বর ২০২৬ তারিখে।"
    assert out["offer"] == "cloudcare"  # offers are codes, the same in every language
    out = word("mta_sts", "Encrypted mail delivery", "not_checked", "no_mx", {}, extra, "bn")
    assert out["title"] == "এনক্রিপ্টেড মেইল ডেলিভারি: পরীক্ষা করা হয়নি"
    # English is unchanged by the Bangla support.
    assert word("ssl", "SSL certificate", "pass", "ok", {"days_left": 70}, extra)["summary"].startswith(
        "Valid certificate, 70 days")


# ---------------------------------------------------------------- severity and business impact


def test_severity_and_impact_groups():
    assert severity("dmarc", "fail", "missing", 4) == "error"
    assert severity("canonical", "warn", "missing", 1) == "notice"
    assert severity("headers", "warn", "some_missing", 4) == "warning"
    assert severity("llms_txt", "warn", "missing", 0) == "notice"
    grouped = {k for _, _, keys in GROUPS for k in keys}
    assert grouped == {c.key for c in CHECKS}
    results = [{"key": "spf", "severity": "error", "title": "SPF record is missing"},
               {"key": "dkim", "severity": "good", "title": "DKIM is set up"},
               {"key": "uptime", "severity": "good", "title": "Fast"},
               {"key": "canonical", "severity": "notice", "title": "No main page address"},
               {"key": "mobile_speed", "severity": "not_checked", "title": "x"}]
    groups = {g["key"]: g for g in impact_groups(results)}
    assert groups["email"]["label"] == "Your emails may land in spam" and groups["email"]["count"] == "1 problem"
    assert groups["online"]["status"] == "good" and groups["google"]["count"] == "1 small improvement"
    assert groups["speed"]["label"] == "Page speed" and groups["speed"]["status"] == "not_checked"
    bn = {g["key"]: g for g in impact_groups(results, "bn")}
    assert bn["email"]["label"] == "আপনার ইমেইল স্প্যামে যেতে পারে" and bn["email"]["count"] == "১টি সমস্যা"
