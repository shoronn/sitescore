"""AI agent readiness: robots.txt, sitemap, Link headers, Markdown, AI crawler rules, Content Signals."""
from __future__ import annotations

import httpx
import pytest

from sitescore.engine.checks import agent
from sitescore.engine.models import Category, CheckResult, Status
from sitescore.engine.scoring import agent_level, agent_score, score_results
from test_engine import make_ctx
from test_new_checks import HOME, ctx_for

GOOD_ROBOTS = """User-agent: *
Allow: /
Disallow: /admin
Content-Signal: search=yes, ai-input=yes, ai-train=no

User-agent: GPTBot
User-agent: CCBot
Disallow: /

Sitemap: https://example.com/sitemap.xml
"""
SITEMAP = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://example.com/</loc></url></urlset>'


def agent_site(**kw):
    """A scan context for a fake site (see agent_handler)."""
    return make_ctx(handler=agent_handler(**kw))


def agent_handler(robots: str | None = GOOD_ROBOTS, sitemap: str | None = SITEMAP, link: str | None = None,
                  markdown: bool = False, llms: str | None = None):
    """A fake site for the agent checks. Missing files answer 404."""

    def handler(req: httpx.Request):
        if req.url.scheme == "http":
            return httpx.Response(301, headers={"location": f"https://{req.url.host}{req.url.path}"})
        path = req.url.path
        if path == "/":
            if markdown and "text/markdown" in req.headers.get("accept", ""):
                return httpx.Response(200, text="# Rahim Traders\n\nWholesale rice.",
                                      headers={"content-type": "text/markdown; charset=utf-8", "x-markdown-tokens": "12"})
            headers = {"content-type": "text/html; charset=utf-8"}
            if link:
                headers["link"] = link
            return httpx.Response(200, text=HOME, headers=headers)
        if path == "/robots.txt" and robots is not None:
            return httpx.Response(200, text=robots, headers={"content-type": "text/plain"})
        if path == "/sitemap.xml" and sitemap is not None:
            return httpx.Response(200, text=sitemap, headers={"content-type": "application/xml"})
        if path == "/llms.txt" and llms is not None:
            return httpx.Response(200, text=llms, headers={"content-type": "text/plain"})
        return httpx.Response(404, text="Not found")

    return handler


# ---------------------------------------------------------------- robots.txt rules

def test_parse_robots_groups_sitemaps_and_signals():
    p = agent.parse_robots(GOOD_ROBOTS)
    assert [g["agents"] for g in p["groups"]] == [["*"], ["gptbot", "ccbot"]]
    assert p["sitemaps"] == ["https://example.com/sitemap.xml"]
    assert agent.parse_signals(p["signals"]) == {"search": "yes", "ai-input": "yes", "ai-train": "no"}


@pytest.mark.parametrize("robots,bot,allowed,source", [
    (GOOD_ROBOTS, "gptbot", False, "explicit"),
    (GOOD_ROBOTS, "claude-user", True, "wildcard"),
    ("User-agent: *\nDisallow: /\n", "chatgpt-user", False, "wildcard"),
    ("User-agent: *\nDisallow:\n", "chatgpt-user", True, "wildcard"),
    ("User-agent: *\nDisallow: /\nAllow: /$\n", "chatgpt-user", True, "wildcard"),
    ("User-agent: *\nDisallow: /*\n", "chatgpt-user", False, "wildcard"),
    ("User-agent: googlebot\nDisallow: /\n", "chatgpt-user", True, "default"),
    ("User-agent: *\nDisallow: /\n\nUser-agent: ChatGPT-User\nAllow: /\n", "chatgpt-user", True, "explicit"),
])
def test_access_follows_rfc_9309(robots, bot, allowed, source):
    assert agent.access_for(agent.parse_robots(robots), bot) == (allowed, source)


def test_link_header_parsing():
    links = agent.parse_link_header('</.well-known/api-catalog>; rel="api-catalog", '
                                    '<https://example.com/wp-json/>; rel="https://api.w.org/", '
                                    '</index.md>; rel=alternate; type="text/markdown"')
    assert [(x["href"], x["rel"]) for x in links] == [
        ("/.well-known/api-catalog", "api-catalog"), ("https://example.com/wp-json/", "https://api.w.org/"),
        ("/index.md", "alternate")]
    assert links[2]["type"] == "text/markdown"


# ---------------------------------------------------------------- the checks

async def test_robots_txt():
    assert (await agent.check_robots_txt(agent_site())).status == Status.PASS
    out = await agent.check_robots_txt(agent_site(robots=None))
    assert (out.status, out.reason) == (Status.FAIL, "missing")
    # Soft 404: an HTML page where robots.txt should be does not count.
    out = await agent.check_robots_txt(ctx_for())
    assert (out.status, out.reason) == (Status.FAIL, "invalid")


async def test_sitemap():
    out = await agent.check_sitemap(agent_site())
    assert (out.status, out.reason) == (Status.PASS, "ok")
    out = await agent.check_sitemap(agent_site(robots="User-agent: *\nDisallow:\n"))
    assert (out.status, out.reason) == (Status.PASS, "not_listed")
    out = await agent.check_sitemap(agent_site(sitemap=None))
    assert (out.status, out.reason) == (Status.WARN, "broken")
    out = await agent.check_sitemap(agent_site(robots="User-agent: *\nDisallow:\n", sitemap=None))
    assert (out.status, out.reason) == (Status.FAIL, "missing")


async def test_sitemap_listed_on_a_dead_domain_but_present_locally_warns():
    robots = "User-agent: *\nAllow: /\nSitemap: https://old-domain.example/sitemap.xml\n"

    site = agent_handler(robots=robots)

    def handler(req: httpx.Request):
        if req.url.host == "old-domain.example":
            raise httpx.ConnectError("does not resolve")
        return site(req)

    out = await agent.check_sitemap(make_ctx(handler=handler))
    assert (out.status, out.reason) == (Status.WARN, "broken")


@pytest.mark.parametrize("link,status,reason", [
    (None, Status.FAIL, "missing"),
    ('<https://example.com/wp-json/>; rel="https://api.w.org/"', Status.FAIL, "other_only"),
    ('</style.css>; rel=preload; as=style', Status.FAIL, "other_only"),
    ('<https://example.com/wp-json/wp/v2/pages/2>; rel="alternate"; type="application/json"', Status.PASS, "ok"),
    ('</.well-known/api-catalog>; rel="api-catalog"', Status.PASS, "ok"),
])
async def test_link_headers(link, status, reason):
    out = await agent.check_link_headers(agent_site(link=link))
    assert (out.status, out.reason) == (status, reason)


async def test_markdown_negotiation():
    out = await agent.check_markdown(agent_site(markdown=True))
    assert (out.status, out.reason) == (Status.PASS, "ok") and out.evidence["tokens"] == "12"
    out = await agent.check_markdown(agent_site())
    assert (out.status, out.reason) == (Status.FAIL, "html_only") and out.evidence["content_type"] == "text/html"


async def test_ai_rules():
    out = await agent.check_ai_rules(agent_site())
    assert (out.status, out.reason) == (Status.PASS, "ok")
    assert out.evidence["named"] == ["GPTBot", "CCBot"] and out.evidence["blocked"] == []
    # No AI crawler named: the general rules let assistants in, as Cloudflare's scanner counts it.
    out = await agent.check_ai_rules(agent_site(robots="User-agent: *\nDisallow: /admin\n"))
    assert (out.status, out.reason) == (Status.PASS, "wildcard")
    out = await agent.check_ai_rules(agent_site(robots="User-agent: *\nDisallow: /\n"))
    assert (out.status, out.reason) == (Status.FAIL, "blocks_assistants")
    out = await agent.check_ai_rules(agent_site(robots=None))
    assert (out.status, out.reason) == (Status.FAIL, "no_robots")


async def test_content_signals():
    out = await agent.check_content_signals(agent_site())
    assert out.status == Status.PASS and out.evidence["signals_text"] == "search=yes, ai-input=yes, ai-train=no"
    out = await agent.check_content_signals(agent_site(robots="User-agent: *\nContent-Signal: maybe\n"))
    assert (out.status, out.reason) == (Status.FAIL, "invalid")
    out = await agent.check_content_signals(agent_site(robots="User-agent: *\nDisallow:\n"))
    assert (out.status, out.reason) == (Status.FAIL, "missing")


async def test_llms_txt_is_information_only():
    assert (await agent.check_llms_txt(agent_site(llms="# Rahim Traders\n> Wholesale rice\n"))).status == Status.PASS
    assert (await agent.check_llms_txt(agent_site())).status == Status.FAIL
    assert (await agent.check_llms_txt(ctx_for())).status == Status.FAIL  # soft 404 HTML


async def test_unreachable_site_is_not_checked():
    def down(req):
        raise httpx.ConnectError("refused")

    ctx = make_ctx(handler=down)
    for fn in (agent.check_robots_txt, agent.check_sitemap, agent.check_link_headers, agent.check_markdown,
               agent.check_ai_rules, agent.check_content_signals, agent.check_llms_txt):
        assert (await fn(ctx)).status == Status.NOT_CHECKED, fn.__name__


# ---------------------------------------------------------------- scoring

def _res(key, status, weight, category=Category.AGENT):
    from sitescore.engine.scoring import points_for

    return CheckResult(key, key, category, weight, status, points_for(status, weight), "", "", "", "", "none",
                       False, {}, 0)


def test_agent_score_is_separate_from_health():
    results = [_res("robots_txt", Status.PASS, 10), _res("sitemap", Status.PASS, 15),
               _res("link_headers", Status.FAIL, 10), _res("markdown", Status.FAIL, 30),
               _res("ai_rules", Status.PASS, 20), _res("content_signals", Status.FAIL, 15),
               _res("llms_txt", Status.FAIL, 0), _res("https", Status.PASS, 6, Category.SECURITY)]
    assert agent_score(results) == 45
    assert agent_level(45) == ("started", "Getting started")
    score, _, cats = score_results(results)
    assert score == 100 and Category.AGENT not in {c.category for c in cats}


def test_agent_levels():
    assert [agent_level(s)[1] for s in (0, 19, 20, 50, 80, 99, 100)] == [
        "Not ready", "Not ready", "Getting started", "Partly ready", "Almost ready", "Almost ready", "Agent ready"]
    assert agent_level(None) == (None, None)
    assert agent_score([_res("markdown", Status.NOT_CHECKED, 30)]) is None


# ---------------------------------------------------------------- reports

def _report_data(with_agent: bool):
    results = [{"key": "https", "name": "HTTPS", "category": "security", "weight": 6, "status": "pass", "points": 6,
                "title": "HTTPS is on and enforced", "summary": "s", "why": "w", "fix": "f", "offer": "none",
                "critical": False, "evidence": {}}]
    if with_agent:
        results.insert(0, {"key": "markdown", "name": "Markdown for agents", "category": "agent", "weight": 30,
                           "status": "fail", "points": 0, "title": "No Markdown version for AI agents", "summary": "s",
                           "why": "w", "fix": "f", "offer": "fixit", "critical": False, "evidence": {}})
    return {"token": "t", "host": "shop.example", "results": results, "score": 100, "band": "good", "band_label": "Good",
            "capped": False, "coverage": 100, "finished_at": "2026-10-29T10:00:00+00:00",
            "agent": {"score": 0 if with_agent else None, "level": "not_ready" if with_agent else None,
                      "label": "Not ready" if with_agent else None, "band": "risk" if with_agent else None},
            "categories": [{"key": "security", "label": "Security", "score": 100, "earned": 6, "available": 6}]}


@pytest.mark.parametrize("with_agent", [True, False])
def test_report_email_and_pdf_with_and_without_agent_results(with_agent):
    from sitescore.config import get_settings
    from sitescore.report import render_pdf, report_context, report_email

    settings = get_settings()
    data = _report_data(with_agent)
    pdf = render_pdf(data, settings)
    assert pdf[:5] == b"%PDF-"
    msg = report_email(data, settings, "owner@shop.example", pdf)
    ctx = report_context(data, settings)
    if with_agent:
        assert msg.subject == "shop.example on SiteScore: AI agent readiness 0/100, health 100/100"
        assert "AI agent readiness: 0/100 (Not ready)." in msg.text and "AI AGENT READINESS" in msg.html
        assert [r["key"] for r in ctx["agent_issues"]] == ["markdown"]
    else:
        # A scan from before AI agent readiness existed: that part is left out, not shown empty.
        assert msg.subject == "shop.example on SiteScore: health 100/100"
        assert "AI agent" not in msg.text and "AI AGENT READINESS" not in msg.html
        assert ctx["agent_items"] == []
