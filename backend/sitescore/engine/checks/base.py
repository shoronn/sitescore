"""Check registry. Each check is an async function decorated with @check."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

from ..models import Category, Outcome

CheckFn = Callable[["ScanContext"], Awaitable[Outcome]]  # noqa: F821


@dataclass(frozen=True)
class CheckDef:
    key: str
    name: str
    category: Category
    weight: int
    fn: CheckFn
    # Waits for the speed test, which can take a minute or more: gets the speed test's own time budget.
    slow: bool = False


REGISTRY: list[CheckDef] = []


def check(key: str, name: str, category: Category, weight: int, slow: bool = False):
    def deco(fn: CheckFn) -> CheckFn:
        REGISTRY.append(CheckDef(key, name, category, weight, fn, slow))
        return fn

    return deco


def parse_version(text: str) -> tuple[int, ...]:
    parts = []
    for piece in text.split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)
