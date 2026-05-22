"""
Phase 1 — Task 1.6: JWT Bridge end-to-end tests.

Tests the full flow of QuantDinger JWT tokens being accepted/rejected by
Analytics' auth system via FastAPI TestClient hitting a protected endpoint.

Scenarios:
  1. Valid QD JWT (created with QD SECRET_KEY, not expired) → 200
  2. Expired QD JWT (exp in the past) → 401
  3. QD JWT with wrong signature (signed with different key) → 401
  4. QUANTDINGER_JWT_SECRET is empty → JWT bridge disabled → 401

Validates: Requirements 1.1–1.7
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
from core.auth import CurrentUser, get_current_user


# ── Constants matching QuantDinger's actual SECRET_KEY ─────────────────────────

QD_SECRET_KEY = "0cf13f1ff25b73a6c682a5d82818a99b4b428206d6c5176bbf69fb4968de374f"
QD_ALGORITHM = "HS256"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_qd_jwt(
    sub: str = "quantdinger",
    user_id: int = 1,
    role: str = "admin",
    token_version: int = 1,
    secret: str = QD_SECRET_KEY,
    algorithm: str = QD_ALGORITHM,
    expire_delta: timedelta | None = None,
) -> str:
    """
    Mint a JWT matching QuantDinger's actual payload format.

    QD JWT payload: {sub: "quantdinger", user_id: 1, role: "admin", token_version: 1, exp: <epoch>}
    """
    if expire_delta is None:
        expire_delta = timedelta(hours=1)

    payload = {
        "sub": sub,
        "user_id": user_id,
        "role": role,
        "token_version": token_version,
        "exp": datetime.now(timezone.utc) + expire_delta,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, secret, algorithm=algorithm)


# ── Minimal FastAPI app with a protected endpoint ─────────────────────────────

_app = FastAPI()


@_app.get("/protected")
async def _protected_endpoint(user: CurrentUser):
    """A protected endpoint that requires authentication."""
    return {
        "sub": user["sub"],
        "role": user["role"],
        "source": user["source"],
    }


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def qd_client(monkeypatch, mock_cache):
    """
    TestClient with QUANTDINGER_JWT_SECRET configured to match QD's SECRET_KEY.
    This enables the JWT bridge.
    """
    monkeypatch.setattr(settings, "QUANTDINGER_JWT_SECRET", QD_SECRET_KEY)
    monkeypatch.setattr(settings, "QUANTDINGER_JWT_ALGORITHM", QD_ALGORITHM)
    with TestClient(_app) as c:
        yield c


@pytest.fixture
def qd_client_bridge_disabled(monkeypatch, mock_cache):
    """
    TestClient with QUANTDINGER_JWT_SECRET empty — JWT bridge is disabled.
    """
    monkeypatch.setattr(settings, "QUANTDINGER_JWT_SECRET", "")
    with TestClient(_app) as c:
        yield c


# ── Test 1: Valid QD JWT → 200 ────────────────────────────────────────────────

class TestValidQdJwt:
    """Validates: Req 1.1, 1.2, 1.5"""

    def test_valid_qd_jwt_returns_200(self, qd_client):
        """A valid QD JWT signed with the correct SECRET_KEY should be accepted."""
        token = _make_qd_jwt()
        resp = qd_client.get(
            "/protected",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

    def test_valid_qd_jwt_returns_correct_user(self, qd_client):
        """The normalised user should have source='quantdinger' and sub=str(user_id)."""
        token = _make_qd_jwt(user_id=42, role="admin")
        resp = qd_client.get(
            "/protected",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        # user_id (int) is converted to str for internal use (Req 1.5)
        assert data["sub"] == "42"
        assert data["role"] == "admin"
        assert data["source"] == "quantdinger"

    def test_valid_qd_jwt_different_users(self, qd_client):
        """Different user_ids produce different sub values."""
        for uid in [1, 2, 100]:
            token = _make_qd_jwt(user_id=uid)
            resp = qd_client.get(
                "/protected",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200
            assert resp.json()["sub"] == str(uid)


# ── Test 2: Expired QD JWT → 401 ─────────────────────────────────────────────

class TestExpiredQdJwt:
    """Validates: Req 1.3, 1.7"""

    def test_expired_qd_jwt_returns_401(self, qd_client):
        """A QD JWT with exp in the past should be rejected with 401."""
        token = _make_qd_jwt(expire_delta=timedelta(hours=-1))
        resp = qd_client.get(
            "/protected",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401

    def test_expired_qd_jwt_error_code(self, qd_client):
        """The 401 response should include AUTH_REQUIRED code."""
        token = _make_qd_jwt(expire_delta=timedelta(seconds=-1))
        resp = qd_client.get(
            "/protected",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401
        detail = resp.json()["detail"]
        assert detail["code"] == "AUTH_REQUIRED"

    def test_just_expired_qd_jwt_rejected(self, qd_client):
        """A token that expired 1 second ago should still be rejected."""
        token = _make_qd_jwt(expire_delta=timedelta(seconds=-1))
        resp = qd_client.get(
            "/protected",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401


# ── Test 3: QD JWT with wrong signature → 401 ────────────────────────────────

class TestWrongSignatureQdJwt:
    """Validates: Req 1.3"""

    def test_wrong_signature_returns_401(self, qd_client):
        """A JWT signed with a different key should be rejected."""
        wrong_secret = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        token = _make_qd_jwt(secret=wrong_secret)
        resp = qd_client.get(
            "/protected",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401

    def test_wrong_signature_error_code(self, qd_client):
        """The 401 response should include AUTH_REQUIRED code."""
        token = _make_qd_jwt(secret="totally-wrong-key")
        resp = qd_client.get(
            "/protected",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401
        detail = resp.json()["detail"]
        assert detail["code"] == "AUTH_REQUIRED"

    def test_tampered_payload_rejected(self, qd_client):
        """A token with a tampered payload (different signature) is rejected."""
        # Create a valid token, then re-sign with wrong key
        token = _make_qd_jwt(secret="attacker-key-12345")
        resp = qd_client.get(
            "/protected",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401


# ── Test 4: QUANTDINGER_JWT_SECRET empty → bridge disabled → 401 ──────────────

class TestBridgeDisabled:
    """Validates: Req 1.4"""

    def test_bridge_disabled_rejects_qd_jwt(self, qd_client_bridge_disabled):
        """When QUANTDINGER_JWT_SECRET is empty, QD JWTs are not accepted."""
        token = _make_qd_jwt()  # Valid QD token, but bridge is off
        resp = qd_client_bridge_disabled.get(
            "/protected",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401

    def test_bridge_disabled_error_code(self, qd_client_bridge_disabled):
        """The rejection should return AUTH_REQUIRED."""
        token = _make_qd_jwt()
        resp = qd_client_bridge_disabled.get(
            "/protected",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401
        detail = resp.json()["detail"]
        assert detail["code"] == "AUTH_REQUIRED"

    def test_bridge_disabled_does_not_crash(self, qd_client_bridge_disabled):
        """The app should not crash when bridge is disabled — just reject gracefully."""
        token = _make_qd_jwt()
        # Should not raise any exception
        resp = qd_client_bridge_disabled.get(
            "/protected",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code in (401, 403)
