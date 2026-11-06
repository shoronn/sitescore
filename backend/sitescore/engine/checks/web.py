"""Security and reliability checks that talk to the website itself."""
from __future__ import annotations

import asyncio
import json
import re
import socket
import ssl
import statistics
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from cryptography import x509

from ..models import Category, Outcome, Status
from .base import check, parse_version

# ---------------------------------------------------------------- HTTPS


def _hsts_ok(value: str | None) -> bool:
    if not value:
        return False
    m = re.search(r"max-age\s*=\s*\"?(\d+)", value, re.I)
    return bool(m and int(m.group(1)) > 0)


@check("https", "HTTPS", Category.SECURITY, 6)
async def check_https(ctx) -> Outcome:
    https = await ctx.fetch(f"https://{ctx.host}/")
    if not https.ok and https.tls_error:
        https = await ctx.fetch(f"https://{ctx.host}/", verify=False)
    http = await ctx.fetch(f"http://{ctx.host}/")

    https_works = https.ok
    redirects = bool(http.ok and http.final_url and http.final_url.startswith("https://"))
    hsts = _hsts_ok(https.header("strict-transport-security")) if https_works else False
    ev = {
        "https_works": https_works,
        "http_redirects_to_https": redirects,
        "http_reachable": http.ok,
        "hsts": hsts,
        "final_url": https.final_url or http.final_url,
    }
    if not https_works:
        return Outcome(Status.FAIL, ev, "no_https", critical=True)
    if http.ok and not redirects:
        return Outcome(Status.WARN, ev, "no_redirect")
    if not hsts:
        return Outcome(Status.WARN, ev, "no_hsts")
    return Outcome(Status.PASS, ev, "ok")


# ---------------------------------------------------------------- SSL certificate


def _probe_tls(host: str, timeout: float, address: str | None = None) -> dict:
    """TLS handshake with `host` as the server name, connecting to `address` (the checked IP)."""
    out: dict = {"verified": False}
    address = address or host
    ctx = ssl.create_default_context()
    try:
        with socket.create_connection((address, 443), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as tls:
                out["verified"] = True
                out["tls_version"] = tls.version()
                der = tls.getpeercert(binary_form=True)
    except ssl.SSLCertVerificationError as exc:
        out["verify_error"] = exc.verify_message or str(exc)
        der = None
    except (OSError, ssl.SSLError) as exc:
        out["connect_error"] = type(exc).__name__
        return out
    if der is None:
        loose = ssl.create_default_context()
        loose.check_hostname = False
        loose.verify_mode = ssl.CERT_NONE
        try:
            with socket.create_connection((address, 443), timeout=timeout) as sock:
                with loose.wrap_socket(sock, server_hostname=host) as tls:
                    der = tls.getpeercert(binary_form=True)
                    out["tls_version"] = tls.version()
        except (OSError, ssl.SSLError):
            der = None
    if der:
        cert = x509.load_der_x509_certificate(der)
        expires = cert.not_valid_after_utc
        out["expires"] = expires.date().isoformat()
        out["days_left"] = (expires - datetime.now(timezone.utc)).days
        out["issuer"] = cert.issuer.rfc4514_string()
    return out


def _legacy_tls(host: str, timeout: float, address: str | None = None) -> bool | None:
    """True if the server still accepts TLS 1.0 or 1.1; None if we cannot tell."""
    try:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ctx.minimum_version = ssl.TLSVersion.TLSv1
        ctx.maximum_version = ssl.TLSVersion.TLSv1_1
        ctx.set_ciphers("DEFAULT:@SECLEVEL=0")
    except (ValueError, ssl.SSLError):
        return None
    try:
        with socket.create_connection((address or host, 443), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=host):
                return True
    except ssl.SSLError:
        return False
    except OSError:
        return None


@check("ssl", "SSL certificate", Category.SECURITY, 7)
async def check_ssl(ctx) -> Outcome:
    t = ctx.settings.http_timeout
    info = await asyncio.to_thread(_probe_tls, ctx.host, t, ctx.connect_address)
    if "connect_error" in info and "expires" not in info:
        return Outcome(Status.FAIL, info, "no_https", critical=True)
    legacy = await asyncio.to_thread(_legacy_tls, ctx.host, t, ctx.connect_address)
    info["legacy_tls"] = legacy
    days = info.get("days_left")
    if not info["verified"]:
        err = (info.get("verify_error") or "").lower()
        if "unable to get local issuer" in err or "unable to verify the first certificate" in err:
            # The certificate is fine but the server leaves out the middle certificate. Desktop
            # browsers often fetch it themselves; many phones, apps and other servers do not.
            return Outcome(Status.FAIL, info, "incomplete_chain")
        reason = "expired" if "expired" in err or (days is not None and days < 0) else (
            "hostname" if "hostname" in err or "ip address mismatch" in err else (
                "self_signed" if "self" in err else "invalid"))
        return Outcome(Status.FAIL, info, reason, critical=True)
    if days is not None and days <= 7:
        return Outcome(Status.FAIL, info, "expiring_soon")
    # Automatic renewal (Let's Encrypt, as Coolify and most hosts use) renews at about 30 days
    # left, so only a certificate with two weeks or less is a real sign renewal has stopped.
    if days is not None and days <= 14:
        return Outcome(Status.WARN, info, "expiring")
    if legacy:
        return Outcome(Status.WARN, info, "legacy_tls")
    return Outcome(Status.PASS, info, "ok")


# ---------------------------------------------------------------- Security headers

HEADER_LABELS = {
    "hsts": "Strict-Transport-Security",
    "csp": "Content-Security-Policy",
    "nosniff": "X-Content-Type-Options",
    "frames": "Clickjacking protection",
    "referrer": "Referrer-Policy",
}


@check("headers", "Security headers", Category.SECURITY, 4)
async def check_headers(ctx) -> Outcome:
    page = await ctx.main_page()
    if not page.ok:
        return Outcome(Status.NOT_CHECKED, {"error": page.error}, "unreachable")
    h = page.header
    csp = h("content-security-policy") or ""
    present = {
        "hsts": _hsts_ok(h("strict-transport-security")),
        "csp": bool(csp.strip()),
        "nosniff": (h("x-content-type-options") or "").lower().strip() == "nosniff",
        "frames": bool(h("x-frame-options")) or "frame-ancestors" in csp.lower(),
        "referrer": bool(h("referrer-policy")),
    }
    count = sum(present.values())
    ev = {
        "present": [HEADER_LABELS[k] for k, v in present.items() if v],
        "missing": [HEADER_LABELS[k] for k, v in present.items() if not v],
        "count": count,
    }
    if count >= 4:
        return Outcome(Status.PASS, ev, "ok")
    if count >= 2:
        return Outcome(Status.WARN, ev, "some_missing")
    return Outcome(Status.FAIL, ev, "none_set" if count == 0 else "most_missing")


# ---------------------------------------------------------------- Software versions

_VERSIONS = json.loads((Path(__file__).parent.parent / "data" / "software_versions.json").read_text())
MIN_SUPPORTED = {k: parse_version(v) for k, v in _VERSIONS["min_supported"].items()}

_PRODUCT_RE = re.compile(r"\b(nginx|apache|openssl|php|openresty|litespeed|microsoft-iis)/(\d+(?:\.\d+)*[a-z]?)", re.I)
_GENERATOR_RE = re.compile(
    r"<meta[^>]+name=[\"']generator[\"'][^>]+content=[\"']([^\"']+)[\"']"
    r"|<meta[^>]+content=[\"']([^\"']+)[\"'][^>]+name=[\"']generator[\"']",
    re.I,
)
_CMS_RE = re.compile(r"\b(wordpress|drupal|joomla!?)\s+(\d+(?:\.\d+)*)", re.I)


def detect_software(headers: dict[str, str], html: str) -> list[dict]:
    found: list[dict] = []

    def add(product: str, version: str, where: str) -> None:
        product = product.lower().rstrip("!")
        if any(f["product"] == product and f["version"] == version for f in found):
            return
        entry = {"product": product, "version": version, "where": where, "outdated": False}
        floor = MIN_SUPPORTED.get(product)
        if floor and version:
            entry["outdated"] = parse_version(version)[: len(floor)] < floor
        found.append(entry)

    for name in ("server", "x-powered-by"):
        for prod, ver in _PRODUCT_RE.findall(headers.get(name, "")):
            add(prod, ver, name)
    aspnet = headers.get("x-aspnet-version")
    if aspnet:
        add("asp.net", aspnet.strip(), "x-aspnet-version")
    for m in _GENERATOR_RE.finditer(html[:200_000]):
        content = m.group(1) or m.group(2) or ""
        for prod, ver in _CMS_RE.findall(content):
            add(prod, ver, "generator tag")
    return found


@check("software", "Software versions", Category.SECURITY, 6)
async def check_software(ctx) -> Outcome:
    page = await ctx.main_page()
    if not page.ok:
        return Outcome(Status.NOT_CHECKED, {"error": page.error}, "unreachable")
    found = detect_software(page.headers, page.text)
    ev = {"found": found}
    outdated = [f for f in found if f["outdated"]]
    if outdated:
        ev["outdated"] = [f"{f['product']} {f['version']}" for f in outdated]
        return Outcome(Status.FAIL, ev, "outdated")
    if found:
        ev["visible"] = [f"{f['product']} {f['version']}" for f in found]
        return Outcome(Status.WARN, ev, "visible")
    return Outcome(Status.PASS, ev, "ok")


# ---------------------------------------------------------------- Uptime and response time


@check("uptime", "Uptime and response time", Category.RELIABILITY, 8)
async def check_uptime(ctx) -> Outcome:
    page = await ctx.main_page()
    url = page.final_url or f"https://{ctx.host}/"
    if urlsplit(url).hostname is None:
        url = f"https://{ctx.host}/"
    samples: list[float] = []
    errors: list[str] = []
    for i in range(3):
        if i:
            await asyncio.sleep(0.7)
        status, ttfb, err = await ctx.timed_get(url)
        if err or status is None or status >= 500:
            errors.append(err or f"HTTP {status}")
        else:
            samples.append(ttfb)
    ev = {"url": url, "samples_ms": [round(s * 1000) for s in samples], "errors": errors}
    if not samples:
        return Outcome(Status.FAIL, ev, "down")
    median = statistics.median(samples)
    ev["ttfb_ms"] = round(median * 1000)
    if errors:
        return Outcome(Status.FAIL, ev, "unstable")
    if median < 0.8:
        return Outcome(Status.PASS, ev, "ok")
    if median <= 1.8:
        return Outcome(Status.WARN, ev, "slowish")
    return Outcome(Status.FAIL, ev, "slow")
