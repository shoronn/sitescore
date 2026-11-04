"""Extra security hygiene: insecure content, cookie flags, security.txt, DNSSEC."""
from __future__ import annotations

from urllib.parse import urlsplit

from ..context import DNSFailure
from ..models import Category, Outcome, Status
from .base import check


async def _https_page(ctx):
    """The homepage, only if it was served over working HTTPS."""
    page = await ctx.main_page()
    if not page.ok or not (page.final_url or "").startswith("https://"):
        return None
    if (await ctx.fetch(f"https://{ctx.host}/")).tls_error:
        return None
    return page


@check("mixed_content", "Secure page content", Category.SECURITY, 2)
async def check_mixed_content(ctx) -> Outcome:
    page = await _https_page(ctx)
    if page is None:
        return Outcome(Status.NOT_CHECKED, {}, "no_https_page")
    info = await ctx.page_info()
    if info is None:
        return Outcome(Status.NOT_CHECKED, {}, "not_html")
    insecure = [(tag, url, kind) for tag, url, kind in info.resources if url.lower().startswith("http://")]
    active = [u for _t, u, k in insecure if k == "active"]
    passive = [u for _t, u, k in insecure if k == "passive"]
    hosts = sorted({urlsplit(u).netloc for u in active + passive if urlsplit(u).netloc})[:5]
    ev = {"active_count": len(active), "passive_count": len(passive), "hosts": hosts}
    if active:
        return Outcome(Status.FAIL, ev, "active")
    if passive:
        return Outcome(Status.WARN, ev, "passive")
    return Outcome(Status.PASS, ev, "ok")


_SESSIONISH = ("sess", "auth", "token", "login", "sid", "jwt", "remember", "wordpress_logged_in", "laravel")


def cookie_problems(set_cookies: list[str]) -> dict:
    """Which cookies lack Secure, HttpOnly (for sign-in cookies) or SameSite."""
    no_secure, no_httponly, no_samesite, names = [], [], [], []
    for raw in set_cookies:
        first, _, rest = raw.partition(";")
        name = first.split("=", 1)[0].strip()
        if not name:
            continue
        names.append(name)
        attrs = {a.strip().split("=", 1)[0].lower() for a in rest.split(";") if a.strip()}
        if "secure" not in attrs:
            no_secure.append(name)
        if "samesite" not in attrs:
            no_samesite.append(name)
        if any(k in name.lower() for k in _SESSIONISH) and "httponly" not in attrs:
            no_httponly.append(name)
    weak = sorted(set(no_secure) | set(no_samesite) | set(no_httponly))
    return {"cookies": names, "no_secure": no_secure, "no_httponly": no_httponly, "no_samesite": no_samesite, "weak": weak}


@check("cookies", "Cookie safety", Category.SECURITY, 1)
async def check_cookies(ctx) -> Outcome:
    page = await _https_page(ctx)
    if page is None:
        return Outcome(Status.NOT_CHECKED, {}, "no_https_page")
    ev = cookie_problems(page.cookies)
    if not ev["cookies"]:
        return Outcome(Status.PASS, ev, "none")
    # Sign-in cookies must be Secure and HttpOnly: without them a session can be stolen.
    signin_insecure = [n for n in ev["no_secure"] if any(k in n.lower() for k in _SESSIONISH)]
    if ev["no_httponly"] or signin_insecure:
        return Outcome(Status.FAIL, ev, "session_unsafe")
    if ev["no_secure"] or ev["no_samesite"]:
        return Outcome(Status.WARN, ev, "flags_missing")
    return Outcome(Status.PASS, ev, "ok")


@check("security_txt", "Security contact", Category.SECURITY, 1)
async def check_security_txt(ctx) -> Outcome:
    if await ctx.site_base() is None:
        return Outcome(Status.NOT_CHECKED, {}, "unreachable")
    res = await ctx.probe("/.well-known/security.txt", max_bytes=8192)
    text = res.text if res.status == 200 else ""
    has_contact = any(line.strip().lower().startswith("contact:") for line in text.splitlines())
    if has_contact and "<html" not in text[:300].lower():
        return Outcome(Status.PASS, {}, "ok")
    return Outcome(Status.WARN, {}, "missing")


@check("dnssec", "DNSSEC", Category.SECURITY, 1)
async def check_dnssec(ctx) -> Outcome:
    if not await ctx.dns_ok():
        return Outcome(Status.NOT_CHECKED, {}, "lookup_failed")
    try:
        ds = await ctx.dns.ds(ctx.apex)
    except DNSFailure:
        return Outcome(Status.NOT_CHECKED, {}, "lookup_failed")
    if ds:
        return Outcome(Status.PASS, {"ds_count": len(ds)}, "ok")
    return Outcome(Status.WARN, {}, "off")
