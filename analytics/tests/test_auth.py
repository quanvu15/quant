"""
Phase 0 — Test Gate: authentication middleware.

Covers:
  - API key generation / verification
  - Analytics-native JWT (create / verify)
  - QuantDinger JWT bridge (verify_quantdinger_jwt)
  - get_current_user FastAPI dependency (all resolution paths)
  - require_role helper
  - Master API key bypass
  - 401 on missing / invalid credentials
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from jose import jwt

from app.config import settings
from core.auth import (
    TIER_ADMIN,
    TIER_FREE,
    TIER_PAID,
    CurrentUser,
    create_analytics_jwt,
    create_jwt_token,
    generate_api_key,
    get_current_user,
    require_role,
    verify_analytics_jwt,
    verify_api_key,
    verify_jwt_token,
    verify_quantdinger_jwt,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_qd_token(
    sub: str = "user-uuid-123",
    role: str = "user",
    email: str = "test@example.com",
    secret: str = "qd-secret",
    algorithm: str = "HS256",
    expire_delta: timedelta = timedelta(hours=1),
) -> str:
    """Mint a fake QuantDinger JWT for testing."""
    payload = {
        "sub": sub,
        "role": role,
        "email": email,
        "exp": datetime.now(timezone.utc) + expire_delta,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, secret, algorithm=algorithm)


# ── Minimal FastAPI app for dependency tests ──────────────────────────────────

_test_app = FastAPI()


@_test_app.get("/protected")
async def _protected(user: CurrentUser):
    return {"sub": user["sub"], "role": user["role"], "source": user["source"]}


@_test_app.get("/admin-only")
async def _admin_only(user: Annotated[dict, Depends(require_role("admin"))]):
    return {"sub": user["sub"]}


# ── API Key tests ─────────────────────────────────────────────────────────────

def test_generate_api_key_format():
    key = generate_api_key("free")
    assert key.startswith("fincept_free_")
    assert len(key) > 20


def test_generate_api_key_paid():
    key = generate_api_key("paid")
    assert key.startswith("fincept_paid_")


@pytest.mark.asyncio
async def test_verify_master_api_key(mock_cache):
    result = await verify_api_key(settings.MASTER_API_KEY)
    assert result == TIER_ADMIN


@pytest.mark.asyncio
async def test_verify_invalid_api_key(mock_cache):
    result = await verify_api_key("invalid_key")
    assert result is None


@pytest.mark.asyncio
async def test_verify_empty_api_key(mock_cache):
    result = await verify_api_key("")
    assert result is None


# ── Analytics-native JWT tests ────────────────────────────────────────────────

def test_create_and_verify_analytics_jwt():
    token = create_analytics_jwt("user-abc", role="user", email="a@b.com")
    payload = verify_analytics_jwt(token)
    assert payload is not None
    assert payload["sub"] == "user-abc"
    assert payload["role"] == "user"
    assert payload["email"] == "a@b.com"
    assert payload["source"] == "analytics"


def test_create_analytics_jwt_admin_role():
    token = create_analytics_jwt("admin-user", role="admin")
    payload = verify_analytics_jwt(token)
    assert payload["role"] == "admin"


def test_verify_analytics_jwt_invalid():
    result = verify_analytics_jwt("not.a.valid.token")
    assert result is None


def test_verify_analytics_jwt_expired():
    token = create_analytics_jwt("user-abc", expire_minutes=-1)
    result = verify_analytics_jwt(token)
    assert result is None


def test_analytics_jwt_extra_claims():
    token = create_analytics_jwt("user-abc", extra_claims={"tier": "paid", "org": "acme"})
    payload = verify_analytics_jwt(token)
    assert payload["tier"] == "paid"
    assert payload["org"] == "acme"


# Backward-compat aliases
def test_create_jwt_token_compat():
    token = create_jwt_token("user123")
    payload = verify_jwt_token(token)
    assert payload is not None
    assert payload["sub"] == "user123"


def test_verify_jwt_token_compat_invalid():
    assert verify_jwt_token("bad.token") is None


# ── QuantDinger JWT bridge tests ──────────────────────────────────────────────

def test_verify_quantdinger_jwt_disabled_when_no_secret(monkeypatch):
    """Bridge returns None when QUANTDINGER_JWT_SECRET is empty."""
    monkeypatch.setattr(settings, "QUANTDINGER_JWT_SECRET", "")
    token = _make_qd_token()
    result = verify_quantdinger_jwt(token)
    assert result is None


def test_verify_quantdinger_jwt_valid(monkeypatch):
    """Valid QuantDinger token is accepted when bridge is configured."""
    secret = "qd-shared-secret"
    monkeypatch.setattr(settings, "QUANTDINGER_JWT_SECRET", secret)
    monkeypatch.setattr(settings, "QUANTDINGER_JWT_ALGORITHM", "HS256")
    token = _make_qd_token(secret=secret)
    result = verify_quantdinger_jwt(token)
    assert result is not None
    assert result["sub"] == "user-uuid-123"
    assert result["role"] == "user"


def test_verify_quantdinger_jwt_wrong_secret(monkeypatch):
    """Token signed with wrong secret is rejected."""
    monkeypatch.setattr(settings, "QUANTDINGER_JWT_SECRET", "correct-secret")
    monkeypatch.setattr(settings, "QUANTDINGER_JWT_ALGORITHM", "HS256")
    token = _make_qd_token(secret="wrong-secret")
    result = verify_quantdinger_jwt(token)
    assert result is None


def test_verify_quantdinger_jwt_expired(monkeypatch):
    """Expired QuantDinger token is rejected."""
    secret = "qd-secret"
    monkeypatch.setattr(settings, "QUANTDINGER_JWT_SECRET", secret)
    monkeypatch.setattr(settings, "QUANTDINGER_JWT_ALGORITHM", "HS256")
    token = _make_qd_token(secret=secret, expire_delta=timedelta(hours=-1))
    result = verify_quantdinger_jwt(token)
    assert result is None


# ── get_current_user dependency tests ────────────────────────────────────────

@pytest.fixture
def dep_client(mock_cache):
    """Test client for the minimal dependency-test app."""
    with TestClient(_test_app) as c:
        yield c


def test_get_current_user_no_credentials(dep_client):
    """No credentials → 401."""
    resp = dep_client.get("/protected")
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "AUTH_REQUIRED"


def test_get_current_user_master_key(dep_client, monkeypatch):
    """Master API key → admin user bypass."""
    monkeypatch.setattr(settings, "MASTER_API_KEY", "fincept_admin_test_key")
    resp = dep_client.get("/protected", headers={"X-API-Key": "fincept_admin_test_key"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["sub"] == "master"
    assert data["role"] == "admin"
    assert data["source"] == "master_key"


def test_get_current_user_analytics_jwt(dep_client):
    """Valid Analytics-native JWT → authenticated user."""
    token = create_analytics_jwt("user-xyz", role="user")
    resp = dep_client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["sub"] == "user-xyz"
    assert data["source"] == "analytics"


def test_get_current_user_quantdinger_jwt(dep_client, monkeypatch):
    """Valid QuantDinger JWT → authenticated user via bridge."""
    secret = "qd-bridge-secret"
    monkeypatch.setattr(settings, "QUANTDINGER_JWT_SECRET", secret)
    monkeypatch.setattr(settings, "QUANTDINGER_JWT_ALGORITHM", "HS256")
    token = _make_qd_token(sub="qd-user-456", secret=secret)
    resp = dep_client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["sub"] == "qd-user-456"
    assert data["source"] == "quantdinger"


def test_get_current_user_invalid_bearer(dep_client):
    """Invalid Bearer token → 401."""
    resp = dep_client.get("/protected", headers={"Authorization": "Bearer not.a.token"})
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "AUTH_REQUIRED"


def test_get_current_user_expired_analytics_jwt(dep_client):
    """Expired Analytics JWT → 401."""
    token = create_analytics_jwt("user-xyz", expire_minutes=-1)
    resp = dep_client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_get_current_user_api_key_free_tier(dep_client, monkeypatch):
    """Well-formed free-tier API key → authenticated as free tier."""
    monkeypatch.setattr(settings, "MASTER_API_KEY", "")  # disable master key
    key = generate_api_key(TIER_FREE)
    resp = dep_client.get("/protected", headers={"X-API-Key": key})
    assert resp.status_code == 200
    data = resp.json()
    assert data["role"] == TIER_FREE
    assert data["source"] == "api_key"


# ── require_role tests ────────────────────────────────────────────────────────

def test_require_role_admin_allowed(dep_client, monkeypatch):
    """Admin user can access admin-only endpoint."""
    monkeypatch.setattr(settings, "MASTER_API_KEY", "fincept_admin_test_key")
    resp = dep_client.get("/admin-only", headers={"X-API-Key": "fincept_admin_test_key"})
    assert resp.status_code == 200


def test_require_role_user_forbidden(dep_client):
    """Non-admin user gets 403 on admin-only endpoint."""
    token = create_analytics_jwt("regular-user", role="user")
    resp = dep_client.get("/admin-only", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "FORBIDDEN"


# ── Health endpoint still public ──────────────────────────────────────────────

def test_health_is_public(client):
    """Health endpoint requires no auth."""
    response = client.get("/health")
    assert response.status_code == 200


def test_rate_limit_middleware_no_crash(client):
    """Middleware should not crash on health endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
