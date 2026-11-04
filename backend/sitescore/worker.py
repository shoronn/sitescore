"""Queueing scans and the RQ worker entry point.

Run a worker with:  rq worker sitescore --url $SITESCORE_REDIS_URL
"""
from __future__ import annotations

import asyncio
import logging

from .config import Settings, get_settings

log = logging.getLogger("sitescore.worker")
QUEUE_NAME = "sitescore"

_inline_tasks: set[asyncio.Task] = set()


def _job_setup() -> Settings:
    from .config import check_settings
    from .logs import setup_logging

    settings = get_settings()
    setup_logging(settings.log_level)
    check_settings(settings)
    return settings


def process_scan(scan_id: int) -> None:
    """RQ job. Each job gets a fresh event loop and database pool."""
    from sqlalchemy.pool import NullPool

    from . import db
    from .scans import run_scan_job

    settings = _job_setup()
    db.init_engine(settings.database_url, poolclass=NullPool)
    asyncio.run(run_scan_job(scan_id, settings))


def process_report(scan_id: int) -> None:
    """RQ job: email the PDF report for one scan."""
    from sqlalchemy.pool import NullPool

    from . import db
    from .scans import deliver_report

    settings = _job_setup()
    db.init_engine(settings.database_url, poolclass=NullPool)
    asyncio.run(deliver_report(scan_id, settings))


def schedule_report(scan_id: int, delay_seconds: int, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    if settings.queue_mode == "inline":
        from .scans import deliver_report

        async def later() -> None:
            await asyncio.sleep(delay_seconds)
            await deliver_report(scan_id, settings)

        task = asyncio.get_running_loop().create_task(later())
        _inline_tasks.add(task)
        task.add_done_callback(_inline_tasks.discard)
        return
    from datetime import timedelta

    from redis import Redis
    from rq import Queue, Retry

    queue = Queue(QUEUE_NAME, connection=Redis.from_url(settings.redis_url))
    retry = Retry(max=3, interval=[60, 300, 900])
    if delay_seconds <= 0:
        queue.enqueue(process_report, scan_id, job_timeout=120, retry=retry)
    else:
        # Needs the worker to run with --with-scheduler.
        queue.enqueue_in(timedelta(seconds=delay_seconds), process_report, scan_id, job_timeout=120, retry=retry)


def enqueue_scan(scan_id: int, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    if settings.queue_mode == "inline":
        from .scans import run_scan_job

        task = asyncio.get_running_loop().create_task(run_scan_job(scan_id, settings))
        _inline_tasks.add(task)
        task.add_done_callback(_inline_tasks.discard)
        return
    from redis import Redis
    from rq import Queue

    queue = Queue(QUEUE_NAME, connection=Redis.from_url(settings.redis_url))
    # The speed test may take up to 4 minutes (waiting for a free slot and one retry included).
    queue.enqueue(process_scan, scan_id, job_timeout=480, result_ttl=3600, failure_ttl=86400)


async def wait_inline() -> None:
    """Tests: wait for inline scans to finish."""
    while _inline_tasks:
        await asyncio.gather(*list(_inline_tasks), return_exceptions=True)
