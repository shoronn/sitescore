"""AI agent readiness: can AI agents and assistants find, read and use the site?

Six checks for content sites (business sites, blogs, shops' public pages), built on
open standards: robots.txt (RFC 9309), sitemaps, Link headers (RFC 8288), Markdown
content negotiation, rules for AI crawlers, and Content Signals. They have their own
score out of 100 (scoring.agent_score), separate from the website health score.
llms.txt is shown for information and not scored.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin, urlsplit

from ..models import Category, Outcome, Status
from .base import check

# Product tokens of AI crawlers and assistants, as they appear in robots.txt (lower case).
AI_CRAWLERS = {
    "gptbot": "GPTBot", "chatgpt-user": "ChatGPT-User", "oai-searchbot": "OAI-SearchBot",
    "claudebot": "ClaudeBot", "claude-user": "Claude-User", "claude-searchbot": "Claude-SearchBot",
    "anthropic-ai": "anthropic-ai", "claude-web": "Claude-Web",
    "google-extended": "Google-Extended", "googleother": "GoogleOther", "google-cloudvertexbot": "Google-CloudVertexBot",
    "perplexitybot": "PerplexityBot", "perplexity-user": "Perplexity-User",
    "ccbot": "CCBot", "applebot-extended": "Applebot-Extended", "bytespider": "Bytespider",
    "amazonbot": "Amazonbot", "meta-externalagent": "meta-externalagent", "meta-externalfetcher": "meta-externalfetcher",
    "facebookbot": "FacebookBot", "cohere-ai": "cohere-ai", "cohere-training-data-crawler": "cohere-training-data-crawler",
    "diffbot": "Diffbot", "youbot": "YouBot", "mistralai-user": "MistralAI-User", "duckassistbot": "DuckAssistBot",
    "ai2bot": "AI2Bot", "omgilibot": "omgilibot", "timpibot": "Timpibot", "imagesiftbot": "ImagesiftBot",
}
# Assistants that read pages to answer people's questions or to show them in AI search.
ASSISTANTS = ("chatgpt-user", "oai-searchbot", "claude-user", "claude-searchbot", "perplexitybot", "perplexity-user")

# Link relations that point an agent to something machine-readable.
AGENT_RELS = {"alternate", "api-catalog", "service-desc", "service-doc", "service-meta", "describedby",
              "sitemap", "llms-txt", "llms-full-txt", "mcp-server-card", "agent-skills"}

SIGNAL_KEYS = ("search", "ai-input", "ai-train")


# ---------------------------------------------------------------- robots.txt

def parse_robots(text: str) -> dict[str, Any]:
    """Groups of (user agents, rules), Sitemap URLs and Content-Signal values."""
    groups: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    sitemaps: list[str] = []
    signals: list[str] = []
    directives = 0
    last_was_agent = False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        field, value = (x.strip() for x in line.split(":", 1))
        field = field.lower()
        if field == "user-agent":
            directives += 1
            if current is None or not last_was_agent:
                current = {"agents": [], "rules": []}
                groups.append(current)
            current["agents"].append(value.lower())
            last_was_agent = True
            continue
        last_was_agent = False
        if field in ("allow", "disallow"):
            directives += 1
            if current is not None:
                current["rules"].append((field, value))
        elif field == "sitemap":
            directives += 1
            if value:
                sitemaps.append(value)
        elif field == "content-signal":
            directives += 1
            signals.append(value)
        elif field in ("crawl-delay", "host", "clean-param"):
            directives += 1
    return {"groups": groups, "sitemaps": sitemaps, "signals": signals, "directives": directives}


def _pattern_matches(pattern: str, path: str) -> bool:
    regex = "".join(".*" if ch == "*" else re.escape(ch) for ch in pattern.rstrip("$"))
    return re.match(regex + ("$" if pattern.endswith("$") else ""), path) is not None


def access_for(parsed: dict[str, Any], agent: str, path: str = "/") -> tuple[bool, str]:
    """(allowed, source) for `agent` on `path`, following RFC 9309.

    source is "explicit" when a group names the agent, "wildcard" when the * group
    applies, and "default" when no group applies (everything is allowed).
    """
    agent = agent.lower()
    explicit = [g for g in parsed["groups"] if agent in g["agents"]]
    groups, source = (explicit, "explicit") if explicit else (
        [g for g in parsed["groups"] if "*" in g["agents"]], "wildcard")
    if not groups:
        return True, "default"
    best: tuple[int, bool] | None = None  # (pattern length, allowed)
    for g in groups:
        for kind, pattern in g["rules"]:
            if not pattern:
                continue  # "Disallow:" with nothing after it allows everything
            if _pattern_matches(pattern, path):
                candidate = (len(pattern), kind == "allow")
                # Longest match wins; on a tie, allow wins.
                if best is None or candidate[0] > best[0] or (candidate[0] == best[0] and candidate[1]):
                    best = candidate
    return (True if best is None else best[1]), source


def parse_signals(values: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for value in values:
        for part in value.split(","):
            if "=" not in part:
                continue
            k, v = (x.strip().lower() for x in part.split("=", 1))
            if k in SIGNAL_KEYS and v in ("yes", "no"):
                out[k] = v
    return out


def _looks_like_html(text: str) -> bool:
    head = text.lstrip()[:300].lower()
    return head.startswith(("<!doctype", "<html", "<head", "<body")) or "<html" in head


async def robots(ctx) -> dict[str, Any]:
    """robots.txt for the site, fetched once (redirects followed, each hop guarded)."""
    if "robots" in ctx.shared:
        return ctx.shared["robots"]
    out: dict[str, Any] = {"state": "unreachable"}
    base = await ctx.site_base()
    if base is not None:
        root, verify = base
        res = await ctx.fetch(root + "/robots.txt", verify=verify)
        if res.error and res.status is None:
            out = {"state": "error", "error": res.error}
        elif res.status != 200:
            out = {"state": "missing", "status": res.status}
        else:
            parsed = parse_robots(res.text)
            if _looks_like_html(res.text) or parsed["directives"] == 0:
                out = {"state": "invalid", "status": res.status}
            else:
                out = {"state": "ok", "parsed": parsed, "url": res.final_url}
    ctx.shared["robots"] = out
    return out


# ---------------------------------------------------------------- checks

@check("robots_txt", "robots.txt", Category.AGENT, 10)
async def check_robots_txt(ctx) -> Outcome:
    r = await robots(ctx)
    if r["state"] == "unreachable":
        return Outcome(Status.NOT_CHECKED, {}, "unreachable")
    if r["state"] == "error":
        return Outcome(Status.NOT_CHECKED, {"error": r["error"]}, "lookup_failed")
    if r["state"] == "ok":
        p = r["parsed"]
        return Outcome(Status.PASS, {"groups": len(p["groups"]), "sitemaps": len(p["sitemaps"])}, "ok")
    if r["state"] == "invalid":
        return Outcome(Status.FAIL, {"status": r.get("status")}, "invalid")
    return Outcome(Status.FAIL, {"status": r.get("status")}, "missing")


def _is_sitemap(text: str, content_type: str, url: str) -> bool:
    head = text.lstrip("﻿ \r\n\t")[:4096]
    if "<urlset" in head or "<sitemapindex" in head:
        return True
    # Compressed sitemaps (sitemap.xml.gz) are valid too.
    return url.endswith(".gz") and ("gzip" in content_type or "octet-stream" in content_type)


@check("sitemap", "Sitemap", Category.AGENT, 15)
async def check_sitemap(ctx) -> Outcome:
    base = await ctx.site_base()
    if base is None:
        return Outcome(Status.NOT_CHECKED, {}, "unreachable")
    root, verify = base
    r = await robots(ctx)
    listed = [u for u in (r.get("parsed") or {}).get("sitemaps", []) if urlsplit(u).scheme in ("http", "https")]
    for url in listed[:2]:
        res = await ctx.fetch(url, verify=verify)
        if res.status == 200 and _is_sitemap(res.text, (res.header("content-type") or "").lower(), url):
            return Outcome(Status.PASS, {"url": url}, "ok")
    for path in ("/sitemap.xml", "/sitemap_index.xml", "/wp-sitemap.xml"):
        url = urljoin(root + "/", path.lstrip("/"))
        res = await ctx.fetch(url, verify=verify)
        if res.status == 200 and _is_sitemap(res.text, (res.header("content-type") or "").lower(), url):
            # A working sitemap exists, but robots.txt points agents to a broken one.
            if listed:
                return Outcome(Status.WARN, {"url": url, "listed": listed[:2]}, "broken")
            return Outcome(Status.PASS, {"url": url}, "not_listed")
    if listed:
        return Outcome(Status.WARN, {"listed": listed[:2]}, "broken")
    return Outcome(Status.FAIL, {}, "missing")


_LINK = re.compile(r'<([^>]*)>((?:\s*;\s*[^;,=\s]+\s*(?:=\s*(?:"[^"]*"|[^;,]*))?)*)')
_PARAM = re.compile(r';\s*([^;,=\s]+)\s*(?:=\s*("[^"]*"|[^;,]*))?')


def parse_link_header(value: str) -> list[dict[str, str]]:
    links = []
    for m in _LINK.finditer(value or ""):
        params = {k.lower(): (v or "").strip().strip('"') for k, v in _PARAM.findall(m.group(2))}
        links.append({"href": m.group(1).strip(), **params})
    return links


@check("link_headers", "Link headers", Category.AGENT, 10)
async def check_link_headers(ctx) -> Outcome:
    page = await ctx.main_page()
    if not page.ok:
        return Outcome(Status.NOT_CHECKED, {}, "unreachable")
    links = parse_link_header(page.header("link") or "")
    rels = sorted({rel for link in links for rel in link.get("rel", "").lower().split() if rel})
    useful = [rel for rel in rels if rel in AGENT_RELS]
    if useful:
        return Outcome(Status.PASS, {"rels": useful}, "ok")
    if links:
        shown = [rel if not rel.startswith("http") else "custom" for rel in rels] or ["no rel"]
        return Outcome(Status.FAIL, {"rels": sorted(set(shown))[:4]}, "other_only")
    return Outcome(Status.FAIL, {}, "missing")


@check("markdown", "Markdown for agents", Category.AGENT, 30)
async def check_markdown(ctx) -> Outcome:
    page = await ctx.main_page()
    base = await ctx.site_base()
    if not page.ok or not page.final_url or base is None:
        return Outcome(Status.NOT_CHECKED, {}, "unreachable")
    res = await ctx.fetch(page.final_url, verify=base[1], headers={"Accept": "text/markdown"})
    if res.status is None:
        return Outcome(Status.NOT_CHECKED, {"error": res.error or "no answer"}, "lookup_failed")
    ctype = (res.header("content-type") or "").split(";")[0].strip().lower()
    ev = {"status": res.status, "content_type": ctype or "none"}
    if res.status == 200 and ctype in ("text/markdown", "text/x-markdown"):
        if res.header("x-markdown-tokens"):
            ev["tokens"] = res.header("x-markdown-tokens")
        return Outcome(Status.PASS, ev, "ok")
    return Outcome(Status.FAIL, ev, "html_only")


@check("ai_rules", "AI crawler rules", Category.AGENT, 20)
async def check_ai_rules(ctx) -> Outcome:
    r = await robots(ctx)
    if r["state"] == "unreachable":
        return Outcome(Status.NOT_CHECKED, {}, "unreachable")
    if r["state"] == "error":
        return Outcome(Status.NOT_CHECKED, {"error": r["error"]}, "lookup_failed")
    if r["state"] != "ok":
        return Outcome(Status.FAIL, {}, "no_robots")
    parsed = r["parsed"]
    named_keys = [k for k in AI_CRAWLERS if any(k in g["agents"] for g in parsed["groups"])]
    named = [AI_CRAWLERS[k] for k in named_keys]
    blocked = [AI_CRAWLERS[k] for k in ASSISTANTS if not access_for(parsed, k)[0]]
    ev = {"named": named[:8], "blocked": blocked}
    if len(blocked) == len(ASSISTANTS):
        return Outcome(Status.FAIL, ev, "blocks_assistants")
    if named:
        return Outcome(Status.PASS, ev, "ok")
    return Outcome(Status.PASS, ev, "wildcard")


@check("content_signals", "Content Signals", Category.AGENT, 15)
async def check_content_signals(ctx) -> Outcome:
    r = await robots(ctx)
    if r["state"] == "unreachable":
        return Outcome(Status.NOT_CHECKED, {}, "unreachable")
    if r["state"] == "error":
        return Outcome(Status.NOT_CHECKED, {"error": r["error"]}, "lookup_failed")
    if r["state"] != "ok":
        return Outcome(Status.FAIL, {}, "no_robots")
    raw = r["parsed"]["signals"]
    if not raw:
        return Outcome(Status.FAIL, {}, "missing")
    signals = parse_signals(raw)
    if not signals:
        return Outcome(Status.FAIL, {"raw": raw[0][:120]}, "invalid")
    text = ", ".join(f"{k}={signals[k]}" for k in SIGNAL_KEYS if k in signals)
    return Outcome(Status.PASS, {"signals": signals, "signals_text": text}, "ok")


@check("llms_txt", "llms.txt", Category.AGENT, 0)
async def check_llms_txt(ctx) -> Outcome:
    """Information only (weight 0): useful to some AI tools, not counted in the score."""
    base = await ctx.site_base()
    if base is None:
        return Outcome(Status.NOT_CHECKED, {}, "unreachable")
    root, verify = base
    res = await ctx.fetch(root + "/llms.txt", verify=verify)
    text = res.text.lstrip("﻿ \r\n\t")
    if res.status == 200 and text.startswith("#") and not _looks_like_html(text):
        return Outcome(Status.PASS, {}, "ok")
    return Outcome(Status.FAIL, {}, "missing")
