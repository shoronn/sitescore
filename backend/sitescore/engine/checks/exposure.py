"""Files and folders that should never be public.

Each file is recognised by what is inside it, never by the status code alone: many sites
answer every address with their homepage and a 200, which must not count as a finding.
Only the start of each file is read, and nothing of its contents is kept.
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Callable

from ..models import Category, Outcome, Status
from .base import check


def _looks_html(text: str) -> bool:
    head = text.lstrip()[:200].lower()
    return head.startswith(("<!doctype", "<html", "<head", "<body")) or "<html" in head


def _git_head(body: bytes, text: str) -> bool:
    return bool(re.match(r"ref: refs/[\w./-]+\s*$", text.strip()) or re.fullmatch(r"[0-9a-f]{40}", text.strip()))


def _env_file(body: bytes, text: str) -> bool:
    if _looks_html(text):
        return False
    lines = [ln for ln in text.splitlines() if re.match(r"^\s*(export\s+)?[A-Z][A-Z0-9_]{2,}\s*=", ln)]
    return len(lines) >= 2


def _wp_config(body: bytes, text: str) -> bool:
    return "DB_PASSWORD" in text and "define" in text and not _looks_html(text)


def _sql_dump(body: bytes, text: str) -> bool:
    if _looks_html(text):
        return False
    t = text.upper()
    return "CREATE TABLE" in t or "INSERT INTO" in t or "-- MYSQL DUMP" in t or "-- POSTGRESQL DATABASE DUMP" in t


def _archive(body: bytes, text: str) -> bool:
    return body.startswith(b"PK\x03\x04") or body.startswith(b"\x1f\x8b") or body.startswith(b"Rar!")


def _phpinfo(body: bytes, text: str) -> bool:
    return "phpinfo()" in text and "PHP Version" in text


def _ds_store(body: bytes, text: str) -> bool:
    return body[:8] == b"\x00\x00\x00\x01Bud1"


def _server_status(body: bytes, text: str) -> bool:
    return "Apache Server Status" in text or "Apache Status" in text


def _htpasswd(body: bytes, text: str) -> bool:
    return not _looks_html(text) and bool(re.search(r"^[\w.@-]+:(\$apr1\$|\$2[aby]\$|\{SHA\}|\$1\$|\$5\$|\$6\$)", text, re.M))


def _sftp_json(body: bytes, text: str) -> bool:
    return not _looks_html(text) and '"host"' in text and ('"password"' in text or '"username"' in text)


@dataclass(frozen=True)
class Probe:
    path: str
    label: str
    matches: Callable[[bytes, str], bool]
    severity: str  # "high": passwords or code leak; "medium"; "low"


PROBES: tuple[Probe, ...] = (
    Probe("/.git/HEAD", "the site's Git folder (its full source code and history)", _git_head, "high"),
    Probe("/.env", "a .env settings file (often holds passwords and keys)", _env_file, "high"),
    Probe("/wp-config.php.bak", "a backup of wp-config.php (holds the database password)", _wp_config, "high"),
    Probe("/wp-config.php~", "a backup of wp-config.php (holds the database password)", _wp_config, "high"),
    Probe("/wp-config.old", "a backup of wp-config.php (holds the database password)", _wp_config, "high"),
    Probe("/backup.sql", "a database dump", _sql_dump, "high"),
    Probe("/dump.sql", "a database dump", _sql_dump, "high"),
    Probe("/database.sql", "a database dump", _sql_dump, "high"),
    Probe("/backup.zip", "a website backup archive", _archive, "high"),
    Probe("/backup.tar.gz", "a website backup archive", _archive, "high"),
    Probe("/.htpasswd", "a password file (.htpasswd)", _htpasswd, "high"),
    Probe("/.vscode/sftp.json", "an editor upload file with server login details", _sftp_json, "high"),
    Probe("/phpinfo.php", "a phpinfo page showing the server's full setup", _phpinfo, "medium"),
    Probe("/info.php", "a phpinfo page showing the server's full setup", _phpinfo, "medium"),
    Probe("/.DS_Store", "a .DS_Store file that lists folder contents", _ds_store, "low"),
    Probe("/server-status", "the Apache server status page", _server_status, "low"),
)


async def _probe_all(ctx, probes) -> list[tuple[Probe, object]]:
    results = await asyncio.gather(*(ctx.probe(p.path) for p in probes))
    return list(zip(probes, results))


@check("exposed_files", "Exposed files", Category.SECURITY, 7)
async def check_exposed_files(ctx) -> Outcome:
    if await ctx.site_base() is None:
        return Outcome(Status.NOT_CHECKED, {}, "unreachable")
    found: list[dict] = []
    for probe, res in await _probe_all(ctx, PROBES):
        if res.status == 200 and res.body and probe.matches(res.body, res.text):
            if not any(f["label"] == probe.label for f in found):
                found.append({"path": probe.path, "label": probe.label, "severity": probe.severity})
    ev = {"found": [f"{f['path']} ({f['label']})" for f in found], "checked": len(PROBES)}
    high = [f for f in found if f["severity"] == "high"]
    if high:
        return Outcome(Status.FAIL, ev, "exposed", critical=True)
    if any(f["severity"] == "medium" for f in found):
        return Outcome(Status.FAIL, ev, "info_page")
    if found:
        return Outcome(Status.WARN, ev, "minor")
    return Outcome(Status.PASS, ev, "ok")


FOLDERS = ("/wp-content/uploads/", "/uploads/", "/images/", "/files/", "/backup/", "/backups/")
_LISTING = re.compile(r"<title>\s*Index of /|<h1>\s*Index of /|Directory listing for /|\[To Parent Directory\]", re.I)


@check("directory_listing", "Open folders", Category.SECURITY, 2)
async def check_directory_listing(ctx) -> Outcome:
    if await ctx.site_base() is None:
        return Outcome(Status.NOT_CHECKED, {}, "unreachable")
    results = await asyncio.gather(*(ctx.probe(f, max_bytes=8192) for f in FOLDERS))
    open_dirs = [f for f, r in zip(FOLDERS, results) if r.status == 200 and _LISTING.search(r.text)]
    ev = {"folders": open_dirs}
    if not open_dirs:
        return Outcome(Status.PASS, ev, "ok")
    if any("backup" in f for f in open_dirs):
        return Outcome(Status.FAIL, ev, "backup_listed")
    return Outcome(Status.FAIL, ev, "listed")
