from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import jwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_optional_session, verify_csrf
from app.core.config import settings
from app.core.security import create_session_token, hash_password
from app.db.session import get_session
from app.main import app
from app.models.user import User, UserRole


# Fixture for a test manager
@pytest.fixture
def mock_manager() -> User:
    return User(
        id="usr-123",
        email="manager@surabaya.go.id",
        hashed_password=hash_password("password123"),
        role=UserRole.manager,
        is_active=True,
    )


# Fixture for a test visitor
@pytest.fixture
def mock_visitor() -> User:
    return User(
        id="usr-456",
        email="visitor@public.com",
        hashed_password=hash_password("visitor123"),
        role=UserRole.visitor,
        is_active=True,
    )


def test_login_success(mock_manager):
    """Test successful manager login returning HttpOnly session cookie and CSRF token."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_manager
    mock_session.execute.return_value = mock_result

    async def override_session():
        yield mock_session

    app.dependency_overrides[get_session] = override_session
    client = TestClient(app)

    try:
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": "manager@surabaya.go.id", "password": "password123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["user"]["email"] == "manager@surabaya.go.id"
        assert data["user"]["role"] == "manager"  # server-derived role
        assert "csrf_token" in data

        # Check cookies
        cookies = resp.cookies
        assert settings.session_cookie_name in cookies
        assert settings.csrf_cookie_name in cookies
    finally:
        app.dependency_overrides.clear()


def test_login_wrong_password(mock_manager):
    """Test login failure on incorrect password."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_manager
    mock_session.execute.return_value = mock_result

    async def override_session():
        yield mock_session

    app.dependency_overrides[get_session] = override_session
    client = TestClient(app)

    try:
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": "manager@surabaya.go.id", "password": "wrongpassword"},
        )
        assert resp.status_code == 401
        assert "Invalid email or password" in resp.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_login_nonexistent_user():
    """Test login failure when user does not exist."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result

    async def override_session():
        yield mock_session

    app.dependency_overrides[get_session] = override_session
    client = TestClient(app)

    try:
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": "unknown@domain.com", "password": "password123"},
        )
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_login_inactive_user(mock_manager):
    """Test login rejected for inactive account."""
    mock_manager.is_active = False
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_manager
    mock_session.execute.return_value = mock_result

    async def override_session():
        yield mock_session

    app.dependency_overrides[get_session] = override_session
    client = TestClient(app)

    try:
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": "manager@surabaya.go.id", "password": "password123"},
        )
        assert resp.status_code == 403
        assert "inactive" in resp.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


def test_get_me_authenticated(mock_manager):
    """Test /api/v1/me and /api/v1/auth/me return the server-derived role for authenticated manager."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_manager
    mock_session.execute.return_value = mock_result

    async def override_session(request=None):
        yield mock_session

    app.dependency_overrides[get_optional_session] = override_session
    client = TestClient(app)

    try:
        token = create_session_token("usr-123", "manager")
        client.cookies.set(settings.session_cookie_name, token)

        # Test /api/v1/me
        resp_me = client.get("/api/v1/me")
        assert resp_me.status_code == 200
        assert resp_me.json()["role"] == "manager"
        assert resp_me.json()["email"] == "manager@surabaya.go.id"

        # Test /api/v1/auth/me
        resp_auth_me = client.get("/api/v1/auth/me")
        assert resp_auth_me.status_code == 200
        assert resp_auth_me.json()["role"] == "manager"
    finally:
        app.dependency_overrides.clear()


def test_get_me_unauthenticated():
    """Test anonymous visitor receives 401 when accessing manager /me endpoint."""
    client = TestClient(app)
    resp = client.get("/api/v1/me")
    assert resp.status_code == 401
    assert "Authentication required" in resp.json()["detail"]


def test_get_me_visitor_role_forbidden(mock_visitor):
    """Test that a non-manager authenticated user receives 403 on manager-only route."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_visitor
    mock_session.execute.return_value = mock_result

    async def override_session(request=None):
        yield mock_session

    app.dependency_overrides[get_optional_session] = override_session
    client = TestClient(app)

    try:
        token = create_session_token("usr-456", "visitor")
        client.cookies.set(settings.session_cookie_name, token)

        resp = client.get("/api/v1/me")
        assert resp.status_code == 403
        assert "Manager access required" in resp.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_expired_session_cannot_read_or_write(mock_manager):
    """Test that an expired session token is rejected with 401."""
    client = TestClient(app)

    # Generate an expired token
    expired_payload = {
        "sub": "usr-123",
        "role": "manager",
        "exp": datetime.now(UTC) - timedelta(hours=1),
        "iat": datetime.now(UTC) - timedelta(hours=2),
    }
    expired_token = jwt.encode(expired_payload, settings.jwt_secret, algorithm="HS256")
    client.cookies.set(settings.session_cookie_name, expired_token)

    resp = client.get("/api/v1/me")
    assert resp.status_code == 401
    assert "expired" in resp.json()["detail"].lower()


def test_logout():
    """Test logout clears session and CSRF cookies."""
    client = TestClient(app)
    client.cookies.set(settings.session_cookie_name, "dummy-token")
    client.cookies.set(settings.csrf_cookie_name, "dummy-csrf")

    resp = client.post("/api/v1/auth/logout")
    assert resp.status_code == 200
    assert resp.json()["message"] == "Logged out successfully"


def test_csrf_token_endpoint():
    """Test GET /api/v1/auth/csrf returns valid CSRF token."""
    client = TestClient(app)
    resp = client.get("/api/v1/auth/csrf")
    assert resp.status_code == 200
    csrf_token = resp.json()["csrf_token"]
    assert len(csrf_token) == 64  # secrets.token_hex(32) produces 64 hex characters


def test_csrf_protection_dependency():
    """Test CSRF protection on state-changing calls."""
    test_app = FastAPI()

    @test_app.post("/test-mutation", dependencies=[Depends(verify_csrf)])
    def mutation_route():
        return {"status": "mutated"}

    client = TestClient(test_app)

    # Case 1: No session cookie -> passes (e.g. public mutation if any)
    resp = client.post("/test-mutation")
    assert resp.status_code == 200

    # Case 2: Session cookie present, but missing CSRF header -> 403 Forbidden
    client.cookies.set(settings.session_cookie_name, "session-token")
    client.cookies.set(settings.csrf_cookie_name, "csrf-token-abc")
    resp_no_header = client.post("/test-mutation")
    assert resp_no_header.status_code == 403
    assert "CSRF" in resp_no_header.json()["detail"]

    # Case 3: Session cookie present, CSRF header invalid -> 403 Forbidden
    resp_invalid_header = client.post(
        "/test-mutation",
        headers={"x-csrf-token": "wrong-token"},
    )
    assert resp_invalid_header.status_code == 403

    # Case 4: Session cookie present, CSRF header matches cookie -> 200 OK
    resp_valid = client.post(
        "/test-mutation",
        headers={"x-csrf-token": "csrf-token-abc"},
    )
    assert resp_valid.status_code == 200
    assert resp_valid.json() == {"status": "mutated"}
