import os
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "postgresql+asyncpg://test:test@localhost/mangrove_test"
os.environ["JWT_SECRET"] = "task03-test-secret-which-is-not-used-in-production"
os.environ["ENVIRONMENT"] = "test"
os.environ["SESSION_COOKIE_SECURE"] = "false"

from app.api.deps import get_optional_session
from app.core.config import settings
from app.core.security import create_session_token, generate_csrf_token, hash_password
from app.db.session import get_session
from app.main import app
from app.models.user import User, UserRole


@pytest.fixture(scope="session")
def password_hash():
    return hash_password("test-password-123")


@pytest.fixture
def manager(password_hash):
    return User(
        id="4ae4be42-9b07-4b72-89f2-c8f5d3a43a15",
        email="manager@example.test",
        hashed_password=password_hash,
        role=UserRole.manager,
        is_active=True,
        session_version=0,
        data_label="synthetic",
    )


@pytest.fixture
def db_mock(manager):
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = manager
    session.execute.return_value = result
    return session


@pytest.fixture
def client(db_mock):
    async def override():
        yield db_mock

    app.dependency_overrides[get_session] = override
    app.dependency_overrides[get_optional_session] = override
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def authenticate(client, user, *, role=None):
    token = create_session_token(user.id, role or user.role.value, user.session_version)
    csrf = generate_csrf_token(token)
    client.cookies.set(settings.session_cookie_name, token)
    client.cookies.set(settings.csrf_cookie_name, csrf)
    return {"X-CSRF-Token": csrf}
