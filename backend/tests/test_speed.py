"""The built-in speed test: outbound filter, slot limit, and (when installed) a real browser run."""
from __future__ import annotations

import asyncio
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from sitescore.engine import guard
from sitescore.engine.egress import EgressProxy
from sitescore.engine.models import ScanError, Status
from sitescore.engine.speedtest import _Slot, run_speed_test, tools_problem


class _Server:
    """A local web server that counts the requests it receives."""

    def __init__(self):
        hits = self.hits = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                hits.append((self.path, dict(self.headers)))
                body = b"<html><body><h1>internal</h1></body></html>"
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def server():
    s = _Server()
    yield s
    s.close()


def fake_resolve(host: str) -> list[str]:
    """public.test stands for a public website (served locally); everything else is private."""
    if host == "public.test":
        return ["127.0.0.1"]
    raise ScanError("private", f"{host} is private")


async def _request(port: int, raw: bytes) -> bytes:
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(raw)
    await writer.drain()
    data = await asyncio.wait_for(reader.read(65536), timeout=5)
    writer.close()
    return data


async def test_proxy_forwards_public_http_and_closes_after_one_response(server):
    async with EgressProxy(allowed_ports=(server.port,), resolve=fake_resolve) as proxy:
        resp = await _request(proxy.port, (
            f"GET http://public.test:{server.port}/page?x=1 HTTP/1.1\r\nHost: public.test:{server.port}\r\n"
            f"Proxy-Connection: keep-alive\r\nConnection: keep-alive\r\n\r\n").encode())
    assert resp.startswith(b"HTTP/1.0 200") or resp.startswith(b"HTTP/1.1 200")
    path, headers = server.hits[0]
    assert path == "/page?x=1"
    assert headers.get("Connection") == "close" and "Proxy-Connection" not in headers


async def test_proxy_refuses_private_hosts_and_other_ports(server):
    async with EgressProxy(allowed_ports=(server.port,), resolve=fake_resolve) as proxy:
        private = await _request(proxy.port, f"CONNECT internal.test:{server.port} HTTP/1.1\r\n\r\n".encode())
        port = await _request(proxy.port, b"CONNECT public.test:22 HTTP/1.1\r\n\r\n")
        ftp = await _request(proxy.port, b"GET ftp://public.test/ HTTP/1.1\r\n\r\n")
    assert private.startswith(b"HTTP/1.1 403") and port.startswith(b"HTTP/1.1 403") and ftp.startswith(b"HTTP/1.1 400")
    assert server.hits == []
    assert any("internal.test" in b for b in proxy.blocked)


async def test_proxy_uses_the_real_guard_by_default(server):
    """With the scanner's own guard, loopback and metadata addresses are refused."""
    async with EgressProxy(allowed_ports=(80, 443, server.port)) as proxy:
        for target in (f"127.0.0.1:{server.port}", f"localhost:{server.port}", "169.254.169.254:80"):
            resp = await _request(proxy.port, f"CONNECT {target} HTTP/1.1\r\n\r\n".encode())
            assert resp.startswith(b"HTTP/1.1 403"), target
        resp = await _request(proxy.port, f"GET http://127.0.0.1:{server.port}/ HTTP/1.1\r\n\r\n".encode())
        assert resp.startswith(b"HTTP/1.1 403")
    assert server.hits == []


async def test_connect_tunnel_pipes_both_ways(server):
    async with EgressProxy(allowed_ports=(server.port,), resolve=fake_resolve) as proxy:
        reader, writer = await asyncio.open_connection("127.0.0.1", proxy.port)
        writer.write(f"CONNECT public.test:{server.port} HTTP/1.1\r\n\r\n".encode())
        await writer.drain()
        assert (await reader.readuntil(b"\r\n\r\n")).startswith(b"HTTP/1.1 200")
        writer.write(b"GET /tunnel HTTP/1.1\r\nHost: public.test\r\nConnection: close\r\n\r\n")
        await writer.drain()
        # The server closes after its answer; read until then (headers and body may arrive apart).
        body = b""
        while chunk := await asyncio.wait_for(reader.read(65536), timeout=5):
            body += chunk
        writer.close()
    assert b"internal" in body and server.hits[0][0] == "/tunnel"


def test_slots_are_shared_between_processes(tmp_path):
    a, b = _Slot(str(tmp_path), 1), _Slot(str(tmp_path), 1)
    assert a.try_take() and not b.try_take()
    a.release()
    assert b.try_take()
    b.release()
    two = [_Slot(str(tmp_path), 2) for _ in range(3)]
    assert [s.try_take() for s in two] == [True, True, False]
    for s in two:
        s.release()


async def test_busy_slots_give_up_in_time(tmp_path, monkeypatch):
    from sitescore.engine import speedtest

    monkeypatch.setattr(speedtest, "lighthouse_command", lambda c: ["/bin/true"])
    monkeypatch.setattr(speedtest, "find_chrome", lambda c: "/bin/true")
    held = _Slot(str(tmp_path), 1)
    assert held.try_take()
    try:
        out = await run_speed_test("https://example.com/", slots=1, slot_dir=str(tmp_path), budget=speedtest.MIN_RUN_SECONDS - 1)
    finally:
        held.release()
    assert out["error"] == "busy"


async def test_missing_tools_are_reported():
    out = await run_speed_test("https://example.com/", lighthouse_cmd="/nonexistent/lighthouse")
    assert out["error"] == "no_tools" and "Lighthouse" in out["detail"]


LIGHTHOUSE = os.environ.get("SITESCORE_LIGHTHOUSE_CMD", "lighthouse")
CHROME = os.environ.get("SITESCORE_CHROME_PATH")


@pytest.mark.skipif(tools_problem(LIGHTHOUSE, CHROME) is not None, reason="Lighthouse and Chromium not installed")
async def test_real_browser_cannot_reach_this_machine(server, tmp_path):
    """End to end: the speed-test browser is refused a local server, which never sees a request."""
    guard.set_blocked_networks([])
    out = await run_speed_test(f"http://127.0.0.1:{server.port}/", lighthouse_cmd=LIGHTHOUSE, chrome_path=CHROME,
                               slots=1, slot_dir=str(tmp_path), budget=90)
    assert "lhr" not in out, out
    assert server.hits == []


# ---------------------------------------------------------------- IPv4 first, DNS once per test

async def test_proxy_prefers_ipv4_and_looks_each_host_up_once(server):
    calls = []

    def resolve(host):
        calls.append(host)
        # A dead IPv6 address listed first, as getaddrinfo often does: it must not be tried first.
        return ["2001:db8::1", "127.0.0.1"]

    async with EgressProxy(allowed_ports=(server.port,), resolve=resolve, connect_timeout=0.5) as proxy:
        for _ in range(3):
            resp = await _request(proxy.port, (f"GET http://public.test:{server.port}/x HTTP/1.1\r\n"
                                               f"Host: public.test\r\n\r\n").encode())
            assert b" 200 " in resp.split(b"\r\n", 1)[0]
    assert calls == ["public.test"] and len(server.hits) == 3


# ---------------------------------------------------------------- Google PageSpeed as the backup

async def test_pagespeed_is_used_only_when_our_test_fails(monkeypatch):
    from sitescore.engine import speedtest
    from sitescore.engine.checks import performance
    from test_engine import LHR, make_ctx

    from sitescore.engine import EngineSettings

    asked = []

    async def ours_fails(url, **kw):
        return {"error": "ERRORED_DOCUMENT_REQUEST", "detail": "(Status code: 403)"}

    async def google(url, key, budget):
        asked.append((url, key))
        return {"lhr": LHR, "via": "pagespeed"}

    monkeypatch.setattr(speedtest, "run_speed_test", ours_fails)
    monkeypatch.setattr(speedtest, "pagespeed_fallback", google)

    # No key: no fallback, the checks say why they were not checked.
    ctx = make_ctx(settings=EngineSettings())
    out = await performance.check_mobile_speed(ctx)
    assert out.status == Status.NOT_CHECKED and out.reason == "speed_blocked" and asked == []

    # With a key, Google's result is used and the wording says who measured it.
    ctx = make_ctx(settings=EngineSettings(psi_api_key="k"))
    from sitescore.engine.runner import _run_one
    from sitescore.engine.checks import CHECKS

    result = await _run_one(ctx, next(c for c in CHECKS if c.key == "mobile_speed"))
    assert result.status == Status.WARN and result.evidence["score"] == 62
    assert result.summary.startswith("Google PageSpeed Insights scores your site 62")
    assert result.evidence["local_error"] == "ERRORED_DOCUMENT_REQUEST" and asked == [("https://example.com/", "k")]


async def test_our_own_result_never_calls_google(monkeypatch):
    from sitescore.engine import EngineSettings, speedtest
    from sitescore.engine.checks import CHECKS
    from sitescore.engine.runner import _run_one
    from test_engine import LHR, make_ctx

    async def ours(url, **kw):
        return {"lhr": LHR}

    async def google(url, key, budget):
        raise AssertionError("Google must not be asked when our own test worked")

    monkeypatch.setattr(speedtest, "run_speed_test", ours)
    monkeypatch.setattr(speedtest, "pagespeed_fallback", google)
    result = await _run_one(make_ctx(settings=EngineSettings(psi_api_key="k")),
                            next(c for c in CHECKS if c.key == "mobile_speed"))
    assert result.summary.startswith("Our speed test scores your site 62")


def test_pretty_phone():
    from sitescore.report import pretty_phone

    assert pretty_phone("8801897669234") == "+880 1897 669234"
    assert pretty_phone("+44 20 7946 0000") == "+442079460000"
    assert pretty_phone(None) is None
