"""Core data types shared by every check and by the API."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any


class Status(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    NOT_CHECKED = "not_checked"


class Category(str, Enum):
    SECURITY = "security"
    RELIABILITY = "reliability"
    EMAIL = "email"
    PERFORMANCE = "performance"
    SEO = "seo"
    # Scored on its own (scoring.agent_score), not part of the health score.
    AGENT = "agent"


HEALTH_CATEGORIES = (Category.SECURITY, Category.RELIABILITY, Category.EMAIL, Category.PERFORMANCE, Category.SEO)

CATEGORY_LABELS = {
    Category.SECURITY: "Security",
    Category.RELIABILITY: "Reliability",
    Category.EMAIL: "Email",
    Category.PERFORMANCE: "Performance",
    Category.SEO: "Search and sharing",
    Category.AGENT: "AI agent readiness",
}


@dataclass
class Outcome:
    """What a check returns. Wording is filled in later from the findings library."""

    status: Status
    evidence: dict[str, Any] = field(default_factory=dict)
    # Short reason code used to pick the right wording, e.g. "no_hsts".
    reason: str = ""
    # A critical finding caps the whole score at 49.
    critical: bool = False


@dataclass
class CheckResult:
    key: str
    name: str
    category: Category
    weight: int
    status: Status
    points: float
    title: str
    summary: str
    why: str
    fix: str
    offer: str
    critical: bool
    evidence: dict[str, Any]
    duration_ms: int

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["category"] = self.category.value
        d["status"] = self.status.value
        return d


@dataclass
class CategoryScore:
    category: Category
    label: str
    earned: float
    available: int
    score: int | None


@dataclass
class ScanReport:
    target: str
    host: str
    apex: str
    score: int | None
    band: str | None
    capped: bool
    coverage: int  # points (out of 100) that could actually be checked
    agent_score: int | None
    categories: list[CategoryScore]
    results: list[CheckResult]
    engine_version: str
    started_at: str
    finished_at: str
    duration_ms: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "host": self.host,
            "apex": self.apex,
            "score": self.score,
            "band": self.band,
            "capped": self.capped,
            "coverage": self.coverage,
            "agent_score": self.agent_score,
            "categories": [
                {
                    "category": c.category.value,
                    "label": c.label,
                    "earned": c.earned,
                    "available": c.available,
                    "score": c.score,
                }
                for c in self.categories
            ],
            "results": [r.to_dict() for r in self.results],
            "engine_version": self.engine_version,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
        }


class ScanError(Exception):
    """The scan cannot run at all (bad domain, private address, does not resolve)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message
