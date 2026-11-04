"""The checks added in October 2026: exposed files, hardening, and search and sharing."""
from __future__ import annotations

import httpx

from sitescore.engine.checks import exposure, hardening, seo
from sitescore.engine.html import parse_page
from sitescore.engine.models import Status
from test_engine import FakeDNS, make_ctx

HOME = """<!doctype html><html lang="en"><head>
<title>Rahim Traders | Wholesale rice and lentils in Dhaka</title>
<meta name="description" content="Rahim Traders supplies rice, lentils and spices to shops and restaurants across Dhaka since 1998.">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta property="og:title" content="Rahim Traders"><meta property="og:image" content="https://example.com/og.png">
<link rel="icon" href="/favicon.png"></head><body><h1>Rahim Traders</h1></body></html>"""


def site(paths: dict | None = None, home: str = HOME, headers: dict | None = None, https: bool = True,
         soft404: bool = True, cookies: list[str] | None = None):
    """A fake site: `paths` maps a path to (status, body bytes or str[, headers]).

    With soft404, every other path answers 200 with the homepage, like many real sites.
    """
    paths = paths or {}

    def handler(req: httpx.Request):
        if req.url.scheme == "http":
            if https:
                return httpx.Response(301, headers={"location": f"https://{req.url.host}/"})
            return httpx.Response(200, text=home, headers={"content-type": "text/html"})
        if not https:
            raise httpx.ConnectError("refused")
        path = req.url.path
        if path in paths:
            status, body, *rest = paths[path]
            hdrs = rest[0] if rest else {}
            return httpx.Response(status, content=body.encode() if isinstance(body, str) else body, headers=hdrs)
        if path == "/":
            h = [("content-type", "text/html; charset=utf-8"), *((headers or {}).items())]
            h += [("set-cookie", c) for c in (cookies or [])]
            return httpx.Response(200, text=home, headers=h)
        if soft404:
            return httpx.Response(200, text=home, headers={"content-type": "text/html"})
        return httpx.Response(404, text="Not found")

    return handler


def ctx_for(**kw):
    dns = kw.pop("dns", None)
    return make_ctx(dns, handler=site(**kw))


# ---------------------------------------------------------------- exposed files

async def test_soft_404_sites_are_not_flagged():
    out = await exposure.check_exposed_files(ctx_for())
    assert out.status == Status.PASS and out.evidence["found"] == []


async def test_env_and_git_are_critical():
    out = await exposure.check_exposed_files(ctx_for(paths={
        "/.env": (200, "APP_NAME=Shop\nAPP_KEY=base64:abc\nDB_PASSWORD=secret\n"),
        "/.git/HEAD": (200, "ref: refs/heads/main\n"),
    }))
    assert out.status == Status.FAIL and out.critical and out.reason == "exposed"
    assert any(f.startswith("/.env") for f in out.evidence["found"])
    assert any(f.startswith("/.git/HEAD") for f in out.evidence["found"])
    # Only the path and a description are kept, never the file's contents.
    assert "secret" not in str(out.evidence)


async def test_database_dump_and_archives_are_recognised_by_content():
    out = await exposure.check_exposed_files(ctx_for(paths={
        "/backup.sql": (200, "-- MySQL dump 10.13\nCREATE TABLE users (id int);"),
        "/backup.zip": (200, b"PK\x03\x04" + b"\x00" * 40),
    }))
    assert out.status == Status.FAIL and out.critical
    assert len(out.evidence["found"]) == 2


async def test_env_lookalike_html_is_ignored():
    out = await exposure.check_exposed_files(ctx_for(paths={"/.env": (200, "<html><body>API_KEY=1\nDB=2</body></html>")}))
    assert out.status == Status.PASS


async def test_phpinfo_fails_without_capping_the_score():
    out = await exposure.check_exposed_files(ctx_for(paths={"/info.php": (200, "<title>phpinfo()</title>PHP Version 8.2.1")}))
    assert (out.status, out.reason, out.critical) == (Status.FAIL, "info_page", False)


async def test_ds_store_is_a_warning():
    out = await exposure.check_exposed_files(ctx_for(paths={"/.DS_Store": (200, b"\x00\x00\x00\x01Bud1" + b"\x00" * 20)}))
    assert (out.status, out.reason) == (Status.WARN, "minor")


async def test_exposed_files_not_checked_when_site_is_down():
    out = await exposure.check_exposed_files(make_ctx(handler=lambda req: (_ for _ in ()).throw(httpx.ConnectError("down"))))
    assert out.status == Status.NOT_CHECKED


async def test_open_folders():
    out = await exposure.check_directory_listing(ctx_for(paths={"/uploads/": (200, "<html><title>Index of /uploads</title>")}))
    assert (out.status, out.reason) == (Status.FAIL, "listed") and out.evidence["folders"] == ["/uploads/"]
    out = await exposure.check_directory_listing(ctx_for(paths={"/backup/": (200, "<h1>Index of /backup</h1>")}))
    assert out.reason == "backup_listed"
    assert (await exposure.check_directory_listing(ctx_for())).status == Status.PASS


# ---------------------------------------------------------------- hardening

async def test_mixed_content():
    active = HOME.replace("<h1>", '<script src="http://cdn.example.net/app.js"></script><h1>')
    out = await hardening.check_mixed_content(ctx_for(home=active))
    assert (out.status, out.evidence["active_count"], out.evidence["hosts"]) == (Status.FAIL, 1, ["cdn.example.net"])
    passive = HOME.replace("<h1>", '<img src="http://img.example.net/a.png"><h1>')
    assert (await hardening.check_mixed_content(ctx_for(home=passive))).status == Status.WARN
    assert (await hardening.check_mixed_content(ctx_for())).status == Status.PASS
    # A site without HTTPS is covered by the HTTPS check instead.
    assert (await hardening.check_mixed_content(ctx_for(https=False))).status == Status.NOT_CHECKED


def test_cookie_problems():
    p = hardening.cookie_problems([
        "PHPSESSID=abc; path=/",
        "_ga=GA1.1; Secure; SameSite=Lax",
        "theme=dark; Secure",
    ])
    assert p["no_httponly"] == ["PHPSESSID"] and p["no_secure"] == ["PHPSESSID"]
    assert p["weak"] == ["PHPSESSID", "theme"]


async def test_cookies_check():
    bad = await hardening.check_cookies(ctx_for(cookies=["laravel_session=x; path=/; SameSite=Lax"]))
    assert (bad.status, bad.reason) == (Status.FAIL, "session_unsafe")
    meh = await hardening.check_cookies(ctx_for(cookies=["lang=bn; Secure"]))
    assert (meh.status, meh.reason) == (Status.WARN, "flags_missing")
    good = await hardening.check_cookies(ctx_for(cookies=["sid=1; Secure; HttpOnly; SameSite=Strict"]))
    assert good.status == Status.PASS
    assert (await hardening.check_cookies(ctx_for())).reason == "none"


async def test_security_txt():
    out = await hardening.check_security_txt(ctx_for(paths={"/.well-known/security.txt": (200, "Contact: mailto:security@example.com\n")}))
    assert out.status == Status.PASS
    assert (await hardening.check_security_txt(ctx_for())).status == Status.WARN  # soft 404 page is not a security.txt


async def test_dnssec():
    on = FakeDNS({("example.com", "DS"): ["12345 13 2 ABCDEF"]})
    assert (await hardening.check_dnssec(make_ctx(on))).status == Status.PASS
    assert (await hardening.check_dnssec(make_ctx(FakeDNS()))).status == Status.WARN
    broken = FakeDNS(fail={("example.com", "DS")})
    assert (await hardening.check_dnssec(make_ctx(broken))).status == Status.NOT_CHECKED


# ---------------------------------------------------------------- search and sharing

async def test_meta_tags():
    assert (await seo.check_meta_tags(ctx_for())).status == Status.PASS
    no_title = HOME.replace("<title>Rahim Traders | Wholesale rice and lentils in Dhaka</title>", "")
    assert (await seo.check_meta_tags(ctx_for(home=no_title))).reason == "no_title"
    no_desc = HOME.replace('<meta name="description"', '<meta name="x"')
    assert (await seo.check_meta_tags(ctx_for(home=no_desc))).reason == "no_description"
    long_title = HOME.replace("Rahim Traders | Wholesale", "Rahim Traders " + "very " * 20)
    assert (await seo.check_meta_tags(ctx_for(home=long_title))).reason == "title_length"


async def test_meta_tags_not_checked_for_non_html():
    out = await seo.check_meta_tags(make_ctx(handler=lambda req: httpx.Response(200, json={"ok": True})))
    assert (out.status, out.reason) == (Status.NOT_CHECKED, "not_html")


async def test_mobile_viewport():
    assert (await seo.check_mobile_viewport(ctx_for())).status == Status.PASS
    none = HOME.replace('<meta name="viewport" content="width=device-width, initial-scale=1">', "")
    assert (await seo.check_mobile_viewport(ctx_for(home=none))).reason == "missing"
    fixed = HOME.replace("width=device-width", "width=1024")
    assert (await seo.check_mobile_viewport(ctx_for(home=fixed))).reason == "fixed_width"
    nozoom = HOME.replace("initial-scale=1", "initial-scale=1, maximum-scale=1, user-scalable=no")
    assert (await seo.check_mobile_viewport(ctx_for(home=nozoom))).reason == "no_zoom"


def test_robots_blocks_everything():
    assert seo.robots_blocks_everything("User-agent: *\nDisallow: /\n")
    assert seo.robots_blocks_everything("User-agent: Googlebot\nDisallow: /")
    assert not seo.robots_blocks_everything("User-agent: *\nDisallow: /admin/\n")
    assert not seo.robots_blocks_everything("User-agent: *\nDisallow:\n")
    assert not seo.robots_blocks_everything("User-agent: BadBot\nDisallow: /\n\nUser-agent: *\nDisallow: /tmp/")
    # Grouped agents share the rules that follow them.
    assert seo.robots_blocks_everything("User-agent: Bingbot\nUser-agent: *\nDisallow: /")


async def test_indexing():
    sitemap = {"/robots.txt": (200, "User-agent: *\nDisallow: /wp-admin/\nSitemap: https://example.com/sitemap.xml\n")}
    assert (await seo.check_indexing(ctx_for(paths=sitemap, soft404=False))).status == Status.PASS
    xml = {"/sitemap.xml": (200, '<?xml version="1.0"?><urlset></urlset>')}
    assert (await seo.check_indexing(ctx_for(paths=xml, soft404=False))).status == Status.PASS
    assert (await seo.check_indexing(ctx_for(soft404=False))).reason == "no_sitemap"
    blocked = {"/robots.txt": (200, "User-agent: *\nDisallow: /\n")}
    assert (await seo.check_indexing(ctx_for(paths=blocked))).reason == "blocked"
    noindex = HOME.replace("<head>", '<head><meta name="robots" content="noindex, nofollow">')
    assert (await seo.check_indexing(ctx_for(home=noindex))).reason == "noindex"
    header = await seo.check_indexing(ctx_for(headers={"x-robots-tag": "noindex"}))
    assert (header.status, header.reason) == (Status.FAIL, "noindex")


async def test_social_preview():
    assert (await seo.check_social_preview(ctx_for())).status == Status.PASS
    bare = HOME.replace('<meta property="og:title" content="Rahim Traders"><meta property="og:image" content="https://example.com/og.png">', "")
    assert (await seo.check_social_preview(ctx_for(home=bare))).reason == "none"
    no_icon = HOME.replace('<link rel="icon" href="/favicon.png">', "")
    assert (await seo.check_social_preview(ctx_for(home=no_icon, soft404=False))).reason == "no_favicon"
    ico = {"/favicon.ico": (200, b"\x00\x00\x01\x00" + b"\x00" * 10, {"content-type": "image/x-icon"})}
    assert (await seo.check_social_preview(ctx_for(home=no_icon, paths=ico, soft404=False))).status == Status.PASS


def test_html_reader_handles_messy_pages():
    info = parse_page("<html><head><title>  Hello\n  world </title><svg><title>icon</title></svg>"
                      "<meta property='og:image' content='x.png'><link rel='Shortcut Icon' href='/f.ico'>"
                      "<script src='http://a.test/x.js'></script><img src='http://b.test/y.png'><p>unclosed")
    assert info.title == "Hello world"
    assert info.meta("og:image") == "x.png" and info.has_link_rel("icon")
    assert ("script", "http://a.test/x.js", "active") in info.resources
    assert ("img", "http://b.test/y.png", "passive") in info.resources
    assert parse_page("").title is None
