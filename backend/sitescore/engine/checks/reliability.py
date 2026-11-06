"""Domain expiry and DNS health."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import httpx

from .. import guard
from ..context import DNSFailure
from ..models import Category, Outcome, Status
from .base import check

# ---------------------------------------------------------------- Domain expiry (RDAP)

IANA_BOOTSTRAP = "https://data.iana.org/rdap/dns.json"
_bootstrap: dict[str, str] | None = None
_bootstrap_lock = asyncio.Lock()


async def rdap_base_for(tld: str, client: httpx.AsyncClient) -> str | None:
    global _bootstrap
    async with _bootstrap_lock:
        if _bootstrap is None:
            r = await client.get(IANA_BOOTSTRAP)
            r.raise_for_status()
            mapping: dict[str, str] = {}
            for tlds, urls in r.json().get("services", []):
                https_urls = [u for u in urls if u.startswith("https://")] or urls
                for t in tlds:
                    mapping[t.lower()] = https_urls[0]
            _bootstrap = mapping
    return _bootstrap.get(tld.lower())


def parse_rdap_expiry(data: dict) -> datetime | None:
    for event in data.get("events", []):
        if event.get("eventAction") == "expiration" and event.get("eventDate"):
            raw = event["eventDate"].replace("Z", "+00:00")
            try:
                dt = datetime.fromisoformat(raw)
            except ValueError:
                continue
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return None


@check("domain_expiry", "Domain expiry", Category.RELIABILITY, 4)
async def check_domain_expiry(ctx) -> Outcome:
    tld = ctx.apex.rsplit(".", 1)[-1]
    try:
        async with httpx.AsyncClient(timeout=ctx.settings.http_timeout, follow_redirects=True) as c:
            base = await rdap_base_for(tld, c)
            if not base:
                return Outcome(Status.NOT_CHECKED, {"tld": tld}, "no_rdap")
            url = base.rstrip("/") + "/domain/" + ctx.apex
            r = await c.get(url, headers={"Accept": "application/rdap+json"})
    except httpx.HTTPError as exc:
        return Outcome(Status.NOT_CHECKED, {"error": type(exc).__name__}, "lookup_failed")
    if r.status_code != 200:
        return Outcome(Status.NOT_CHECKED, {"http_status": r.status_code}, "lookup_failed")
    try:
        expires = parse_rdap_expiry(r.json())
    except ValueError:
        expires = None
    if not expires:
        return Outcome(Status.NOT_CHECKED, {}, "no_date")
    days = (expires - datetime.now(timezone.utc)).days
    ev = {"expires": expires.date().isoformat(), "days_left": days}
    if days > 60:
        return Outcome(Status.PASS, ev, "ok")
    if days >= 15:
        return Outcome(Status.WARN, ev, "soon")
    return Outcome(Status.FAIL, ev, "very_soon")


# ---------------------------------------------------------------- DNS health


@check("dns", "DNS health", Category.RELIABILITY, 4)
async def check_dns(ctx) -> Outcome:
    try:
        nameservers = await ctx.dns.ns(ctx.apex)
    except DNSFailure as exc:
        return Outcome(Status.NOT_CHECKED, {"error": str(exc)}, "lookup_failed")
    if not nameservers:
        # Real domains always have NS records; an empty answer means our resolver failed.
        return Outcome(Status.NOT_CHECKED, {"nameservers": []}, "lookup_failed")

    async def answers(ns: str) -> bool:
        try:
            ips = await ctx.dns.a(ns)
        except DNSFailure:
            return False
        public = [ip for ip in ips if guard.is_public_ip(ip)]
        if not public:
            return False  # never query private or internal addresses
        return await ctx.dns.soa_at(public[0], ctx.apex)

    results = await asyncio.gather(*(answers(n) for n in nameservers))
    responding = [n for n, ok in zip(nameservers, results) if ok]
    try:
        caa = await ctx.dns.caa(ctx.apex)
    except DNSFailure:
        caa = []
    ev = {
        "nameservers": nameservers,
        "responding": responding,
        "not_responding": [n for n in nameservers if n not in responding],
        "caa": bool(caa),
    }
    if len(nameservers) < 2:
        return Outcome(Status.FAIL, ev, "single_ns")
    if not responding:
        return Outcome(Status.FAIL, ev, "none_responding")
    if len(responding) < len(nameservers):
        return Outcome(Status.WARN, ev, "some_lame")
    return Outcome(Status.PASS, ev, "ok")
