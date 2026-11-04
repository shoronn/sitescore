"""Run every check for one target and build the report."""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Awaitable, Callable

from .checks import CHECKS
from .checks.base import CheckDef
from .context import ENGINE_VERSION, EngineSettings, ScanContext
from .findings import word
from .models import CheckResult, Outcome, ScanReport, Status
from .scoring import agent_score, band_for, points_for, score_results

ProgressFn = Callable[[CheckResult], Awaitable[None] | None]


async def _run_one(ctx: ScanContext, c: CheckDef) -> CheckResult:
    start = time.perf_counter()
    try:
        # Speed checks wait as long as the speed test itself may take (plus time to load the
        # homepage first); a shorter limit here would cancel the test midway.
        limit = ctx.settings.speed_timeout + ctx.settings.check_timeout if c.slow else ctx.settings.check_timeout
        outcome = await asyncio.wait_for(c.fn(ctx), timeout=limit)
    except asyncio.TimeoutError:
        outcome = Outcome(Status.NOT_CHECKED, {"error": "timeout"}, "speed_failed" if c.slow else "lookup_failed")
    except Exception as exc:  # noqa: BLE001 - one broken check must never sink the scan
        outcome = Outcome(Status.NOT_CHECKED, {"error": f"{type(exc).__name__}: {exc}"[:300]}, "lookup_failed")
    text = word(c.key, c.name, outcome.status.value, outcome.reason, outcome.evidence,
                {"host": ctx.host, "apex": ctx.apex})
    return CheckResult(
        key=c.key, name=c.name, category=c.category, weight=c.weight,
        status=outcome.status, points=points_for(outcome.status, c.weight),
        title=text["title"], summary=text["summary"], why=text["why"], fix=text["fix"],
        offer=text["offer"], critical=outcome.critical and outcome.status == Status.FAIL,
        evidence={**outcome.evidence, "reason": outcome.reason},
        duration_ms=int((time.perf_counter() - start) * 1000),
    )


async def run_scan(
    target: str,
    settings: EngineSettings | None = None,
    on_result: ProgressFn | None = None,
    ctx: ScanContext | None = None,
) -> ScanReport:
    """Scan `target`. Raises ScanError if the target cannot be scanned at all."""
    started = datetime.now(timezone.utc)
    t0 = time.perf_counter()
    ctx = ctx or ScanContext(target, settings=settings)
    try:
        await ctx.prepare()

        async def run_and_report(c: CheckDef) -> CheckResult:
            result = await _run_one(ctx, c)
            if on_result is not None:
                maybe = on_result(result)
                if asyncio.iscoroutine(maybe):
                    await maybe
            return result

        results = await asyncio.gather(*(run_and_report(c) for c in CHECKS))
    finally:
        await ctx.close()
    score, capped, cats = score_results(list(results))
    return ScanReport(
        target=target, host=ctx.host, apex=ctx.apex, score=score, band=band_for(score),
        capped=capped, coverage=sum(c.available for c in cats), agent_score=agent_score(list(results)), categories=cats, results=list(results), engine_version=ENGINE_VERSION,
        started_at=started.isoformat(), finished_at=datetime.now(timezone.utc).isoformat(),
        duration_ms=int((time.perf_counter() - t0) * 1000),
    )
