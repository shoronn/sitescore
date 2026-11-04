"""Command-line runner: `sitescore scan example.com`."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from .engine import EngineSettings, ScanError, run_scan
from .engine.scoring import agent_level, band_label

COLORS = {"pass": "\033[32m", "warn": "\033[33m", "fail": "\033[31m", "not_checked": "\033[90m"}
ICONS = {"pass": "PASS", "warn": "WARN", "fail": "FAIL", "not_checked": " -- "}
RESET, BOLD = "\033[0m", "\033[1m"


def _c(text: str, status: str, use_color: bool) -> str:
    return f"{COLORS[status]}{text}{RESET}" if use_color else text


async def _scan(args: argparse.Namespace) -> int:
    from .config import engine_settings

    settings: EngineSettings = engine_settings()
    settings.skip_speed_test = args.no_speed
    color = sys.stdout.isatty() and not args.json

    def progress(r) -> None:
        if not args.json and not args.quiet:
            print(f"  {_c(ICONS[r.status.value], r.status.value, color)}  {r.name:<26} {r.title}", flush=True)

    if not args.json:
        title = f"{BOLD}MAKTECH SiteScore{RESET}" if color else "MAKTECH SiteScore"
        print(f"{title}  scanning {args.target} ...\n")
    try:
        report = await run_scan(args.target, settings=settings, on_result=progress)
    except ScanError as exc:
        if args.json:
            print(json.dumps({"error": exc.code, "message": exc.message}))
        else:
            print(f"Cannot scan: {exc.message}")
        return 2
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
        return 0
    print()
    agent = "n/a" if report.agent_score is None else f"{report.agent_score}/100"
    print(f"AI agent readiness: {agent}  ({agent_level(report.agent_score)[1] or 'not enough data'})")
    score = "n/a" if report.score is None else f"{report.score}/100"
    print(f"Health score: {score}  ({band_label(report.band) or 'not enough data'})"
          + ("  [capped by a critical finding]" if report.capped else ""))
    if report.coverage < 70:
        print(f"Partial scan: only {report.coverage} of 100 points could be checked.")
    for c in report.categories:
        s = "n/a" if c.score is None else f"{c.score}"
        print(f"  {c.label:<18} {s:>4}   ({c.earned:g} of {c.available} points)")
    print(f"\nFinished in {report.duration_ms / 1000:.1f} s, engine {report.engine_version}")
    return 0


async def _test_speed(target: str) -> int:
    """Run the speed test alone, with the scanner's settings, and print what happened."""
    import time

    from .config import engine_settings
    from .engine.context import ScanContext
    from .engine.speedtest import lab_metrics, tools_problem

    settings = engine_settings()
    problem = tools_problem(settings.lighthouse_cmd, settings.chrome_path)
    if problem:
        print(f"Speed test cannot run here: {problem}")
        return 1
    try:
        ctx = ScanContext(target, settings=settings)
        await ctx.prepare()
    except ScanError as exc:
        print(f"Cannot scan: {exc.message}")
        return 2
    print(f"Testing {target} (slots: {settings.speed_slots}, time limit: {settings.speed_timeout:.0f} s) ...")
    start = time.monotonic()
    try:
        data = await ctx.speed_test()
    finally:
        await ctx.close()
    took = time.monotonic() - start
    if "lhr" not in data:
        print(f"Failed after {took:.0f} s: {data.get('error')} {data.get('detail', '')}".rstrip())
        return 1
    m = lab_metrics(data["lhr"])
    print(f"Mobile speed score {m.get('score')}/100 in {took:.0f} s (Lighthouse {m.get('lighthouse')})")
    print(f"  Largest content shown: {m.get('lcp_s')} s   Layout shift: {m.get('cls')}   "
          f"Blocking time: {m.get('tbt_ms')} ms   First content: {m.get('fcp_s')} s")
    return 0


async def _staff(args: argparse.Namespace) -> int:
    import getpass

    from sqlalchemy import select

    from . import db
    from .config import get_settings
    from .staff_auth import hash_password

    db.init_engine(get_settings().database_url)
    email = args.email.strip().lower()
    async with db.sessionmaker()() as session:
        staff = await session.scalar(select(db.Staff).where(db.Staff.email == email))
        if args.cmd == "create-staff":
            if args.password_stdin:
                password = sys.stdin.readline().rstrip("\n")
            else:
                password = getpass.getpass("Password (12+ characters): ")
                if getpass.getpass("Repeat password: ") != password:
                    print("Passwords do not match.")
                    return 1
            if len(password) < 12:
                print("Use at least 12 characters.")
                return 1
            if staff is None:
                staff = db.Staff(email=email, name=args.name or email.split("@")[0], role=args.role,
                                 password_hash=hash_password(password))
                session.add(staff)
                print(f"Created {args.role} account for {email}. They set up their authenticator app at first sign-in.")
            else:
                staff.password_hash, staff.is_active = hash_password(password), True
                if args.name:
                    staff.name = args.name
                staff.role = args.role
                print(f"Updated the password for {email}.")
        elif staff is None:
            print(f"No staff account for {email}.")
            return 1
        elif args.cmd == "reset-staff-2fa":
            staff.totp_secret = None
            print(f"{email} will set up their authenticator app again at next sign-in.")
        elif args.cmd == "disable-staff":
            staff.is_active = False
            print(f"{email} can no longer sign in.")
        elif args.cmd == "set-staff-role":
            staff.role = args.role
            print(f"{email} is now {args.role}." + (" Admins can clear all leads." if args.role == "admin" else ""))
        await session.commit()
    await db.get_engine().dispose()
    return 0


async def _cleanup() -> int:
    from . import db
    from .config import get_settings
    from .maintenance import cleanup

    settings = get_settings()
    db.init_engine(settings.database_url)
    result = await cleanup(settings)
    await db.get_engine().dispose()
    print("Deleted: {leads} leads with {scans} scans past {days} days.".format(
        days=settings.lead_retention_days, **result))
    return 0


async def _send_test_email(to: str) -> int:
    """Send a plain test email with the live SMTP settings and say exactly what happened."""
    from . import mailer
    from .config import get_settings
    from .scans import describe_send_error

    settings = get_settings()
    if not settings.smtp_host:
        print("SMTP is not configured (SITESCORE_SMTP_HOST is empty), so nothing can be emailed.", file=sys.stderr)
        return 1
    msg = mailer.Outgoing(
        to=to, subject="SiteScore test email",
        text="This is a test from SiteScore. If you can read it, report emails can be delivered.\n",
        html="<p>This is a test from SiteScore. If you can read it, report emails can be delivered.</p>")
    print(f"Sending a test email to {to} through {settings.smtp_host}:{settings.smtp_port} as {settings.smtp_user}...")
    try:
        await mailer.send(settings, msg)
    except Exception as exc:  # noqa: BLE001
        print(f"Failed: {describe_send_error(exc)}", file=sys.stderr)
        return 1
    print("Sent. If it does not arrive within a few minutes, check the spam folder and the domain's SPF and DKIM records.")
    return 0


async def _send_report(token: str) -> int:
    """Email one scan's PDF report again, right now, and report the outcome."""
    from sqlalchemy import select, update

    from . import db
    from .config import get_settings
    from .scans import deliver_report

    settings = get_settings()
    db.init_engine(settings.database_url)
    token = token.rstrip("/").rsplit("/", 1)[-1]  # accept a full results link too
    try:
        async with db.sessionmaker()() as session:
            scan = await session.scalar(select(db.Scan).where(db.Scan.token == token))
            if scan is None:
                print("No scan with that token.", file=sys.stderr)
                return 1
            if scan.status != "done":
                print(f"That scan is {scan.status}; reports are sent for finished scans.", file=sys.stderr)
                return 1
            await session.execute(update(db.Scan).where(db.Scan.id == scan.id).values(emailed_at=None, report_error=None))
            await session.commit()
            scan_id = scan.id
        try:
            await deliver_report(scan_id, settings)
        except Exception as exc:  # noqa: BLE001
            from .scans import describe_send_error

            print(f"Failed: {describe_send_error(exc)}", file=sys.stderr)
            return 1
        print("Report sent.")
        return 0
    finally:
        await db.get_engine().dispose()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="sitescore", description="MAKTECH SiteScore website health scanner")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan", help="scan one website")
    s.add_argument("target", help="domain or URL, e.g. example.com")
    s.add_argument("--json", action="store_true", help="print the full report as JSON")
    s.add_argument("--quiet", action="store_true", help="only print the summary")
    s.add_argument("--no-speed", action="store_true", help="skip the speed test (Lighthouse)")
    t = sub.add_parser("test-speed", help="run only the speed test on one website and show the result or the exact error")
    t.add_argument("target", help="domain or URL, e.g. example.com")
    c = sub.add_parser("create-staff", help="create a dashboard account, or reset its password")
    c.add_argument("email")
    c.add_argument("--name", help="shown in the dashboard, e.g. Rahim")
    c.add_argument("--role", choices=["sales", "admin"], default="sales")
    c.add_argument("--password-stdin", action="store_true", help="read the password from standard input")
    for name, text in (("reset-staff-2fa", "make someone set up their authenticator app again"),
                       ("disable-staff", "stop someone signing in")):
        sub.add_parser(name, help=text).add_argument("email")
    sr = sub.add_parser("set-staff-role", help="make someone an admin (can clear all leads) or sales")
    sr.add_argument("email")
    sr.add_argument("role", choices=["sales", "admin"])
    sub.add_parser("cleanup", help="delete leads past the retention period (run daily)")
    sub.add_parser("send-test-email", help="send a test email with the SMTP settings").add_argument("to")
    sub.add_parser("send-report", help="email a scan's PDF report again now").add_argument(
        "token", help="the scan token or its results link")
    sub.add_parser("check-config", help="check the settings before starting (used by the Docker image)")
    args = p.parse_args(argv)
    if args.cmd == "check-config":
        from .config import ConfigError, check_settings, get_settings
        from .logs import setup_logging

        setup_logging()
        try:
            check_settings(get_settings())
        except ConfigError as exc:
            print(exc, file=sys.stderr)
            return 1
        print("Settings look good.")
        return 0
    if args.cmd == "cleanup":
        return asyncio.run(_cleanup())
    if args.cmd == "send-test-email":
        return asyncio.run(_send_test_email(args.to))
    if args.cmd == "send-report":
        return asyncio.run(_send_report(args.token))
    if args.cmd == "scan":
        return asyncio.run(_scan(args))
    if args.cmd == "test-speed":
        return asyncio.run(_test_speed(args.target))
    return asyncio.run(_staff(args))


if __name__ == "__main__":
    raise SystemExit(main())
