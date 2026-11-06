"""Email authentication (SPF, DKIM, DMARC) and blocklists."""
from __future__ import annotations

import asyncio
import ipaddress
import re

from ..context import DNSFailure
from ..models import Category, Outcome, Status
from .base import check

# ---------------------------------------------------------------- SPF

LOOKUP_MECHANISMS = ("include", "a", "mx", "ptr", "exists")
_ALL_RE = re.compile(r"^([+\-~?]?)all$", re.I)


def spf_records(txts: list[str]) -> list[str]:
    return [t.strip() for t in txts if t.strip().lower().startswith("v=spf1")]


def parse_spf(record: str) -> dict:
    """Split an SPF record into the parts we care about."""
    terms = record.split()[1:]
    out = {"all": None, "includes": [], "redirect": None, "lookups": 0}
    for raw in terms:
        term = raw.lower()
        m = _ALL_RE.match(term)
        if m:
            out["all"] = m.group(1) or "+"
            continue
        if term.startswith("redirect="):
            out["redirect"] = raw.split("=", 1)[1]
            out["lookups"] += 1
            continue
        mech = term.lstrip("+-~?").split(":", 1)[0].split("/", 1)[0]
        if mech in LOOKUP_MECHANISMS:
            out["lookups"] += 1
            if mech == "include" and ":" in raw:
                out["includes"].append(raw.split(":", 1)[1])
    return out


async def count_spf_lookups(dns, domain: str, seen: set[str] | None = None, depth: int = 0) -> tuple[int, list[str]]:
    """Total DNS lookups an SPF check of `domain` needs (RFC 7208 limit: 10)."""
    seen = seen if seen is not None else set()
    problems: list[str] = []
    if depth > 10 or domain.lower() in seen:
        return 0, problems
    seen.add(domain.lower())
    records = spf_records(await dns.txt(domain))
    if len(records) != 1:
        if depth:
            problems.append(domain)
        return 0, problems
    parsed = parse_spf(records[0])
    total = parsed["lookups"]
    for target in parsed["includes"] + ([parsed["redirect"]] if parsed["redirect"] else []):
        n, p = await count_spf_lookups(dns, target, seen, depth + 1)
        total += n
        problems += p
    return total, problems


@check("spf", "SPF", Category.EMAIL, 4)
async def check_spf(ctx) -> Outcome:
    if not await ctx.dns_ok():
        return Outcome(Status.NOT_CHECKED, {}, "lookup_failed")
    try:
        records = spf_records(await ctx.dns.txt(ctx.apex))
        if not records:
            return Outcome(Status.FAIL, {}, "missing")
        if len(records) > 1:
            return Outcome(Status.FAIL, {"records": records}, "multiple")
        parsed = parse_spf(records[0])
        lookups, broken = await count_spf_lookups(ctx.dns, ctx.apex)
    except DNSFailure as exc:
        return Outcome(Status.NOT_CHECKED, {"error": str(exc)}, "lookup_failed")
    all_q = parsed["all"]
    if all_q is None and parsed["redirect"]:
        try:
            target = spf_records(await ctx.dns.txt(parsed["redirect"]))
        except DNSFailure:
            target = []
        if target:
            all_q = parse_spf(target[0])["all"]
    ev = {"record": records[0], "all": all_q, "lookups": lookups, "broken_includes": broken}
    if all_q == "+":
        return Outcome(Status.FAIL, ev, "plus_all")
    if lookups > 10:
        return Outcome(Status.FAIL, ev, "too_many_lookups")
    if broken:
        return Outcome(Status.WARN, ev, "broken_include")
    if all_q is None:
        return Outcome(Status.WARN, ev, "no_all")
    if all_q == "?":
        return Outcome(Status.WARN, ev, "neutral")
    if lookups >= 9:
        # One more email service added (a newsletter tool, a CRM) and SPF breaks.
        return Outcome(Status.WARN, ev, "near_limit")
    return Outcome(Status.PASS, ev, "ok")


# ---------------------------------------------------------------- DKIM


@check("dkim", "DKIM", Category.EMAIL, 3)
async def check_dkim(ctx) -> Outcome:
    if not await ctx.dns_ok():
        return Outcome(Status.NOT_CHECKED, {}, "lookup_failed")
    selectors = list(ctx.settings.dkim_selectors)

    async def probe(sel: str) -> bool | None:
        try:
            txts = await ctx.dns.txt(f"{sel}._domainkey.{ctx.apex}")
        except DNSFailure:
            return None
        return any(re.search(r"\bp=[A-Za-z0-9+/]{20,}", t) for t in txts)

    results = await asyncio.gather(*(probe(s) for s in selectors))
    found = [s for s, ok in zip(selectors, results) if ok]
    if found:
        return Outcome(Status.PASS, {"selectors": found}, "ok")
    if all(r is None for r in results):
        return Outcome(Status.NOT_CHECKED, {}, "lookup_failed")
    # We only know common selector names, so "not found" is never a fail.
    return Outcome(Status.WARN, {"tried": selectors}, "not_found")


# ---------------------------------------------------------------- DMARC


def parse_dmarc(record: str) -> dict[str, str]:
    tags = {}
    for part in record.split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            tags[k.strip().lower()] = v.strip()
    return tags


@check("dmarc", "DMARC", Category.EMAIL, 4)
async def check_dmarc(ctx) -> Outcome:
    if not await ctx.dns_ok():
        return Outcome(Status.NOT_CHECKED, {}, "lookup_failed")
    try:
        txts = await ctx.dns.txt(f"_dmarc.{ctx.apex}")
    except DNSFailure as exc:
        return Outcome(Status.NOT_CHECKED, {"error": str(exc)}, "lookup_failed")
    records = [t for t in txts if t.strip().lower().startswith("v=dmarc1")]
    if not records:
        return Outcome(Status.FAIL, {}, "missing")
    if len(records) > 1:
        return Outcome(Status.FAIL, {"records": records}, "multiple")
    tags = parse_dmarc(records[0])
    policy = tags.get("p", "").lower()
    ev = {"record": records[0], "policy": policy or None, "rua": tags.get("rua")}
    if policy in ("quarantine", "reject"):
        return Outcome(Status.PASS, ev, "ok")
    if policy == "none":
        return Outcome(Status.WARN, ev, "monitor_only")
    return Outcome(Status.FAIL, ev, "invalid")


# ---------------------------------------------------------------- Blocklists


def reverse_ipv4(ip: str) -> str:
    return ".".join(reversed(ip.split(".")))


def is_listing(answer: str) -> bool:
    """127.0.0.x means listed; 127.255.255.x is a provider error code, not a listing."""
    try:
        addr = ipaddress.ip_address(answer)
    except ValueError:
        return False
    return addr in ipaddress.ip_network("127.0.0.0/8") and not answer.startswith("127.255.255.")


@check("blacklist", "Blocklists", Category.EMAIL, 3)
async def check_blacklist(ctx) -> Outcome:
    if not await ctx.dns_ok():
        return Outcome(Status.NOT_CHECKED, {}, "lookup_failed")
    zones = list(ctx.settings.dnsbl_ip_zones)
    if not zones:
        return Outcome(Status.NOT_CHECKED, {}, "not_configured")
    try:
        mx = await ctx.dns.mx(ctx.apex)
        ips: list[str] = []
        for _, host in mx[:3]:
            for ip in await ctx.dns.a(host):
                if ip not in ips:
                    ips.append(ip)
        source = "mail server"
        if not ips:
            ips = [ip for ip in (ctx.ips or await ctx.dns.a(ctx.host)) if ":" not in ip]
            source = "website"
    except DNSFailure as exc:
        return Outcome(Status.NOT_CHECKED, {"error": str(exc)}, "lookup_failed")
    ips = [ip for ip in ips if ":" not in ip][:4]
    if not ips:
        return Outcome(Status.NOT_CHECKED, {}, "no_ip")

    async def lookup(ip: str, zone: str) -> tuple[str, str, bool | None]:
        try:
            answers = await ctx.dns.a(f"{reverse_ipv4(ip)}.{zone}")
        except DNSFailure:
            return ip, zone, None
        return ip, zone, any(is_listing(a) for a in answers)

    results = await asyncio.gather(*(lookup(ip, z) for ip in ips for z in zones))
    listed = [{"ip": ip, "list": z} for ip, z, hit in results if hit]
    ev = {"checked_ips": ips, "source": source, "lists": zones, "listed": listed}
    if listed:
        return Outcome(Status.FAIL, ev, "listed", critical=True)
    if all(hit is None for _, _, hit in results):
        return Outcome(Status.NOT_CHECKED, ev, "lookup_failed")
    return Outcome(Status.PASS, ev, "ok")


# ---------------------------------------------------------------- MTA-STS and TLS reporting


@check("mta_sts", "Encrypted mail delivery", Category.EMAIL, 1)
async def check_mta_sts(ctx) -> Outcome:
    """MTA-STS makes other mail servers deliver to you only over checked encryption; TLS-RPT
    asks them to report when that fails. Only meaningful for a domain that receives email."""
    if not await ctx.dns_ok():
        return Outcome(Status.NOT_CHECKED, {}, "lookup_failed")
    try:
        if not await ctx.dns.mx(ctx.apex):
            return Outcome(Status.NOT_CHECKED, {}, "no_mx")
        sts = any(t.strip().lower().startswith("v=stsv1") for t in await ctx.dns.txt(f"_mta-sts.{ctx.apex}"))
        rpt = any(t.strip().lower().startswith("v=tlsrptv1") for t in await ctx.dns.txt(f"_smtp._tls.{ctx.apex}"))
    except DNSFailure as exc:
        return Outcome(Status.NOT_CHECKED, {"error": str(exc)}, "lookup_failed")
    ev = {"mta_sts": sts, "tls_rpt": rpt}
    if sts:
        policy = await ctx.fetch(f"https://mta-sts.{ctx.apex}/.well-known/mta-sts.txt")
        text = policy.text.lower() if policy.ok and policy.status == 200 else ""
        mode = re.search(r"^\s*mode\s*:\s*(\w+)", text, re.M)
        if "stsv1" not in text or not mode:
            return Outcome(Status.WARN, ev, "broken_policy")
        ev["mode"] = mode.group(1)
    if sts and rpt:
        return Outcome(Status.PASS, ev, "ok")
    if sts:
        return Outcome(Status.WARN, ev, "no_tlsrpt")
    if rpt:
        return Outcome(Status.WARN, ev, "no_sts")
    return Outcome(Status.WARN, ev, "missing")
