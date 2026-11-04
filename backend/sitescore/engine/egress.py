"""A small HTTP proxy that lets the speed-test browser reach public web servers only.

The browser loads whatever the scanned page asks for: images, scripts, redirects to
other hosts. Every one of those connections goes through this proxy, which resolves
the host itself, refuses private, internal and reserved addresses (the same rule as
the rest of the scanner, see guard.py) and then connects to the checked address, so
a page cannot use the browser to reach anything inside our network.

Supports CONNECT tunnels (https and wss) and plain http requests. Plain http
connections are closed after one response, so a kept-alive browser connection can
never be reused for a different host than the one that was checked.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Callable
from urllib.parse import urlsplit

from . import guard
from .models import ScanError

log = logging.getLogger("sitescore.speed.proxy")

MAX_HEAD_BYTES = 32 * 1024
HOP_HEADERS = {"proxy-connection", "proxy-authorization", "connection", "keep-alive", "te", "trailer", "upgrade"}


class EgressProxy:
    def __init__(
        self,
        allowed_ports: tuple[int, ...] = (80, 443),
        idle_timeout: float = 30.0,
        connect_timeout: float = 5.0,
        max_connections: int = 128,
        resolve: Callable[[str], list[str]] = guard.assert_public_host,
    ):
        self.allowed_ports = allowed_ports
        self.idle_timeout = idle_timeout
        self.connect_timeout = connect_timeout
        self.resolve = resolve
        self._slots = asyncio.Semaphore(max_connections)
        self._server: asyncio.base_events.Server | None = None
        self._tasks: set[asyncio.Task] = set()
        self.blocked: list[str] = []
        self.port = 0
        # One lookup per host for the whole test: a page opens many connections to the same few hosts.
        self._dns: dict[str, list[str] | ScanError] = {}

    async def start(self) -> int:
        self._server = await asyncio.start_server(self._accept, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]
        return self.port

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
        for t in list(self._tasks):
            t.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        if self._server is not None:
            await self._server.wait_closed()

    async def __aenter__(self) -> "EgressProxy":
        await self.start()
        return self

    async def __aexit__(self, *exc) -> None:
        await self.close()

    async def _accept(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        if task is not None:
            self._tasks.add(task)
        try:
            async with self._slots:
                await self._handle(reader, writer)
        except (asyncio.CancelledError, ConnectionError, asyncio.IncompleteReadError, asyncio.LimitOverrunError):
            pass
        except Exception:  # noqa: BLE001 - one bad connection must not stop the proxy
            log.debug("proxy connection failed", exc_info=True)
        finally:
            _close(writer)
            if task is not None:
                self._tasks.discard(task)

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=15)
        except (asyncio.TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError):
            return
        if len(head) > MAX_HEAD_BYTES:
            return await _reply(writer, 431, "Request headers too large")
        lines = head.decode("latin-1").split("\r\n")
        try:
            method, target, version = lines[0].split(" ", 2)
        except ValueError:
            return await _reply(writer, 400, "Bad request")

        if method.upper() == "CONNECT":
            host, _, port_text = target.rpartition(":")
            host = host.strip("[]")
            path = None
        else:
            parts = urlsplit(target)
            if parts.scheme != "http" or not parts.hostname:
                return await _reply(writer, 400, "Only http and https are allowed")
            host, port_text = parts.hostname, str(parts.port or 80)
            path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        try:
            port = int(port_text)
        except ValueError:
            return await _reply(writer, 400, "Bad port")
        if port not in self.allowed_ports:
            self.blocked.append(f"{host}:{port} (port)")
            return await _reply(writer, 403, "Port not allowed")

        ips = await self._lookup(host)
        if isinstance(ips, ScanError):
            self.blocked.append(f"{host} ({ips.code})")
            return await _reply(writer, 403, "Address not allowed")
        upstream = await self._connect(ips, port)
        if upstream is None:
            return await _reply(writer, 502, "Could not connect")
        up_reader, up_writer = upstream
        try:
            if path is None:
                writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                await writer.drain()
            else:
                kept = [line for line in lines[1:] if line and line.split(":", 1)[0].strip().lower() not in HOP_HEADERS]
                new_head = "\r\n".join([f"{method} {path} {version}", *kept, "Connection: close", "", ""])
                up_writer.write(new_head.encode("latin-1"))
                await up_writer.drain()
            await self._pipe(reader, writer, up_reader, up_writer)
        finally:
            _close(up_writer)

    async def _lookup(self, host: str) -> list[str] | ScanError:
        key = host.lower()
        if key not in self._dns:
            try:
                ips = await asyncio.to_thread(self.resolve, host)
                # IPv4 first, like the rest of the scanner: many servers and containers have
                # no working IPv6 route, and waiting on it would stall every request.
                self._dns[key] = sorted(ips, key=lambda ip: ":" in ip)
            except ScanError as exc:
                self._dns[key] = exc
        return self._dns[key]

    async def _connect(self, ips: list[str], port: int):
        for ip in ips[:4]:
            try:
                return await asyncio.wait_for(asyncio.open_connection(ip, port), timeout=self.connect_timeout)
            except (OSError, asyncio.TimeoutError):
                continue
        return None

    async def _pipe(self, c_reader, c_writer, u_reader, u_writer) -> None:
        async def pump(src: asyncio.StreamReader, dst: asyncio.StreamWriter) -> None:
            while True:
                data = await asyncio.wait_for(src.read(65536), timeout=self.idle_timeout)
                if not data:
                    return
                dst.write(data)
                await dst.drain()

        tasks = [asyncio.create_task(pump(c_reader, u_writer)), asyncio.create_task(pump(u_reader, c_writer))]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)


async def _reply(writer: asyncio.StreamWriter, status: int, text: str) -> None:
    body = text.encode()
    writer.write(f"HTTP/1.1 {status} {text}\r\nContent-Type: text/plain\r\nContent-Length: {len(body)}\r\n"
                 f"Connection: close\r\n\r\n".encode() + body)
    try:
        await writer.drain()
    except ConnectionError:
        pass


def _close(writer: asyncio.StreamWriter) -> None:
    try:
        writer.close()
    except Exception:  # noqa: BLE001
        pass
