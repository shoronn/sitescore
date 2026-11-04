"""Production safety: start-up checks, response headers, request limits, CSV export, enrolment limits."""
from __future__ import annotations

import pytest

from test_api import client, sign_in  # noqa: F401
from test_admin import add_staff

from sitescore.admin import csv_safe
from sitescore.config import ConfigError, Settings, check_settings

GOOD = dict(
    env="production",
    secret_key="x" * 64,
    database_url="postgresql+asyncpg://u:p@db-host:5432/sitescore",
    redis_url="redis://default:p@redis-host:6379/0",
    queue_mode="rq",
    smtp_host="mail.maktechgroup.com", smtp_user="sitescore@maktechgroup.com", smtp_password="secret",
    public_base_url="https://sitescore.maktechgroup.com",
    cors_origins="https://sitescore.maktechgroup.com",
    cookie_secure=True,
)


def test_good_production_settings_pass():
    assert Settings(**GOOD).production_problems() == []
    check_settings(Settings(**GOOD))


@pytest.mark.parametrize("change,needle", [
    ({"secret_key": "change-me-in-production-please-use-64-random-chars"}, "SECRET_KEY"),
    ({"database_url": "mysql://u:p@db:5432/x"}, "DATABASE_URL"),
    ({"smtp_host": None}, "SMTP"),
    ({"redis_url": None}, "REDIS_URL"),
    ({"public_base_url": "http://sitescore.maktechgroup.com"}, "PUBLIC_BASE_URL"),
    ({"cors_origins": ""}, "CORS_ORIGINS"),
    ({"cookie_secure": False}, "COOKIE_SECURE"),
])
def test_bad_production_settings_refuse_to_start(change, needle):
    with pytest.raises(ConfigError) as exc:
        check_settings(Settings(**{**GOOD, **change}))
    assert needle in str(exc.value)


@pytest.mark.parametrize("given", [
    "postgres://postgres:pw@abc123:5432/postgres",           # what Coolify shows
    "postgresql://postgres:pw@abc123:5432/postgres",
    "postgresql+psycopg2://postgres:pw@abc123:5432/postgres",
    " 'postgresql+asyncpg://postgres:pw@abc123:5432/postgres' ",
])
def test_any_postgres_url_is_switched_to_asyncpg(given):
    s = Settings(**{**GOOD, "database_url": given})
    assert s.database_url == "postgresql+asyncpg://postgres:pw@abc123:5432/postgres"
    assert s.production_problems() == []


def test_development_is_not_checked():
    check_settings(Settings(env="development"))


def test_csv_safe():
    assert csv_safe("=HYPERLINK(\"http://x\")") == "'=HYPERLINK(\"http://x\")"
    assert csv_safe("+880171") == "'+880171"
    assert csv_safe("Karim Shop") == "Karim Shop" and csv_safe(None) == "" and csv_safe(65) == "65"


async def test_security_headers_and_no_store(client):
    r = await client.get("/api/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["cache-control"] == "no-store"


async def test_large_bodies_are_refused(client):
    r = await client.post("/api/auth/start", content=b"{" + b" " * 70_000 + b"}",
                          headers={"content-type": "application/json"})
    assert r.status_code == 413


async def test_enroll_attempts_are_limited(client):
    await add_staff()
    data = (await client.post("/api/admin/login", json={"email": "sales@maktech.test",
                                                        "password": "a-long-password-123"})).json()
    codes = []
    for _ in range(6):
        r = await client.post("/api/admin/enroll", json={"enroll_token": data["enroll_token"], "code": "000000"})
        codes.append(r.status_code)
    assert codes[-1] == 429 and 429 not in codes[:5]
