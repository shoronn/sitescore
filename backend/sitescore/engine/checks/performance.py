"""Page speed from the built-in speed test (Lighthouse on a simulated mid-range phone over 4G)."""
from __future__ import annotations

import re

from ..models import Category, Outcome, Status
from ..speedtest import final_screenshot, lab_metrics, speed_fixes
from .base import check

# Lighthouse's own errors that mean the page itself did not load properly.
PAGE_ERRORS = {"NO_FCP", "NO_LCP", "FAILED_DOCUMENT_REQUEST", "ERRORED_DOCUMENT_REQUEST",
               "INSECURE_DOCUMENT_REQUEST", "NOT_HTML", "PAGE_HUNG", "DNS_FAILURE", "CHROME_INTERSTITIAL_ERROR"}


# Status codes that mean the site turned the test browser away (bot protection, firewall).
BLOCKED = re.compile(r"\(Status code: (401|403|406|429|503)\)")


def _source(data: dict, m: dict) -> dict:
    """Say who measured it: our own browser, or Google PageSpeed as the fallback."""
    if data.get("via") == "pagespeed":
        m["tester"] = "Google PageSpeed Insights"
        m["local_error"] = data.get("local_error", "")
    else:
        m["tester"] = "Our speed test"
    return m


def _failed(data: dict) -> Outcome:
    code = data.get("error", "")
    ev = {"error": code, "detail": data.get("detail", "")}
    if code == "unreachable":
        return Outcome(Status.NOT_CHECKED, ev, "unreachable")
    if code in PAGE_ERRORS and BLOCKED.search(ev["detail"] or ""):
        return Outcome(Status.NOT_CHECKED, ev, "speed_blocked")
    if code in PAGE_ERRORS:
        return Outcome(Status.NOT_CHECKED, ev, "speed_page_error")
    return Outcome(Status.NOT_CHECKED, ev, "speed_failed")


@check("mobile_speed", "Mobile speed score", Category.PERFORMANCE, 8, slow=True)
async def check_mobile_speed(ctx) -> Outcome:
    data = await ctx.speed_test()
    if "lhr" not in data:
        return _failed(data)
    m = _source(data, lab_metrics(data["lhr"]))
    if "score" not in m:
        return Outcome(Status.NOT_CHECKED, m, "speed_failed")
    # What would save the most time, and what the page looked like on the test phone.
    m["fixes"] = speed_fixes(data["lhr"])
    shot = final_screenshot(data["lhr"])
    if shot:
        m["screenshot"] = shot
    if m["score"] >= 90:
        return Outcome(Status.PASS, m, "ok")
    if m["score"] >= 50:
        return Outcome(Status.WARN, m, "average")
    return Outcome(Status.FAIL, m, "poor")


@check("web_vitals", "Core Web Vitals", Category.PERFORMANCE, 5, slow=True)
async def check_web_vitals(ctx) -> Outcome:
    """Loading (LCP), visual stability (CLS) and responsiveness.

    Responsiveness in the field is INP, which needs real visitors. In a lab test the
    standard stand-in is Total Blocking Time: how long the page is too busy to react.
    """
    data = await ctx.speed_test()
    if "lhr" not in data:
        return _failed(data)
    m = _source(data, lab_metrics(data["lhr"]))
    lcp, cls, tbt = m.get("lcp_s"), m.get("cls"), m.get("tbt_ms")
    if lcp is None or cls is None or tbt is None:
        return Outcome(Status.NOT_CHECKED, m, "speed_failed")
    if lcp > 4.0 or cls > 0.25 or tbt > 600:
        return Outcome(Status.FAIL, m, "poor")
    if lcp > 2.5 or cls > 0.1 or tbt > 200:
        return Outcome(Status.WARN, m, "needs_work")
    return Outcome(Status.PASS, m, "ok")
