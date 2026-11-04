"""The built-in speed test: Lighthouse in headless Chromium, run inside the worker.

This is the same measurement Google PageSpeed Insights makes (Lighthouse, mobile
phone, simulated slow 4G), run on our own server, so no Google API key or quota is
involved. Scores land close to PageSpeed's but not exactly on them: PageSpeed's own
score moves a few points from run to run, and our server's speed differs from
Google's.

Safety: the browser's traffic goes through EgressProxy, which allows public web
servers only. A slot limit (file locks shared by every worker process in the
container) stops several tests running at once and slowing each other down, which
would make scores worse than they really are.

Memory: a test starts only when enough memory is free, and Chrome is marked as the
first thing the kernel may kill if memory runs out anyway. Then one speed test fails
instead of a scan worker (which would restart the worker container).
"""
from __future__ import annotations

import asyncio
import fcntl
import json
import logging
import os
import shlex
import shutil
import signal
import tempfile
import time
from pathlib import Path
from typing import Any

from .egress import EgressProxy

log = logging.getLogger("sitescore.speed")

CHROME_CANDIDATES = ("/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome", "/usr/bin/google-chrome-stable")

# Never shown to visitors; staff see them in the dashboard and the worker log.
SKIP_AUDITS = "full-page-screenshot,screenshot-thumbnails,final-screenshot,network-requests,main-thread-tasks"
# Least time worth starting a test with. Lighthouse needs roughly 15 to 45 seconds.
MIN_RUN_SECONDS = 50
# Longest single attempt, so a hung first try still leaves time for a second one.
MAX_ATTEMPT_SECONDS = 110
# Failures where a second try usually works: the browser crashed, lost contact, or the
# page never painted while the server was busy.
RETRY_ERRORS = {"crashed", "PROTOCOL_TIMEOUT", "NO_FCP", "NO_LCP", "PAGE_HUNG", "TARGET_CRASHED"}


def available_memory_mb() -> int | None:
    """Memory this container can still use, in MB: the smaller of the container limit
    (cgroup v2 or v1) and the machine's available memory. None if it cannot be read."""
    values: list[int] = []
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                values.append(int(line.split()[1]) // 1024)
    except (OSError, ValueError):
        pass
    for limit_file, usage_file in (("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory.current"),
                                   ("/sys/fs/cgroup/memory/memory.limit_in_bytes",
                                    "/sys/fs/cgroup/memory/memory.usage_in_bytes")):
        try:
            limit = Path(limit_file).read_text().strip()
            usage = int(Path(usage_file).read_text().strip())
        except (OSError, ValueError):
            continue
        if limit.isdigit() and int(limit) < 1 << 60:
            values.append(max(0, (int(limit) - usage) // (1024 * 1024)))
        break
    return min(values) if values else None


def _mark_expendable() -> None:
    """Runs in the Lighthouse process before it starts; Chrome inherits it."""
    try:
        with open("/proc/self/oom_score_adj", "w") as fh:
            fh.write("1000")
    except OSError:
        pass


def find_chrome(configured: str | None) -> str | None:
    for path in (configured, os.environ.get("CHROME_PATH"), *CHROME_CANDIDATES):
        if path and Path(path).is_file() and os.access(path, os.X_OK):
            return path
    return None


def lighthouse_command(configured: str) -> list[str] | None:
    cmd = shlex.split(configured or "lighthouse")
    if not cmd:
        return None
    exe = cmd[0] if os.path.isabs(cmd[0]) else shutil.which(cmd[0])
    if not exe or not os.access(exe, os.X_OK):
        return None
    return [exe, *cmd[1:]]


def tools_problem(lighthouse_cmd: str, chrome_path: str | None) -> str | None:
    """A sentence saying what is missing for the speed test, or None if it can run."""
    if lighthouse_command(lighthouse_cmd) is None:
        return f"Lighthouse was not found (SITESCORE_LIGHTHOUSE_CMD={lighthouse_cmd!r})."
    if find_chrome(chrome_path) is None:
        return "Chromium was not found (set SITESCORE_CHROME_PATH)."
    return None


class _Slot:
    """One of N cross-process slots, held with an exclusive file lock."""

    def __init__(self, directory: str, count: int):
        self.directory = Path(directory)
        self.count = max(1, count)
        self._fh = None

    def try_take(self) -> bool:
        self.directory.mkdir(parents=True, exist_ok=True)
        for i in range(self.count):
            fh = open(self.directory / f"slot-{i}.lock", "a+")  # noqa: SIM115 - held until release()
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                fh.close()
                continue
            self._fh = fh
            return True
        return False

    def release(self) -> None:
        if self._fh is not None:
            try:
                fcntl.flock(self._fh, fcntl.LOCK_UN)
            finally:
                self._fh.close()
                self._fh = None


async def run_speed_test(
    url: str,
    *,
    lighthouse_cmd: str = "lighthouse",
    chrome_path: str | None = None,
    slots: int = 2,
    slot_dir: str = "/tmp/sitescore-speed",
    budget: float = 180.0,
    ignore_cert_errors: bool = False,
    min_free_mb: int = 600,
) -> dict[str, Any]:
    """Run Lighthouse (mobile, performance only) on `url`.

    Returns {"lhr": <Lighthouse result>} or {"error": <code>, "detail": <text>}.
    Error codes: no_tools, busy, timeout, crashed, and Lighthouse's own runtime errors
    such as NO_FCP or FAILED_DOCUMENT_REQUEST.
    """
    deadline = time.monotonic() + budget
    cmd = lighthouse_command(lighthouse_cmd)
    chrome = find_chrome(chrome_path)
    if cmd is None or chrome is None:
        return {"error": "no_tools", "detail": tools_problem(lighthouse_cmd, chrome_path) or ""}

    slot = _Slot(slot_dir, slots)
    waited = time.monotonic()
    low_memory = False
    while True:
        if slot.try_take():
            free = available_memory_mb()
            if free is None or free >= min_free_mb:
                break
            # A slot is free but memory is short: give the slot back and wait, rather than
            # start a browser that would push the server out of memory.
            slot.release()
            if not low_memory:
                log.warning("speed test for %s waiting: only %d MB of memory free (needs %d)", url, free, min_free_mb)
                low_memory = True
        if deadline - time.monotonic() < MIN_RUN_SECONDS:
            if low_memory:
                return {"error": "low_memory", "detail": f"Less than {min_free_mb} MB of memory stayed free."}
            return {"error": "busy", "detail": "Every speed-test slot stayed busy."}
        await asyncio.sleep(0.5)
    waited = time.monotonic() - waited
    if waited > 1:
        log.info("speed test for %s waited %.0f s to start", url, waited)
    try:
        result: dict[str, Any] = {"error": "not_run", "detail": ""}
        for attempt in range(2):
            remaining = deadline - time.monotonic()
            if remaining < MIN_RUN_SECONDS:
                break
            result = await _run_once(cmd, chrome, url, min(remaining, MAX_ATTEMPT_SECONDS), ignore_cert_errors)
            if result.get("error") not in RETRY_ERRORS:
                break
            log.warning("speed test for %s failed (%s), trying again", url, result.get("error"))
        return result
    finally:
        slot.release()


async def _run_once(cmd: list[str], chrome: str, url: str, budget: float, ignore_cert_errors: bool) -> dict[str, Any]:
    async with EgressProxy() as proxy:
        flags = [
            "--headless=new", "--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu",
            # A server has no graphics chip. Without this, a WebGL page (three.js and the like)
            # is drawn frame by frame in software, or retries WebGL in a loop, and shows a
            # minute or more of "blocking time" that no phone with a GPU would ever see.
            "--disable-3d-apis",
            f"--proxy-server=http://127.0.0.1:{proxy.port}",
            # Send even localhost through the proxy (Chrome skips the proxy for it by default).
            "--proxy-bypass-list=<-loopback>",
            "--disable-quic", "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
            "--disable-background-networking", "--disable-component-update", "--disable-sync",
            "--disable-default-apps", "--disable-extensions", "--mute-audio", "--no-first-run",
        ]
        if ignore_cert_errors:
            flags.append("--ignore-certificate-errors")
        with tempfile.TemporaryDirectory(prefix="sitescore-lh-") as tmp:
            out = Path(tmp) / "lhr.json"
            args = [
                *cmd, url,
                "--output=json", f"--output-path={out}",
                "--only-categories=performance",
                f"--skip-audits={SKIP_AUDITS}",
                "--quiet",
                f"--max-wait-for-load={int(min(45, max(15, budget - 30)) * 1000)}",
                f"--chrome-flags={' '.join(flags)}",
            ]
            env = {**os.environ, "CHROME_PATH": chrome, "TMPDIR": tmp, "HOME": tmp}
            proc = await asyncio.create_subprocess_exec(
                *args, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
                env=env, start_new_session=True, preexec_fn=_mark_expendable)
            try:
                _, stderr = await asyncio.wait_for(proc.communicate(), timeout=budget)
            except asyncio.TimeoutError:
                _kill_group(proc)
                await proc.wait()
                return {"error": "timeout", "detail": f"No result within {int(budget)} s."}
            except asyncio.CancelledError:
                _kill_group(proc)
                raise
            finally:
                # Chrome helpers can outlive Lighthouse; never leave them running.
                _kill_group(proc)
            if proxy.blocked:
                log.info("speed test for %s: blocked %d requests (%s)", url, len(proxy.blocked),
                         ", ".join(proxy.blocked[:5]))
            if not out.exists():
                tail = (stderr or b"").decode("utf-8", "replace").strip().splitlines()[-3:]
                return {"error": "crashed", "detail": " | ".join(tail)[:300] or f"exit code {proc.returncode}"}
            try:
                lhr = json.loads(out.read_text("utf-8"))
            except (OSError, ValueError) as exc:
                return {"error": "crashed", "detail": f"unreadable result: {exc}"[:300]}
    runtime = lhr.get("runtimeError") or {}
    if runtime.get("code") and runtime.get("code") != "NO_ERROR":
        return {"error": runtime["code"], "detail": (runtime.get("message") or "")[:300]}
    return {"lhr": lhr}


def _kill_group(proc: asyncio.subprocess.Process) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def lab_metrics(lhr: dict[str, Any]) -> dict[str, Any]:
    """The numbers we report, from a Lighthouse result."""
    out: dict[str, Any] = {"source": "lab"}
    perf = (lhr.get("categories") or {}).get("performance") or {}
    if perf.get("score") is not None:
        out["score"] = round(perf["score"] * 100)
    audits = lhr.get("audits") or {}

    def value(audit: str) -> float | None:
        v = (audits.get(audit) or {}).get("numericValue")
        return float(v) if isinstance(v, (int, float)) else None

    lcp, cls, fcp, tbt, si = (value(a) for a in (
        "largest-contentful-paint", "cumulative-layout-shift", "first-contentful-paint",
        "total-blocking-time", "speed-index"))
    if lcp is not None:
        out["lcp_s"] = round(lcp / 1000, 1)
    if cls is not None:
        out["cls"] = round(cls, 3)
    if fcp is not None:
        out["fcp_s"] = round(fcp / 1000, 1)
    if tbt is not None:
        out["tbt_ms"] = round(tbt)
    if si is not None:
        out["si_s"] = round(si / 1000, 1)
    if lhr.get("lighthouseVersion"):
        out["lighthouse"] = lhr["lighthouseVersion"]
    return out


# ---------------------------------------------------------------- optional fallback

PSI_URL = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"


async def pagespeed_fallback(url: str, api_key: str, budget: float) -> dict[str, Any]:
    """Ask Google PageSpeed Insights, when our own browser could not test the page.

    Google runs the same Lighthouse test from its own network, which bot protection
    usually lets through. Only the page address is sent. Returns {"lhr": ...} like
    run_speed_test, or {"error": "pagespeed_...", "detail": ...}.
    """
    import httpx

    deadline = time.monotonic() + budget
    params = {"url": url, "strategy": "mobile", "category": "performance", "key": api_key}
    result: dict[str, Any] = {"error": "pagespeed_not_run", "detail": ""}
    for attempt in range(2):
        remaining = deadline - time.monotonic()
        if remaining < 15:
            break
        try:
            async with httpx.AsyncClient(timeout=remaining) as client:
                r = await client.get(PSI_URL, params=params)
        except httpx.TimeoutException:
            return {"error": "pagespeed_timeout", "detail": f"No answer from Google within {int(remaining)} s."}
        except httpx.HTTPError as exc:
            result = {"error": "pagespeed_failed", "detail": type(exc).__name__}
        else:
            if r.status_code == 200:
                lhr = (r.json() or {}).get("lighthouseResult") or {}
                runtime = lhr.get("runtimeError") or {}
                if runtime.get("code") and runtime.get("code") != "NO_ERROR":
                    return {"error": runtime["code"], "detail": (runtime.get("message") or "")[:300]}
                return {"lhr": lhr, "via": "pagespeed"}
            try:
                message = ((r.json() or {}).get("error") or {}).get("message", "")
            except ValueError:
                message = ""
            result = {"error": f"pagespeed_http_{r.status_code}", "detail": message[:300]}
            if r.status_code != 429 and r.status_code < 500:
                return result  # a key or request problem: trying again will not help
        if attempt == 0:
            await asyncio.sleep(2)
    return result

