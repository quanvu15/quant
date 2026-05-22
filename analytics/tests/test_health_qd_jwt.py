"""
Phase 1 — Test Gate: QD JWT → /api/v1/health → 200

Verifies that a QuantDinger JWT (signed with QD SECRET_KEY) can access
the authenticated health endpoint at /api/v1/health and receive HTTP 200.

This is the Test Gate verification for:
  `curl -H "Authorization: Bearer <QD_JWT>" http://localhost:8081/api/v1/health` → 200

Validates: Requirements 1.1, 1.2, 10.4
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from jose import jwt

from app.config import settings
from app.main import app


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
    """Mint a JWT matching QuantDinger's actual payload format."""
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


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def qd_health_client(monkeypatch, mock_cache):
    """
    TestClient with QUANTDINGER_JWT_SECRET configured to match QD's SECRET_KEY.
    Uses the real app (not a minimal test app) to test /api/v1/health.
    """
    monkeypatch.setattr(settings, "QUANTDINGER_JWT_SECRET", QD_SECRET_KEY)
    monkeypatch.setattr(settings, "QUANTDINGER_JWT_ALGORITHM", QD_ALGORITHM)
    with TestClient(app) as c:
        yield c


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestQdJwtHealthEndpoint:
    """Test Gate: QD JWT can access /api/v1/health → 200"""

    def test_qd_jwt_health_returns_200(self, qd_health_client):
        """
        A valid QD JWT should get HTTP 200 from /api/v1/health.
        This is the primary Test Gate assertion.
        """
        token = _make_qd_jwt()
        resp = qd_health_client.get(
            "/api/v1/health",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

    def test_qd_jwt_health_response_shape(self, qd_health_client):
        """Response should include status, version, and uptime_seconds (Req 10.4)."""
        token = _make_qd_jwt()
        resp = qd_health_client.get(
            "/api/v1/health",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data
        assert "uptime_seconds" in data

    def test_qd_jwt_health_no_auth_returns_401(self, qd_health_client):
        """/api/v1/health without auth should return 401."""
        resp = qd_health_client.get("/api/v1/health")
        assert resp.status_code == 401

    def test_qd_jwt_health_expired_token_returns_401(self, qd_health_client):
        """An expired QD JWT should get 401 from /api/v1/health."""
        token = _make_qd_jwt(expire_delta=timedelta(hours=-1))
        resp = qd_health_client.get(
            "/api/v1/health",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401

    def test_qd_jwt_health_wrong_signature_returns_401(self, qd_health_client):
        """A QD JWT with wrong signature should get 401 from /api/v1/health."""
        token = _make_qd_jwt(secret="wrong-secret-key")
        resp = qd_health_client.get(
            "/api/v1/health",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401

    def test_public_health_still_works(self, qd_health_client):
        """The public /health endpoint should still work without auth."""
        resp = qd_health_client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
