"""Input normalisation and SSRF protection.

Every host the scanner touches (the target and every redirect hop) goes through
`assert_public_host`, so the public form can never be used to reach private or
internal addresses.
"""
from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urlsplit

import tldextract

from .models import ScanError

# Offline extractor: uses the public suffix list bundled with tldextract.
_extract = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None)

_LABEL = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")

# Extra ranges to refuse on top of non-global addresses (set from settings).
BLOCKED_NETWORKS: list[ipaddress._BaseNetwork] = []


def set_blocked_networks(cidrs: list[str]) -> None:
    BLOCKED_NETWORKS.clear()
    for c in cidrs:
        c = c.strip()
        if c:
            BLOCKED_NETWORKS.append(ipaddress.ip_network(c, strict=False))


def normalize_target(raw: str) -> tuple[str, str]:
    """Turn what a visitor typed into (host, apex).

    "https://www.Example.com/about?x=1" -> ("www.example.com", "example.com")
    """
    if not raw or not raw.strip():
        raise ScanError("empty", "Please enter a website address.")
    text = raw.strip()
    if "://" not in text:
        text = "http://" + text
    try:
        parts = urlsplit(text)
    except ValueError as exc:
        raise ScanError("invalid", "That does not look like a website address.") from exc
    if parts.scheme not in ("http", "https"):
        raise ScanError("invalid", "Only http and https websites can be scanned.")
    if parts.port not in (None, 80, 443):
        raise ScanError("invalid", "Only standard web ports (80 and 443) can be scanned.")
    host = (parts.hostname or "").rstrip(".").lower()
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ScanError("invalid", "That does not look like a website address.") from exc
    if not host or len(host) > 253:
        raise ScanError("invalid", "That does not look like a website address.")
    try:
        ipaddress.ip_address(host)
        raise ScanError("ip_address", "Please enter a domain name, not an IP address.")
    except ValueError:
        pass
    labels = host.split(".")
    if len(labels) < 2 or not all(_LABEL.match(label) for label in labels):
        raise ScanError("invalid", "That does not look like a website address.")
    ext = _extract(host)
    if not ext.suffix or not ext.domain:
        raise ScanError("invalid", "That does not look like a public website address.")
    apex = f"{ext.domain}.{ext.suffix}"
    return host, apex


def is_public_ip(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    if not addr.is_global or addr.is_multicast or addr.is_reserved:
        return False
    return not any(addr in net for net in BLOCKED_NETWORKS)


def resolve_ips(host: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return []
    seen: list[str] = []
    for info in infos:
        ip = info[4][0]
        if ip not in seen:
            seen.append(ip)
    return seen


def assert_public_host(host: str) -> list[str]:
    """Resolve `host` and refuse it unless every address is public."""
    ips = resolve_ips(host)
    if not ips:
        raise ScanError("no_dns", f"{host} does not resolve to any address. Check the spelling.")
    bad = [ip for ip in ips if not is_public_ip(ip)]
    if bad:
        raise ScanError("private", f"{host} points to a private or reserved address and cannot be scanned.")
    return ips
