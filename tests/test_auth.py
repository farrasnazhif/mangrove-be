from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import jwt
import pytest
from fastapi import HTTPException

from app.core.config import Settings, settings
from app.core.security import (
    create_session_token,
    decode_session_token,
    generate_csrf_token,
    hash_password,
    verify_csrf_token,
    verify_password,
)
from app.models.user import UserRole
from tests.conftest import authenticate


def login(client, **changes):
    csrf = client.get("/api/v1/auth/csrf").json()["csrf_token"]
    payload = {"email": "manager@example.test", "password": "test-password-123", **changes}
    return client.post("/api/v1/auth/login", json=payload, headers={"X-CSRF-Token": csrf})


def test_login_success(client):
    response = login(client)
    assert response.status_code == 200
    assert response.json()["user"]["role"] == "manager"
    assert "hashed_password" not in response.text
    cookies = response.headers.get_list("set-cookie")
    assert any("HttpOnly" in cookie and "SameSite=lax" in cookie for cookie in cookies)
    assert response.headers["cache-control"] == "no-store"
    assert client.get("/api/v1/me").status_code == 200


def test_login_secure_cookie(client, monkeypatch):
    client.base_url = "https://testserver"
    monkeypatch.setattr(settings, "session_cookie_secure", True)
    response = login(client)
    assert response.status_code == 200
    assert all("Secure" in cookie for cookie in response.headers.get_list("set-cookie"))


@pytest.mark.parametrize(
    "case,expected",
    [
        ("wrong-password", 401),
        ("missing", 401),
        ("inactive", 403),
        ("visitor", 403),
    ],
)
def test_rejected_login(client, manager, db_mock, case, expected):
    if case == "missing":
        db_mock.execute.return_value.scalar_one_or_none.return_value = None
    elif case == "inactive":
        manager.is_active = False
    elif case == "visitor":
        manager.role = UserRole.visitor
    response = login(client, password="wrong" if case == "wrong-password" else "test-password-123")
    assert response.status_code == expected


def test_login_requires_csrf(client):
    response = client.post("/api/v1/auth/login", json={"email": "a@b", "password": "secret"})
    assert response.status_code == 403


def test_login_rejects_role_in_body(client):
    assert login(client, role="manager").status_code == 422


@pytest.mark.parametrize("path", ["/api/v1/me", "/api/v1/auth/me"])
def test_get_me_uses_database_role(client, manager, path):
    authenticate(client, manager, role="visitor")
    response = client.get(path)
    assert response.status_code == 200
    assert response.json()["role"] == "manager"


def test_demoted_manager_denied_despite_signed_manager_claim(client, manager):
    authenticate(client, manager)
    manager.role = UserRole.visitor
    assert client.get("/api/v1/me").status_code == 403


def test_inactive_manager_denied(client, manager):
    authenticate(client, manager)
    manager.is_active = False
    assert client.get("/api/v1/me").status_code == 401


def test_logout_revokes_and_clears_cookies(client, manager, db_mock):
    response = login(client)
    assert response.status_code == 200
    headers = {"X-CSRF-Token": response.json()["csrf_token"]}
    old_token = client.cookies.get(settings.session_cookie_name)
    response = client.post("/api/v1/auth/logout", headers=headers)
    assert response.status_code == 200
    assert settings.session_cookie_name not in client.cookies
    assert settings.csrf_cookie_name not in client.cookies
    db_mock.commit.assert_awaited_once()
    # DB integration test separately proves that the UPDATE persists.
    manager.session_version = 1
    client.cookies.set(settings.session_cookie_name, old_token)
    assert client.get("/api/v1/me").status_code == 401


@pytest.mark.parametrize("case", ["missing", "wrong", "forged", "other-session", "expired"])
def test_real_logout_csrf(client, manager, db_mock, case):
    headers = authenticate(client, manager)
    if case == "missing":
        headers = {}
    elif case == "wrong":
        headers = {"X-CSRF-Token": "wrong"}
    else:
        if case == "forged":
            csrf = "attacker-controlled-cookie-and-header"
        elif case == "other-session":
            csrf = generate_csrf_token(create_session_token(manager.id, "manager"))
        else:
            with patch("app.core.security.time.time", return_value=1):
                csrf = generate_csrf_token(client.cookies.get(settings.session_cookie_name))
        client.cookies.set(settings.csrf_cookie_name, csrf)
        headers = {"X-CSRF-Token": csrf}
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 403
    db_mock.commit.assert_not_awaited()


def test_expired_session_cannot_read_or_write(client, manager, db_mock):
    payload = jwt.decode(
        create_session_token(manager.id, "manager"),
        settings.jwt_secret,
        algorithms=["HS256"],
    )
    payload["exp"] = datetime.now(UTC) - timedelta(seconds=5)
    expired = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    client.cookies.set(settings.session_cookie_name, expired)
    assert client.get("/api/v1/me").status_code == 401
    assert client.post("/api/v1/auth/logout").status_code == 401
    db_mock.commit.assert_not_awaited()


def test_refresh_csrf_allows_logout(client, manager):
    authenticate(client, manager)
    csrf = client.get("/api/v1/auth/csrf").json()["csrf_token"]
    assert client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 200


def test_password_hashing_and_malformed_inputs(password_hash):
    assert verify_password("test-password-123", password_hash)
    assert not verify_password("wrong", password_hash)
    assert not verify_password("a" * 73, password_hash)
    assert not verify_password("secret", "corrupted-hash")
    with pytest.raises(ValueError):
        hash_password("a" * 73)


def test_missing_exp_claim_is_rejected():
    token = jwt.encode({"sub": "a", "role": "manager"}, settings.jwt_secret, algorithm="HS256")
    with pytest.raises(HTTPException) as error:
        decode_session_token(token)
    assert error.value.status_code == 401


def test_csrf_is_bound_to_session():
    csrf = generate_csrf_token("session-a")
    assert verify_csrf_token(csrf, csrf, "session-a")
    assert not verify_csrf_token(csrf, csrf, "session-b")


@pytest.mark.parametrize(
    "changes",
    [
        {"boundary_lon_min": 10, "boundary_lon_max": 9},
        {"boundary_lat_min": 91},
        {"boundary_approved": True},
        {"session_cookie_samesite": "none", "session_cookie_secure": False},
        {"environment": "production", "session_cookie_secure": False},
        {"environment": "production", "session_cookie_secure": True, "jwt_secret": "change-me"},
    ],
)
def test_invalid_config_fails_closed(changes):
    config = {"database_url": "postgresql+asyncpg://test/test", "jwt_secret": "test", **changes}
    with pytest.raises(ValueError):
        Settings(_env_file=None, **config)
