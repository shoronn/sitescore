"""Turn check results into a score out of 100, category scores and a band."""
from __future__ import annotations

from .models import CATEGORY_LABELS, HEALTH_CATEGORIES, Category, CategoryScore, CheckResult, Status

POINTS = {Status.PASS: 1.0, Status.WARN: 0.5, Status.FAIL: 0.0}
CRITICAL_CAP = 49

BANDS = [(80, "good", "Good"), (50, "attention", "Needs attention"), (0, "risk", "At risk")]


def points_for(status: Status, weight: int) -> float:
    return POINTS.get(status, 0.0) * weight


def band_for(score: int | None) -> str | None:
    if score is None:
        return None
    for floor, key, _label in BANDS:
        if score >= floor:
            return key
    return "risk"


def band_label(band: str | None) -> str | None:
    return next((label for _f, key, label in BANDS if key == band), None)


def score_results(results: list[CheckResult]) -> tuple[int | None, bool, list[CategoryScore]]:
    """The website health score: (score, capped, per-category scores).

    Not-checked results do not count, and AI agent readiness has its own score.
    """
    counted = [r for r in results if r.status != Status.NOT_CHECKED and r.category in HEALTH_CATEGORIES]
    available = sum(r.weight for r in counted)
    earned = sum(r.points for r in counted)
    score = round(earned / available * 100) if available else None
    capped = False
    if score is not None and any(r.critical for r in counted) and score > CRITICAL_CAP:
        score, capped = CRITICAL_CAP, True

    cats = []
    for cat in HEALTH_CATEGORIES:
        rs = [r for r in counted if r.category == cat]
        avail = sum(r.weight for r in rs)
        got = sum(r.points for r in rs)
        cats.append(CategoryScore(cat, CATEGORY_LABELS[cat], got, avail, round(got / avail * 100) if avail else None))
    return score, capped, cats


# AI agent readiness: its own score out of 100 and a plain label.
AGENT_LEVELS = [(100, "ready", "Agent ready"), (80, "almost", "Almost ready"), (50, "partly", "Partly ready"),
                (20, "started", "Getting started"), (0, "not_ready", "Not ready")]


def agent_score(results: list[CheckResult]) -> int | None:
    """Weighted share of the agent checks that pass. None when none could be checked."""
    counted = [r for r in results if r.category == Category.AGENT and r.weight > 0 and r.status != Status.NOT_CHECKED]
    available = sum(r.weight for r in counted)
    if not available:
        return None
    return round(sum(r.points for r in counted) / available * 100)


def agent_level(score: int | None) -> tuple[str, str] | tuple[None, None]:
    """(key, label) for an agent score, e.g. ("partly", "Partly ready")."""
    if score is None:
        return None, None
    for floor, key, label in AGENT_LEVELS:
        if score >= floor:
            return key, label
    return "not_ready", "Not ready"


def agent_band(score: int | None) -> str | None:
    """Colour band shared with the health score: good, attention or risk."""
    return band_for(score)
