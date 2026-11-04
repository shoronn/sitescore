"""Sessions, input validation (email, phone, text) and Turnstile."""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from pathlib import Path

import httpx
from email_validator import EmailNotValidError, validate_email
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .config import Settings

_DISPOSABLE = {
    line.strip().lower()
    for line in (Path(__file__).parent / "data" / "disposable_domains.txt").read_text().splitlines()
    if line.strip() and not line.startswith("#")
}


class InputError(Exception):
    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field = field
        self.message = message


def aware(dt: datetime | None) -> datetime | None:
    """SQLite drops time zones; treat stored naive datetimes as UTC."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


# ---------------------------------------------------------------- input

async def normalize_email(raw: str, check_deliverability: bool) -> str:
    try:
        info = await asyncio.to_thread(validate_email, (raw or "").strip(), check_deliverability=check_deliverability)
    except EmailNotValidError as exc:
        raise InputError("email", "Please enter a valid email address you can receive mail at.") from exc
    email = info.normalized.lower()
    domain = email.rsplit("@", 1)[-1]
    if domain in _DISPOSABLE or any(domain.endswith("." + d) for d in _DISPOSABLE):
        raise InputError("email", "Please use your regular email address, not a temporary one.")
    return email


_PHONE_OK = re.compile(r"^\+?[0-9]{7,15}$")


def normalize_phone(raw: str | None) -> str | None:
    if not raw or not raw.strip():
        return None
    cleaned = re.sub(r"[\s\-().]", "", raw.strip())
    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]
    if not _PHONE_OK.match(cleaned):
        raise InputError("phone", "Please enter a valid phone number, or leave it empty.")
    return cleaned


def clean_text(raw: str | None, limit: int) -> str | None:
    if raw is None:
        return None
    text = " ".join(raw.split())[:limit]
    return text or None


# ---------------------------------------------------------------- sessions

def _serializer(settings: Settings) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.secret_key, salt="sitescore-session")


def make_session(settings: Settings, lead_id: int) -> str:
    return _serializer(settings).dumps({"lead": lead_id})


def read_session(settings: Settings, token: str | None) -> int | None:
    if not token:
        return None
    try:
        data = _serializer(settings).loads(token, max_age=settings.session_days * 86400)
    except (BadSignature, SignatureExpired):
        return None
    lead = data.get("lead") if isinstance(data, dict) else None
    return lead if isinstance(lead, int) else None


# ---------------------------------------------------------------- Turnstile

async def verify_turnstile(settings: Settings, token: str | None, ip: str | None) -> bool:
    if not settings.turnstile_secret:
        return True  # switched off (development)
    if not token:
        return False
    data = {"secret": settings.turnstile_secret, "response": token}
    if ip:
        data["remoteip"] = ip
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post("https://challenges.cloudflare.com/turnstile/v0/siteverify", data=data)
        return bool(r.json().get("success"))
    except (httpx.HTTPError, ValueError):
        return False
