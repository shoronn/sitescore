"""One log format for the API, workers and command-line tools."""
from __future__ import annotations

import logging

_done = False


def setup_logging(level: str = "INFO") -> None:
    global _done
    if _done:
        return
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    for noisy in ("httpx", "httpcore", "fontTools", "weasyprint"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    _done = True
