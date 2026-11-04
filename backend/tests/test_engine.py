"""Engine tests. DNS and HTTP are faked, so these run offline."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest

from sitescore.engine import EngineSettings, ScanContext, ScanError, Status, run_scan
from sitescore.engine import findings, guard
from sitescore.engine.checks import CHECKS, TOTAL_WEIGHT, email, performance, reliability, web
from sitescore.engine.context import DNSFailure
from sitescore.engine.models import Category, CheckResult
from sitescore.engine.scoring import score_results


# ---------------------------------------------------------------- fakes

class FakeDNS:
    def __init__(self, records: dict | None = None, fail: set | None = None, soa_ok: bool = True):
        self.records = dict(records or {})
        self.records.setdefault(("example.com", "NS"), ["ns1.default.test", "ns2.default.test"])
        self.fail = fail or set()
        self.soa_ok = soa_ok

    def _get(self, name, rtype):
        if (name, rtype) in self.fail:
            raise DNSFailure("fake failure")
        return self.records.get((name, rtype), [])

    async def txt(self, name): return self._get(name, "TXT")
    async def a(self, name): return self._get(name, "A")
    async def aaaa(self, name): return self._get(name, "AAAA")
    async def mx(self, name): return self._get(name, "MX")
    async def ns(self, name): return self._get(name, "NS")
    async def caa(self, name): return self._get(name, "CAA")
    async def ds(self, name): return self._get(name, "DS")
    async def soa_at(self, ip, zone): return self.soa_ok if ip != "1.0.0.1" else False


def make_ctx(dns=None, handler=None, target="example.com", settings=None):
    transport = httpx.MockTransport(handler or (lambda req: httpx.Response(200, text="ok")))
    client = httpx.AsyncClient(transport=transport, follow_redirects=False)
    return ScanContext(target, settings=settings or EngineSettings(skip_speed_test=True),
                       http_client=client, dns_client=dns or FakeDNS(), skip_guard=True)


# ---------------------------------------------------------------- registry + wording

def test_health_and_agent_checks_each_worth_100_points():
    from sitescore.engine.checks import AGENT_KEYS, AGENT_WEIGHT

    assert len(CHECKS) == 30
    assert TOTAL_WEIGHT == 100 and AGENT_WEIGHT == 100
    by_cat = {}
    for c in CHECKS:
        by_cat[c.category] = by_cat.get(c.category, 0) + c.weight
    # Reliability: uptime 9, domain expiry 5, DNS 5 (the backup question is gone).
    # Performance: mobile speed 9, Core Web Vitals 6.
    assert by_cat == {Category.SECURITY: 40, Category.RELIABILITY: 19, Category.EMAIL: 16,
                      Category.PERFORMANCE: 15, Category.SEO: 10, Category.AGENT: 100}
    assert [c.key for c in CHECKS[:len(AGENT_KEYS)]] == AGENT_KEYS
    # llms.txt is shown for information only.
    assert next(c for c in CHECKS if c.key == "llms_txt").weight == 0
    # Report order groups the checks by category, in the category order.
    order = [c.category for c in CHECKS]
    # AI agent readiness first, then the health areas in their order.
    from sitescore.engine.models import HEALTH_CATEGORIES

    area_order = [Category.AGENT, *HEALTH_CATEGORIES]
    assert order == sorted(order, key=area_order.index)


def test_every_reason_a_check_can_return_has_wording():
    """Each reason code used in the checks has a finding, so no result shows a bare name."""
    import inspect
    import re as _re

    from sitescore.engine.checks import base

    for c in base.REGISTRY:
        src = inspect.getsource(c.fn)
        pairs = []
        for line in src.splitlines():
            m = _re.search(r"Outcome\(Status\.(PASS|WARN|FAIL|NOT_CHECKED),(.*)", line)
            if m:
                words = _re.findall(r"\"(\w+)\"", m.group(2).split("critical=")[0])
                if words:
                    pairs.append((m.group(1), words[-1]))
        assert pairs, c.key
        for status, reason in pairs:
            if status == "NOT_CHECKED":
                assert reason in findings.NOT_CHECKED, (c.key, reason)
            else:
                assert reason in findings.FINDINGS.get(c.key, {}), (c.key, reason)


def test_wording_has_no_dashes_and_valid_offers():
    offers = {"none", "fixit", "cloudcare", "email_setup", "security_shield"}
    for key, reasons in findings.FINDINGS.items():
        for reason, entry in reasons.items():
            for field in ("title", "summary", "why", "fix"):
                assert "\u2014" not in entry[field] and "\u2013" not in entry[field], (key, reason)
            assert entry["offer"] in offers, (key, reason)
    for text in findings.NOT_CHECKED.values():
        assert "\u2014" not in text and "\u2013" not in text


# ---------------------------------------------------------------- guard

@pytest.mark.parametrize("raw,host,apex", [
    ("example.com", "example.com", "example.com"),
    ("https://WWW.Example.com/about?x=1", "www.example.com", "example.com"),
    ("shop.example.com.bd", "shop.example.com.bd", "example.com.bd"),
    ("http://example.co.uk:443/", "example.co.uk", "example.co.uk"),
])
def test_normalize_target(raw, host, apex):
    assert guard.normalize_target(raw) == (host, apex)


@pytest.mark.parametrize("raw", ["", "localhost", "192.168.1.1", "ftp://example.com", "example.com:8080",
                                 "exa mple.com", "-bad-.com", "com"])
def test_normalize_target_rejects(raw):
    with pytest.raises(ScanError):
        guard.normalize_target(raw)


@pytest.mark.parametrize("ip,ok", [
    ("8.8.8.8", True), ("10.0.0.1", False), ("127.0.0.1", False), ("169.254.169.254", False),
    ("192.168.0.10", False), ("100.64.0.1", False), ("::1", False), ("::ffff:10.0.0.1", False),
    ("2606:4700::1111", True),
])
def test_public_ip(ip, ok):
    assert guard.is_public_ip(ip) is ok


def test_blocked_networks():
    guard.set_blocked_networks(["8.8.8.0/24"])
    try:
        assert guard.is_public_ip("8.8.8.8") is False
    finally:
        guard.set_blocked_networks([])


def test_redirect_to_private_host_is_refused(monkeypatch):
    def handler(req):
        return httpx.Response(302, headers={"location": "http://internal.example/"})

    ctx = make_ctx(handler=handler)
    ctx.skip_guard = False

    def fake_guard(host):
        if host == "internal.example":
            raise ScanError("private", "private address")
        return ["93.184.216.34"]

    monkeypatch.setattr(guard, "assert_public_host", fake_guard)

    async def go():
        return await ctx.fetch("https://example.com/")

    import asyncio
    res = asyncio.run(go())
    assert res.error == "private address"
    assert res.status is None


# ---------------------------------------------------------------- web checks

def site(headers=None, https=True, redirect=True, html="<html></html>", status=200):
    headers = headers or {}

    def handler(req: httpx.Request):
        if req.url.scheme == "http":
            if redirect:
                return httpx.Response(301, headers={"location": f"https://{req.url.host}/"})
            return httpx.Response(200, text=html)
        if not https:
            raise httpx.ConnectError("connection refused")
        return httpx.Response(status, headers=headers, text=html)

    return handler


async def test_https_pass():
    ctx = make_ctx(handler=site({"strict-transport-security": "max-age=31536000"}))
    out = await web.check_https(ctx)
    assert out.status == Status.PASS


async def test_https_no_hsts_warns():
    out = await web.check_https(make_ctx(handler=site()))
    assert (out.status, out.reason) == (Status.WARN, "no_hsts")


async def test_https_no_redirect_warns():
    out = await web.check_https(make_ctx(handler=site({"strict-transport-security": "max-age=1"}, redirect=False)))
    assert out.reason == "no_redirect"


async def test_https_missing_fails_critical():
    out = await web.check_https(make_ctx(handler=site(https=False, redirect=False)))
    assert out.status == Status.FAIL and out.critical


async def test_headers_counts():
    full = {
        "strict-transport-security": "max-age=600", "content-security-policy": "default-src 'self'",
        "x-content-type-options": "nosniff", "x-frame-options": "DENY", "referrer-policy": "no-referrer",
    }
    assert (await web.check_headers(make_ctx(handler=site(full)))).status == Status.PASS
    some = {"x-content-type-options": "nosniff", "content-security-policy": "frame-ancestors 'none'"}
    out = await web.check_headers(make_ctx(handler=site(some)))
    assert out.status == Status.WARN and out.evidence["count"] == 3  # CSP frame-ancestors counts twice
    assert (await web.check_headers(make_ctx(handler=site({})))).status == Status.FAIL


def test_detect_software():
    found = web.detect_software(
        {"server": "Apache/2.4.57 (Ubuntu) OpenSSL/1.1.1f", "x-powered-by": "PHP/7.4.33"},
        '<meta name="generator" content="WordPress 6.4.2" />',
    )
    names = {(f["product"], f["version"]): f["outdated"] for f in found}
    assert names[("apache", "2.4.57")] is False
    assert names[("openssl", "1.1.1f")] is True
    assert names[("php", "7.4.33")] is True
    assert names[("wordpress", "6.4.2")] is True
    assert web.detect_software({"server": "nginx"}, "") == []
    current = web.detect_software({"x-powered-by": "PHP/8.3.12"}, '<meta content="WordPress 7.1.3" name="generator">')
    assert all(not f["outdated"] for f in current) and len(current) == 2


async def test_software_statuses():
    assert (await web.check_software(make_ctx(handler=site({"server": "cloudflare"})))).status == Status.PASS
    assert (await web.check_software(make_ctx(handler=site({"server": "nginx/1.24.0"})))).status == Status.WARN
    out = await web.check_software(make_ctx(handler=site({"x-powered-by": "PHP/7.2.1"})))
    assert out.status == Status.FAIL and out.evidence["outdated"] == ["php 7.2.1"]


async def test_uptime_pass_and_down():
    out = await web.check_uptime(make_ctx(handler=site()))
    assert out.status == Status.PASS and len(out.evidence["samples_ms"]) == 3
    out = await web.check_uptime(make_ctx(handler=site(status=503)))
    assert out.status == Status.FAIL


async def test_ssl_outcomes(monkeypatch):
    def probe(result, legacy=False):
        monkeypatch.setattr(web, "_probe_tls", lambda h, t, a=None: dict(result))
        monkeypatch.setattr(web, "_legacy_tls", lambda h, t, a=None: legacy)

    probe({"verified": True, "days_left": 80, "expires": "2027-01-01"})
    assert (await web.check_ssl(make_ctx())).status == Status.PASS
    probe({"verified": True, "days_left": 80}, legacy=True)
    assert (await web.check_ssl(make_ctx())).reason == "legacy_tls"
    # Auto-renewed certificates sit near 30 days for a while: that is fine. Two weeks is not.
    probe({"verified": True, "days_left": 29})
    assert (await web.check_ssl(make_ctx())).status == Status.PASS
    probe({"verified": True, "days_left": 12})
    assert (await web.check_ssl(make_ctx())).status == Status.WARN
    probe({"verified": True, "days_left": 5})
    assert (await web.check_ssl(make_ctx())).status == Status.FAIL
    probe({"verified": False, "verify_error": "certificate has expired", "days_left": -3})
    out = await web.check_ssl(make_ctx())
    assert out.reason == "expired" and out.critical
    probe({"verified": False, "verify_error": "Hostname mismatch, certificate is not valid", "days_left": 50})
    assert (await web.check_ssl(make_ctx())).reason == "hostname"
    probe({"verified": False, "connect_error": "ConnectionRefusedError"})
    assert (await web.check_ssl(make_ctx())).reason == "no_https"


# ---------------------------------------------------------------- email checks

def test_parse_spf():
    p = email.parse_spf("v=spf1 include:_spf.google.com a mx ip4:1.2.3.4 ~all")
    assert p["all"] == "~" and p["lookups"] == 3 and p["includes"] == ["_spf.google.com"]
    assert email.parse_spf("v=spf1 -all")["all"] == "-"
    assert email.parse_spf("v=spf1 all")["all"] == "+"
    assert email.parse_spf("v=spf1 redirect=_spf.example.net")["redirect"] == "_spf.example.net"


async def test_spf_pass_and_lookup_limit():
    dns = FakeDNS({
        ("example.com", "TXT"): ["v=spf1 include:a.test include:b.test ~all", "google-site-verification=x"],
        ("a.test", "TXT"): ["v=spf1 ip4:1.1.1.1 -all"],
        ("b.test", "TXT"): ["v=spf1 a mx -all"],
    })
    out = await email.check_spf(make_ctx(dns))
    assert out.status == Status.PASS and out.evidence["lookups"] == 4

    many = {("example.com", "TXT"): ["v=spf1 " + " ".join(f"include:i{i}.test" for i in range(6)) + " -all"]}
    for i in range(6):
        many[(f"i{i}.test", "TXT")] = ["v=spf1 a mx -all"]
    out = await email.check_spf(make_ctx(FakeDNS(many)))
    assert (out.status, out.reason) == (Status.FAIL, "too_many_lookups") and out.evidence["lookups"] == 18


@pytest.mark.parametrize("records,status,reason", [
    ([], Status.FAIL, "missing"),
    (["v=spf1 -all", "v=spf1 a -all"], Status.FAIL, "multiple"),
    (["v=spf1 +all"], Status.FAIL, "plus_all"),
    (["v=spf1 a ?all"], Status.WARN, "neutral"),
    (["v=spf1 a"], Status.WARN, "no_all"),
    (["v=spf1 include:gone.test -all"], Status.WARN, "broken_include"),
])
async def test_spf_problems(records, status, reason):
    out = await email.check_spf(make_ctx(FakeDNS({("example.com", "TXT"): records})))
    assert (out.status, out.reason) == (status, reason)


async def test_broken_resolver_gives_not_checked():
    dns = FakeDNS({("example.com", "NS"): []})
    for fn in (email.check_spf, email.check_dkim, email.check_dmarc, email.check_blacklist, reliability.check_dns):
        assert (await fn(make_ctx(dns))).status == Status.NOT_CHECKED, fn.__name__


async def test_spf_dns_failure_not_checked():
    out = await email.check_spf(make_ctx(FakeDNS(fail={("example.com", "TXT")})))
    assert out.status == Status.NOT_CHECKED


async def test_dkim():
    key = "v=DKIM1; k=rsa; p=MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA"
    out = await email.check_dkim(make_ctx(FakeDNS({("google._domainkey.example.com", "TXT"): [key]})))
    assert out.status == Status.PASS and out.evidence["selectors"] == ["google"]
    out = await email.check_dkim(make_ctx(FakeDNS()))
    assert (out.status, out.reason) == (Status.WARN, "not_found")


@pytest.mark.parametrize("records,status", [
    (["v=DMARC1; p=reject; rua=mailto:d@example.com"], Status.PASS),
    (["v=DMARC1; p=quarantine"], Status.PASS),
    (["v=DMARC1; p=none"], Status.WARN),
    (["v=DMARC1; rua=mailto:x@y.z"], Status.FAIL),
    ([], Status.FAIL),
    (["v=DMARC1; p=none", "v=DMARC1; p=reject"], Status.FAIL),
])
async def test_dmarc(records, status):
    out = await email.check_dmarc(make_ctx(FakeDNS({("_dmarc.example.com", "TXT"): records})))
    assert out.status == status


async def test_blacklist():
    base = {("example.com", "MX"): [(10, "mx.example.com")], ("mx.example.com", "A"): ["198.51.100.7"]}
    out = await email.check_blacklist(make_ctx(FakeDNS(dict(base))))
    assert out.status == Status.PASS and out.evidence["source"] == "mail server"
    listed = dict(base)
    listed[("7.100.51.198.bl.spamcop.net", "A")] = ["127.0.0.2"]
    out = await email.check_blacklist(make_ctx(FakeDNS(listed)))
    assert out.status == Status.FAIL and out.critical and out.evidence["listed"][0]["list"] == "bl.spamcop.net"
    errcode = dict(base)
    errcode[("7.100.51.198.bl.spamcop.net", "A")] = ["127.255.255.254"]
    assert (await email.check_blacklist(make_ctx(FakeDNS(errcode)))).status == Status.PASS


# ---------------------------------------------------------------- reliability checks

async def test_dns_health():
    recs = {("example.com", "NS"): ["ns1.host.test", "ns2.host.test"],
            ("ns1.host.test", "A"): ["8.8.8.8"], ("ns2.host.test", "A"): ["8.8.4.4"]}
    assert (await reliability.check_dns(make_ctx(FakeDNS(recs)))).status == Status.PASS
    recs[("ns2.host.test", "A")] = ["1.0.0.1"]  # does not answer
    out = await reliability.check_dns(make_ctx(FakeDNS(recs)))
    assert out.reason == "some_lame" and out.evidence["not_responding"] == ["ns2.host.test"]
    single = {("example.com", "NS"): ["ns1.host.test"], ("ns1.host.test", "A"): ["8.8.8.8"]}
    assert (await reliability.check_dns(make_ctx(FakeDNS(single)))).reason == "single_ns"


def test_rdap_expiry_parse():
    data = {"events": [{"eventAction": "registration", "eventDate": "2001-01-01T00:00:00Z"},
                       {"eventAction": "expiration", "eventDate": "2027-03-05T04:00:00Z"}]}
    assert reliability.parse_rdap_expiry(data).date().isoformat() == "2027-03-05"
    assert reliability.parse_rdap_expiry({"events": []}) is None


# ---------------------------------------------------------------- performance (built-in speed test)

LHR = {
    "lighthouseVersion": "13.5.0",
    "categories": {"performance": {"score": 0.62}},
    "audits": {"largest-contentful-paint": {"numericValue": 3100.0},
               "cumulative-layout-shift": {"numericValue": 0.05},
               "first-contentful-paint": {"numericValue": 1500.0},
               "total-blocking-time": {"numericValue": 230.0},
               "speed-index": {"numericValue": 2600.0}},
}


def test_lab_metrics():
    from sitescore.engine.speedtest import lab_metrics

    assert lab_metrics(LHR) == {"source": "lab", "score": 62, "lcp_s": 3.1, "cls": 0.05, "fcp_s": 1.5,
                                "tbt_ms": 230, "si_s": 2.6, "lighthouse": "13.5.0"}


async def test_performance_checks():
    ctx = make_ctx()

    async def fake_speed():
        return {"lhr": LHR}

    ctx.speed_test = fake_speed
    assert (await performance.check_mobile_speed(ctx)).status == Status.WARN
    vitals = await performance.check_web_vitals(ctx)
    assert vitals.status == Status.WARN and vitals.evidence["tbt_ms"] == 230


@pytest.mark.parametrize("lcp,cls,tbt,status", [
    (2000, 0.05, 150, Status.PASS), (3000, 0.05, 150, Status.WARN), (2000, 0.2, 150, Status.WARN),
    (2000, 0.05, 400, Status.WARN), (4500, 0.05, 150, Status.FAIL), (2000, 0.3, 150, Status.FAIL),
    (2000, 0.05, 700, Status.FAIL)])
async def test_web_vitals_thresholds(lcp, cls, tbt, status):
    ctx = make_ctx()
    lhr = {"categories": {"performance": {"score": 0.9}}, "audits": {
        "largest-contentful-paint": {"numericValue": lcp}, "cumulative-layout-shift": {"numericValue": cls},
        "total-blocking-time": {"numericValue": tbt}}}

    async def fake_speed():
        return {"lhr": lhr}

    ctx.speed_test = fake_speed
    assert (await performance.check_web_vitals(ctx)).status == status


@pytest.mark.parametrize("error,detail,reason", [
    ("timeout", "x", "speed_failed"), ("busy", "x", "speed_failed"), ("low_memory", "x", "speed_failed"),
    ("NO_FCP", "x", "speed_page_error"), ("unreachable", "x", "unreachable"),
    ("ERRORED_DOCUMENT_REQUEST", "Lighthouse was unable to reliably load the page. (Status code: 403)", "speed_blocked"),
    ("ERRORED_DOCUMENT_REQUEST", "Lighthouse was unable to reliably load the page. (Status code: 500)", "speed_page_error")])
async def test_speed_test_failures_are_not_checked(error, detail, reason):
    ctx = make_ctx()

    async def failed():
        return {"error": error, "detail": detail}

    ctx.speed_test = failed
    out = await performance.check_mobile_speed(ctx)
    assert out.status == Status.NOT_CHECKED and out.reason == reason and out.evidence["error"] == error


# ---------------------------------------------------------------- scoring + full run

def _result(key, cat, weight, status, critical=False):
    from sitescore.engine.scoring import points_for
    return CheckResult(key, key, cat, weight, status, points_for(status, weight), "", "", "", "", "none",
                       critical, {}, 0)


def test_scoring_and_cap():
    rs = [_result("a", Category.SECURITY, 10, Status.PASS), _result("b", Category.EMAIL, 10, Status.WARN),
          _result("c", Category.EMAIL, 6, Status.NOT_CHECKED)]
    score, capped, cats = score_results(rs)
    assert score == 75 and not capped
    email_cat = next(c for c in cats if c.category == Category.EMAIL)
    assert (email_cat.earned, email_cat.available, email_cat.score) == (5.0, 10, 50)
    rs.append(_result("d", Category.SECURITY, 1, Status.FAIL, critical=True))
    score, capped, _ = score_results(rs)
    assert score == 49 and capped
    assert score_results([_result("x", Category.EMAIL, 5, Status.NOT_CHECKED)])[0] is None


async def test_full_scan_offline(monkeypatch):
    monkeypatch.setattr(web, "_probe_tls", lambda h, t, a=None: {"verified": True, "days_left": 70, "expires": "2026-12-19"})
    monkeypatch.setattr(web, "_legacy_tls", lambda h, t, a=None: False)

    async def no_rdap(tld, client):
        return None

    monkeypatch.setattr(reliability, "rdap_base_for", no_rdap)
    dns = FakeDNS({
        ("example.com", "TXT"): ["v=spf1 -all"],
        ("_dmarc.example.com", "TXT"): ["v=DMARC1; p=none"],
        ("example.com", "NS"): ["ns1.x.test", "ns2.x.test"],
        ("ns1.x.test", "A"): ["8.8.8.8"], ("ns2.x.test", "A"): ["8.8.4.4"],
        ("example.com", "A"): ["93.184.216.34"],
    })
    ctx = make_ctx(dns, handler=site({"server": "nginx/1.24.0"}))
    seen = []
    report = await run_scan("example.com", ctx=ctx, on_result=lambda r: seen.append(r.key))
    assert len(seen) == len(CHECKS) and [r.key for r in report.results][:2] == ["robots_txt", "sitemap"]
    by_key = {r.key: r for r in report.results}
    assert by_key["domain_expiry"].status == Status.NOT_CHECKED
    assert by_key["mobile_speed"].status == Status.NOT_CHECKED
    assert by_key["software"].title == "Your server reveals its software versions"
    assert "nginx 1.24.0" in by_key["software"].summary
    assert by_key["ssl"].summary.startswith("Valid certificate, 70 days")
    assert findings.nice_date("2026-11-08") == "8 Nov 2026"
    assert by_key["headers"].summary == "None of the 5 recommended security headers are set."
    assert 0 <= report.score <= 100 and report.band in ("good", "attention", "risk")
    not_run = {"domain_expiry", "mobile_speed", "web_vitals"}
    assert {r.key for r in report.results if r.status == Status.NOT_CHECKED} == not_run
    assert report.coverage == 100 - sum(c.weight for c in CHECKS if c.key in not_run)
    # The agent checks run in the same scan and have their own score.
    assert report.agent_score is not None and 0 <= report.agent_score <= 100
    # This fake site answers every address with a 200 page: none of that counts as an exposed file.
    assert by_key["exposed_files"].status == Status.PASS and by_key["directory_listing"].status == Status.PASS
    assert by_key["mobile_viewport"].status == Status.FAIL and by_key["indexing"].status == Status.WARN
    d = report.to_dict()
    assert d["results"][0]["status"] in ("pass", "warn", "fail", "not_checked")
    for r in d["results"]:
        for field in ("title", "summary"):
            assert "?" not in r[field] or r["key"] == "ssl", (r["key"], r[field])


async def test_scan_rejects_private_target(monkeypatch):
    monkeypatch.setattr(guard, "resolve_ips", lambda host: ["10.1.2.3"])
    with pytest.raises(ScanError) as exc:
        await run_scan("intranet.example.com", settings=EngineSettings(skip_speed_test=True))
    assert exc.value.code == "private"


async def test_connections_are_pinned_to_the_checked_ip(monkeypatch):
    """DNS rebinding: the request must go to the IP that passed the guard, with the real Host and SNI."""
    seen = []

    def handler(req: httpx.Request):
        seen.append((req.url.host, req.headers["host"], req.extensions.get("sni_hostname")))
        return httpx.Response(200, text="ok")

    calls = {"n": 0}

    def rebinding_dns(host):
        calls["n"] += 1
        return ["93.184.216.34", "2606:2800:220:1::248"]

    monkeypatch.setattr(guard, "assert_public_host", rebinding_dns)
    ctx = make_ctx(handler=handler)
    ctx.skip_guard = False
    res = await ctx.fetch("https://example.com/path")
    assert res.ok and seen == [("93.184.216.34", "example.com", "example.com")]
    status, ttfb, err = await ctx.timed_get("http://example.com:443/")
    assert status == 200 and seen[-1][:2] == ("93.184.216.34", "example.com:443")


async def test_dns_check_skips_private_nameserver_addresses():
    queried = []

    class Spy(FakeDNS):
        async def soa_at(self, ip, zone):
            queried.append(ip)
            return True

    recs = {("example.com", "NS"): ["ns1.evil.test", "ns2.evil.test"],
            ("ns1.evil.test", "A"): ["10.0.0.5"], ("ns2.evil.test", "A"): ["8.8.4.4"]}
    out = await reliability.check_dns(make_ctx(Spy(recs)))
    assert queried == ["8.8.4.4"] and out.evidence["not_responding"] == ["ns1.evil.test"]


def _make_tls_server(tmp_path, hostname: str):
    """A local HTTPS server whose certificate is valid only for `hostname`, signed by a test CA."""
    import datetime as dt
    import http.server
    import ssl
    import threading

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    now = dt.datetime.now(dt.timezone.utc)
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "SiteScore Test CA")])
    ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name).public_key(ca_key.public_key())
          .serial_number(1).not_valid_before(now - dt.timedelta(days=1)).not_valid_after(now + dt.timedelta(days=2))
          .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
          .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=False,
                                       data_encipherment=False, key_agreement=False, key_cert_sign=True,
                                       crl_sign=True, encipher_only=False, decipher_only=False), critical=True)
          .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
          .sign(ca_key, hashes.SHA256()))
    key = ec.generate_private_key(ec.SECP256R1())
    cert = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hostname)]))
            .issuer_name(ca_name).public_key(key.public_key()).serial_number(2)
            .not_valid_before(now - dt.timedelta(days=1)).not_valid_after(now + dt.timedelta(days=2))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(hostname)]), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
            .sign(ca_key, hashes.SHA256()))
    (tmp_path / "ca.pem").write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    (tmp_path / "cert.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    (tmp_path / "key.pem").write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                         serialization.NoEncryption()))

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = f"host={self.headers.get('Host')}".encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    sctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    sctx.load_cert_chain(tmp_path / "cert.pem", tmp_path / "key.pem")
    server.socket = sctx.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    trust = ssl.create_default_context(cafile=str(tmp_path / "ca.pem"))
    return server, trust


async def test_pinned_tls_still_verifies_the_hostname(monkeypatch, tmp_path):
    """Pinning connects to the checked IP but must still check the certificate against the real name."""
    server, trust = _make_tls_server(tmp_path, "good.example.com")
    port = server.server_address[1]
    monkeypatch.setattr(guard, "assert_public_host", lambda host: ["127.0.0.1"])
    try:
        for host, should_pass in (("good.example.com", True), ("evil.example.com", False)):
            client = httpx.AsyncClient(verify=trust, trust_env=False)
            ctx = ScanContext(host, settings=EngineSettings(skip_speed_test=True), http_client=client,
                              dns_client=FakeDNS(), skip_guard=False)
            res = await ctx.fetch(f"https://{host}:{port}/")
            await client.aclose()
            if should_pass:
                assert res.ok and res.text == f"host={host}:{port}"
            else:
                assert not res.ok and res.tls_error, res.error
    finally:
        server.shutdown()


# ---------------------------------------------------------------- speed test timing

async def test_slow_speed_test_is_not_cut_off_by_the_normal_check_limit():
    """The speed test takes longer than other checks; its checks must wait for it, not time out."""
    import asyncio

    from sitescore.engine.runner import _run_one

    ctx = make_ctx(settings=EngineSettings(check_timeout=0.05, speed_timeout=2))

    async def slow_speed():
        await asyncio.sleep(0.3)  # longer than check_timeout
        return {"lhr": LHR}

    ctx.speed_test = slow_speed
    mobile = next(c for c in CHECKS if c.key == "mobile_speed")
    assert mobile.slow
    result = await _run_one(ctx, mobile)
    assert result.status == Status.WARN and result.evidence.get("score") == 62
    # Every other check keeps the normal, shorter limit.
    assert [c.key for c in CHECKS if c.slow] == ["mobile_speed", "web_vitals"]
