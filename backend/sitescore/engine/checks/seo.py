"""Search and sharing basics: what Google and social apps see on the homepage."""
from __future__ import annotations

import re

from ..models import Category, Outcome, Status
from .base import check


def _unreadable(ctx_page_ok: bool) -> Outcome:
    return Outcome(Status.NOT_CHECKED, {}, "unreachable" if not ctx_page_ok else "not_html")


@check("meta_tags", "Title and description", Category.SEO, 3)
async def check_meta_tags(ctx) -> Outcome:
    page = await ctx.main_page()
    info = await ctx.page_info()
    if info is None:
        return _unreadable(page.ok)
    title = (info.title or "").strip()
    desc = (info.meta("description") or "").strip()
    ev = {"title": title[:120], "title_len": len(title), "desc_len": len(desc)}
    if not title:
        return Outcome(Status.FAIL, ev, "no_title")
    if not desc:
        return Outcome(Status.WARN, ev, "no_description")
    if not 10 <= len(title) <= 70:
        return Outcome(Status.WARN, ev, "title_length")
    if not 50 <= len(desc) <= 170:
        return Outcome(Status.WARN, ev, "description_length")
    return Outcome(Status.PASS, ev, "ok")


@check("mobile_viewport", "Mobile-friendly setup", Category.SEO, 3)
async def check_mobile_viewport(ctx) -> Outcome:
    page = await ctx.main_page()
    info = await ctx.page_info()
    if info is None:
        return _unreadable(page.ok)
    vp = (info.meta("viewport") or "").lower().replace(" ", "")
    ev = {"viewport": vp[:120]}
    if not vp:
        return Outcome(Status.FAIL, ev, "missing")
    if "width=device-width" not in vp:
        return Outcome(Status.FAIL, ev, "fixed_width")
    if "user-scalable=no" in vp or "user-scalable=0" in vp or re.search(r"maximum-scale=(1(\.0)?|0?\.\d+)(,|$)", vp):
        return Outcome(Status.WARN, ev, "no_zoom")
    return Outcome(Status.PASS, ev, "ok")


def robots_blocks_everything(robots: str) -> bool:
    """True if robots.txt tells every crawler (User-agent: *) or Googlebot to stay out of the whole site."""
    groups: list[tuple[set[str], list[str]]] = []
    agents: set[str] = set()
    rules: list[str] = []
    last_was_agent = False
    for raw in robots.splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        field, value = (x.strip() for x in line.split(":", 1))
        field = field.lower()
        if field == "user-agent":
            if not last_was_agent and (agents or rules):
                groups.append((agents, rules))
                agents, rules = set(), []
            agents.add(value.lower())
            last_was_agent = True
        elif field in ("disallow", "allow"):
            rules.append(f"{field}:{value}")
            last_was_agent = False
    if agents or rules:
        groups.append((agents, rules))
    for agents, rules in groups:
        if agents & {"*", "googlebot"}:
            if "disallow:/" in [r.replace(" ", "") for r in rules] and not any(r.startswith("allow:/") and r != "allow:" for r in rules):
                return True
    return False


@check("indexing", "Search engine access", Category.SEO, 3)
async def check_indexing(ctx) -> Outcome:
    page = await ctx.main_page()
    if not page.ok:
        return Outcome(Status.NOT_CHECKED, {}, "unreachable")
    info = await ctx.page_info()
    robots_tag = (page.header("x-robots-tag") or "").lower()
    meta_robots = ((info.meta("robots", "googlebot") if info else None) or "").lower()
    if "noindex" in robots_tag or "noindex" in meta_robots:
        return Outcome(Status.FAIL, {"where": "page"}, "noindex")
    robots = await ctx.probe("/robots.txt", max_bytes=65536)
    robots_text = robots.text if robots.status == 200 and "<html" not in robots.text[:300].lower() else ""
    if robots_text and robots_blocks_everything(robots_text):
        return Outcome(Status.FAIL, {"where": "robots.txt"}, "blocked")
    sitemap = any(line.strip().lower().startswith("sitemap:") for line in robots_text.splitlines())
    if not sitemap:
        for path in ("/sitemap.xml", "/sitemap_index.xml", "/wp-sitemap.xml"):
            res = await ctx.probe(path, max_bytes=4096)
            if res.status == 200 and ("<urlset" in res.text or "<sitemapindex" in res.text):
                sitemap = True
                break
    ev = {"robots_txt": bool(robots_text), "sitemap": sitemap}
    if not sitemap:
        return Outcome(Status.WARN, ev, "no_sitemap")
    return Outcome(Status.PASS, ev, "ok")


@check("social_preview", "Sharing preview", Category.SEO, 1)
async def check_social_preview(ctx) -> Outcome:
    page = await ctx.main_page()
    info = await ctx.page_info()
    if info is None:
        return _unreadable(page.ok)
    og = {k: bool(info.meta(f"og:{k}")) for k in ("title", "description", "image")}
    favicon = info.has_link_rel("icon", "shortcut", "apple-touch-icon")
    if not favicon:
        res = await ctx.probe("/favicon.ico", max_bytes=512)
        favicon = res.status == 200 and (
            "image" in (res.header("content-type") or "") or res.body[:4] in (b"\x00\x00\x01\x00", b"\x89PNG"))
    missing = [k for k, v in og.items() if not v]
    ev = {"missing": [f"og:{k}" for k in missing], "favicon": favicon}
    if len(missing) == 3:
        return Outcome(Status.WARN, ev, "none")
    if og["title"] and og["image"]:
        return Outcome(Status.PASS, ev, "ok") if favicon else Outcome(Status.WARN, ev, "no_favicon")
    return Outcome(Status.WARN, ev, "partial")
