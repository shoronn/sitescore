"""Shared state for one scan: settings, cached HTTP fetches, DNS and the speed test."""
from __future__ import annotations

import asyncio
import logging
import ssl
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlsplit

import dns.asyncresolver
import dns.exception
import dns.flags
import dns.message
import dns.asyncquery
import dns.rdatatype
import dns.resolver
import httpx

from . import guard
from .models import ScanError

log = logging.getLogger("sitescore.engine")

ENGINE_VERSION = "2.0.0"


@dataclass
class EngineSettings:
    user_agent: str = "MAKTECH-SiteScore/1.0 (+https://sitescore.maktechgroup.com/about)"
    http_timeout: float = 10.0
    dns_timeout: float = 5.0
    check_timeout: float = 45.0
    # Built-in speed test (Lighthouse in headless Chromium, see speedtest.py). The budget
    # covers waiting for a free slot, the test itself and one retry after a browser crash.
    speed_timeout: float = 240.0
    speed_slots: int = 2
    speed_min_free_mb: int = 600
    speed_slot_dir: str = "/tmp/sitescore-speed"
    lighthouse_cmd: str = "lighthouse"
    chrome_path: str | None = None
    # Optional: when our own browser cannot test a page, ask Google PageSpeed Insights.
    psi_api_key: str | None = None
    # Development only: this sandbox's network presents its own certificates.
    speed_ignore_cert_errors: bool = False
    # IP blocklists. Confirm each provider's terms allow commercial use before launch.
    dnsbl_ip_zones: tuple[str, ...] = ("bl.spamcop.net", "psbl.surriel.com", "b.barracudacentral.org")
    dkim_selectors: tuple[str, ...] = (
        "default", "google", "selector1", "selector2", "k1", "k2", "s1", "s2",
        "mail", "dkim", "zoho", "zmail", "mxvault", "smtp", "everlytickey1",
    )
    blocked_networks: tuple[str, ...] = ()
    max_body_bytes: int = 512 * 1024
    skip_speed_test: bool = False


@dataclass
class FetchResult:
    url: str
    final_url: str | None = None
    status: int | None = None
    headers: dict[str, str] = field(default_factory=dict)
    text: str = ""
    history: list[tuple[str, int]] = field(default_factory=list)
    elapsed_ms: int | None = None
    error: str | None = None
    tls_error: bool = False
    cookies: list[str] = field(default_factory=list)  # every Set-Cookie header on the final response
    body: bytes = b""  # raw start of the body, filled only by probe()

    @property
    def ok(self) -> bool:
        return self.status is not None and self.error is None

    def header(self, name: str) -> str | None:
        return self.headers.get(name.lower())


class DNSFailure(Exception):
    """DNS could not answer (timeout, SERVFAIL). Different from "no such record"."""


class DNSClient:
    def __init__(self, timeout: float = 5.0, resolver: Any | None = None):
        self._resolver = resolver or dns.asyncresolver.Resolver()
        self._resolver.lifetime = timeout
        self._resolver.timeout = min(timeout, 3.0)
        self._timeout = timeout
        self._cache: dict[tuple[str, str], list[Any]] = {}

    async def _resolve(self, name: str, rdtype: str) -> list[Any]:
        key = (name.lower(), rdtype)
        if key in self._cache:
            return self._cache[key]
        try:
            answer = await self._resolver.resolve(name, rdtype)
            records = list(answer)
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
            records = []
        except dns.resolver.NoNameservers as exc:
            raise DNSFailure(f"no nameserver answered for {name} {rdtype}") from exc
        except dns.exception.Timeout as exc:
            raise DNSFailure(f"timeout for {name} {rdtype}") from exc
        self._cache[key] = records
        return records

    async def txt(self, name: str) -> list[str]:
        out = []
        for r in await self._resolve(name, "TXT"):
            out.append(b"".join(r.strings).decode("utf-8", "replace"))
        return out

    async def a(self, name: str) -> list[str]:
        return [r.address for r in await self._resolve(name, "A")]

    async def aaaa(self, name: str) -> list[str]:
        return [r.address for r in await self._resolve(name, "AAAA")]

    async def mx(self, name: str) -> list[tuple[int, str]]:
        recs = await self._resolve(name, "MX")
        return sorted((r.preference, r.exchange.to_text().rstrip(".").lower()) for r in recs)

    async def ns(self, name: str) -> list[str]:
        return sorted(r.target.to_text().rstrip(".").lower() for r in await self._resolve(name, "NS"))

    async def ds(self, name: str) -> list[str]:
        """DS records published by the parent zone: present when DNSSEC is switched on."""
        return [r.to_text() for r in await self._resolve(name, "DS")]

    async def caa(self, name: str) -> list[str]:
        return [r.to_text() for r in await self._resolve(name, "CAA")]

    async def soa_at(self, nameserver_ip: str, zone: str) -> bool:
        """True if `nameserver_ip` answers authoritatively for `zone`."""
        q = dns.message.make_query(zone, dns.rdatatype.SOA)
        try:
            resp = await dns.asyncquery.udp(q, nameserver_ip, timeout=self._timeout)
        except Exception:  # noqa: BLE001 - any failure means it did not answer
            return False
        return bool(resp.flags & dns.flags.AA) and len(resp.answer) > 0


class ScanContext:
    def __init__(
        self,
        target: str,
        settings: EngineSettings | None = None,
        http_client: httpx.AsyncClient | None = None,
        dns_client: Any | None = None,
        skip_guard: bool = False,
    ):
        self.settings = settings or EngineSettings()
        guard.set_blocked_networks(list(self.settings.blocked_networks))
        self.target = target
        self.host, self.apex = guard.normalize_target(target)
        self.skip_guard = skip_guard
        self.ips: list[str] = []
        self._own_client = http_client is None
        # trust_env=False: connections to scanned sites always go direct. A proxy from the
        # environment would resolve hostnames itself and undo the pinning to checked IPs.
        self.http = http_client or httpx.AsyncClient(
            headers={"User-Agent": self.settings.user_agent, "Accept": "text/html,*/*;q=0.8"},
            timeout=self.settings.http_timeout,
            follow_redirects=False,
            trust_env=False,
            # The operating system's trusted certificates, the same store the raw TLS check uses,
            # so the two can never disagree about a certificate.
            verify=ssl.create_default_context(),
        )
        self._insecure_http: httpx.AsyncClient | None = None
        self.dns = dns_client or DNSClient(self.settings.dns_timeout)
        self._fetch_cache: dict[tuple, FetchResult] = {}
        self._fetch_locks: dict[tuple, asyncio.Lock] = {}
        self._speed: dict[str, Any] | None = None
        self._speed_lock = asyncio.Lock()
        # Polite limit for the small path probes (exposed files, open folders).
        self._probe_sem = asyncio.Semaphore(6)
        self.shared: dict[str, Any] = {}

    async def prepare(self) -> None:
        """Resolve the target and refuse private addresses. Raises ScanError."""
        if self.skip_guard:
            return
        ips = await asyncio.to_thread(guard.assert_public_host, self.host)
        self.ips = sorted(ips, key=lambda ip: ":" in ip)

    @property
    def connect_address(self) -> str:
        """Where raw TLS probes connect: the checked IP, or the hostname when the guard is off."""
        return self.ips[0] if self.ips else self.host

    async def close(self) -> None:
        if self._own_client:
            await self.http.aclose()
        if self._insecure_http is not None:
            await self._insecure_http.aclose()

    def _client(self, verify: bool) -> httpx.AsyncClient:
        if verify:
            return self.http
        if self._insecure_http is None:
            self._insecure_http = httpx.AsyncClient(
                headers=dict(self.http.headers), timeout=self.settings.http_timeout,
                follow_redirects=False, verify=False, trust_env=False,
            )
        return self._insecure_http

    async def _resolve_hop(self, url: str) -> list[str]:
        """Check the hop's host and return its public IPs (IPv4 first). Empty when the guard is off."""
        if self.skip_guard:
            return []
        host = urlsplit(url).hostname or ""
        ips = await asyncio.to_thread(guard.assert_public_host, host)
        return sorted(ips, key=lambda ip: ":" in ip)

    @staticmethod
    def _request(client: httpx.AsyncClient, url: str, ips: list[str]) -> httpx.Request:
        """Build a GET that connects to the checked IP, not to whatever DNS answers next.

        Without this, a domain could resolve to a public address for the check and to an
        internal one for the connection (DNS rebinding). The Host header and TLS server
        name still carry the real hostname, so virtual hosts and certificates work.
        """
        if not ips:
            return client.build_request("GET", url)
        parts = urlsplit(url)
        host = parts.hostname or ""
        ip = ips[0]
        port = f":{parts.port}" if parts.port else ""
        pinned = parts._replace(netloc=(f"[{ip}]" if ":" in ip else ip) + port).geturl()
        return client.build_request("GET", pinned, headers={"Host": host + port},
                                    extensions={"sni_hostname": host})

    async def fetch(self, url: str, verify: bool = True, max_redirects: int = 6,
                    headers: dict[str, str] | None = None) -> FetchResult:
        """GET `url`, following redirects by hand so every hop passes the SSRF guard."""
        key = (url, verify, tuple(sorted((headers or {}).items())))
        lock = self._fetch_locks.setdefault(key, asyncio.Lock())
        async with lock:
            if key in self._fetch_cache:
                return self._fetch_cache[key]
            result = await self._do_fetch(url, verify, max_redirects, headers)
            self._fetch_cache[key] = result
            return result

    async def _do_fetch(self, url: str, verify: bool, max_redirects: int,
                        headers: dict[str, str] | None = None) -> FetchResult:
        result = FetchResult(url=url)
        client = self._client(verify)
        current = url
        start = time.perf_counter()
        try:
            for _ in range(max_redirects + 1):
                ips = await self._resolve_hop(current)
                req = self._request(client, current, ips)
                for name, value in (headers or {}).items():
                    req.headers[name] = value
                resp = await client.send(req, stream=True)
                try:
                    if resp.is_redirect and "location" in resp.headers:
                        nxt = urljoin(current, resp.headers["location"])
                        result.history.append((current, resp.status_code))
                        if urlsplit(nxt).scheme not in ("http", "https"):
                            break
                        current = nxt
                        continue
                    body = b""
                    async for chunk in resp.aiter_bytes():
                        body += chunk
                        if len(body) >= self.settings.max_body_bytes:
                            break
                    result.final_url = current
                    result.status = resp.status_code
                    result.headers = {k.lower(): v for k, v in resp.headers.items()}
                    result.cookies = resp.headers.get_list("set-cookie")
                    result.text = body.decode(resp.encoding or "utf-8", "replace")
                    break
                finally:
                    await resp.aclose()
            else:
                result.error = "too many redirects"
        except ScanError as exc:
            result.error = exc.message
        except httpx.ConnectError as exc:
            msg = str(exc)
            result.tls_error = "CERTIFICATE" in msg.upper() or "SSL" in msg.upper()
            result.error = "tls" if result.tls_error else "connect"
        except httpx.TimeoutException:
            result.error = "timeout"
        except httpx.HTTPError as exc:
            result.error = type(exc).__name__
        result.elapsed_ms = int((time.perf_counter() - start) * 1000)
        return result

    async def timed_get(self, url: str) -> tuple[int | None, float | None, str | None]:
        """One GET without redirects; returns (status, time to first byte in seconds, error)."""
        try:
            ips = await self._resolve_hop(url)
            start = time.perf_counter()
            resp = await self.http.send(self._request(self.http, url, ips), stream=True)
            ttfb = time.perf_counter() - start
            await resp.aclose()
            return resp.status_code, ttfb, None
        except ScanError as exc:
            return None, None, exc.message
        except httpx.TimeoutException:
            return None, None, "timeout"
        except httpx.HTTPError as exc:
            return None, None, type(exc).__name__

    async def main_page(self) -> FetchResult:
        """The homepage over HTTPS if it works, else over HTTP."""
        https = await self.fetch(f"https://{self.host}/")
        if https.ok:
            return https
        if https.tls_error:
            insecure = await self.fetch(f"https://{self.host}/", verify=False)
            if insecure.ok:
                return insecure
        return await self.fetch(f"http://{self.host}/")

    async def site_base(self) -> tuple[str, bool] | None:
        """(scheme://host, verify) of the working homepage, or None if the site did not load."""
        page = await self.main_page()
        if not page.ok or not page.final_url:
            return None
        parts = urlsplit(page.final_url)
        verify = not (parts.scheme == "https" and (await self.fetch(f"https://{self.host}/")).tls_error)
        return f"{parts.scheme}://{parts.netloc}", verify

    async def probe(self, path: str, max_bytes: int = 4096, timeout: float = 6.0) -> FetchResult:
        """GET one path on the site without following redirects, reading only the start.

        Used to see whether a file that should be private can be downloaded. Only the
        first few KB are read, to recognise the file type; nothing is stored.
        """
        result = FetchResult(url=path)
        base = await self.site_base()
        if base is None:
            result.error = "unreachable"
            return result
        root, verify = base
        url = root + path
        result.url = url
        client = self._client(verify)
        async with self._probe_sem:
            try:
                ips = await self._resolve_hop(url)
                req = self._request(client, url, ips)
                req.extensions["timeout"] = httpx.Timeout(timeout).as_dict()
                resp = await client.send(req, stream=True)
                try:
                    body = b""
                    async for chunk in resp.aiter_bytes():
                        body += chunk
                        if len(body) >= max_bytes:
                            break
                    result.status = resp.status_code
                    result.final_url = url
                    result.headers = {k.lower(): v for k, v in resp.headers.items()}
                    result.body = body[:max_bytes]
                    result.text = result.body.decode(resp.encoding or "utf-8", "replace")
                finally:
                    await resp.aclose()
            except ScanError as exc:
                result.error = exc.message
            except httpx.TimeoutException:
                result.error = "timeout"
            except httpx.HTTPError as exc:
                result.error = type(exc).__name__
        return result

    async def page_info(self):
        """The homepage HTML, parsed once and shared by the checks that read it."""
        from .html import parse_page

        if "page_info" not in self.shared:
            page = await self.main_page()
            ctype = (page.header("content-type") or "").lower()
            is_html = page.ok and ("html" in ctype or page.text.lstrip()[:15].lower().startswith(("<!doctype", "<html")))
            self.shared["page_info"] = parse_page(page.text) if is_html else None
        return self.shared["page_info"]

    async def dns_ok(self) -> bool:
        """Sanity check before trusting "record missing" answers.

        Every real domain has NS records. If we cannot see them, the resolver is
        not giving full answers, and DNS-based checks must say "not checked"
        rather than report records as missing.
        """
        if "dns_ok" not in self.shared:
            try:
                self.shared["dns_ok"] = bool(await self.dns.ns(self.apex))
            except DNSFailure:
                self.shared["dns_ok"] = False
        return self.shared["dns_ok"]

    async def speed_test(self) -> dict[str, Any]:
        """One Lighthouse run (mobile), shared by both performance checks.

        Our own browser first. If it cannot test the page and a PageSpeed key is set, Google
        PageSpeed Insights is asked instead, within the same overall time limit.
        """
        from .speedtest import pagespeed_fallback, run_speed_test

        async with self._speed_lock:
            if self._speed is not None:
                return self._speed
            if self.settings.skip_speed_test:
                self._speed = {"error": "skipped"}
                return self._speed
            page = await self.main_page()
            if not page.ok:
                self._speed = {"error": "unreachable"}
                return self._speed
            url = page.final_url or f"https://{self.host}/"
            # The homepage only loaded with certificate checks off: test it the same way.
            insecure = url.startswith("https://") and (await self.fetch(f"https://{self.host}/")).tls_error
            s = self.settings
            started = time.monotonic()
            self._speed = await run_speed_test(
                url, lighthouse_cmd=s.lighthouse_cmd, chrome_path=s.chrome_path, slots=s.speed_slots,
                slot_dir=s.speed_slot_dir, budget=s.speed_timeout, min_free_mb=s.speed_min_free_mb,
                ignore_cert_errors=insecure or s.speed_ignore_cert_errors)
            if "error" in self._speed:
                log.warning("speed test for %s: %s %s", url, self._speed["error"], self._speed.get("detail", ""))
                # What is left of the speed checks' time limit (see runner._run_one), with a margin.
                left = s.speed_timeout + s.check_timeout - (time.monotonic() - started) - 10
                if s.psi_api_key and left >= 30:
                    ours = self._speed
                    google = await pagespeed_fallback(url, s.psi_api_key, min(left, 120))
                    if "lhr" in google:
                        log.info("speed test for %s: used Google PageSpeed after %s", url, ours["error"])
                        self._speed = {**google, "local_error": ours["error"]}
                    else:
                        log.warning("speed test for %s: Google PageSpeed failed too: %s %s", url,
                                    google["error"], google.get("detail", ""))
            return self._speed
