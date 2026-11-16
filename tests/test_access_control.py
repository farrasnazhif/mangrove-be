import base64
import json
import re

import pytest
from fastapi.routing import APIRoute

from app.api.deps import optional_user, require_manager
from app.core.config import settings
from app.core.security import create_session_token
from app.main import app
from app.models.user import UserRole

# A private route changed to optional_user must fail the audit. New public routes
# require deliberate review here, instead of silently escaping authorization tests.
PUBLIC_ROUTES = {
    ("GET", "/api/v1/health"),
    ("POST", "/api/v1/auth/login"),
    ("GET", "/api/v1/auth/csrf"),
}


def api_routes():
    routes = []
    for route in app.routes:
        if isinstance(route, APIRoute):
            routes.append(route)
        elif hasattr(route, "effective_route_contexts"):
            routes.extend(r for r in route.effective_route_contexts() if hasattr(r, "dependant"))
    return routes


def manager_routes():
    return [
        (method, route.path)
        for route in api_routes()
        for method in route.methods
        if (method, route.path) not in PUBLIC_ROUTES
    ]


def test_every_route_has_explicit_expected_access():
    routes = api_routes()
    assert routes, "Route audit must never pass without scanning routes"
    paths = {route.path for route in routes}
    assert paths == set(app.openapi()["paths"])
    for route in routes:
        dependencies = {dependency.call for dependency in route.dependant.dependencies}
        for method in route.methods:
            expected = optional_user if (method, route.path) in PUBLIC_ROUTES else require_manager
            assert expected in dependencies, f"{method} {route.path} needs {expected.__name__}"


@pytest.mark.parametrize("method,path", manager_routes())
@pytest.mark.parametrize(
    "attack", ["anonymous", "visitor", "forged-jwt", "role-header", "role-query"]
)
def test_manager_routes_reject_modified_requests(client, manager, db_mock, method, path, attack):
    headers = {}
    if attack in {"visitor", "forged-jwt"}:
        manager.role = UserRole.visitor
        token = create_session_token(manager.id, "visitor")
        if attack == "forged-jwt":
            head, payload, signature = token.split(".")
            data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
            data["role"] = "manager"
            payload = base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip("=")
            token = f"{head}.{payload}.{signature}"
        client.cookies.set(settings.session_cookie_name, token)
    elif attack == "role-header":
        headers = {"X-Role": "manager", "X-User-Role": "manager"}
    elif attack == "role-query":
        path += "?role=manager"
    path = re.sub(r"\{[^}]+\}", "00000000-0000-0000-0000-000000000001", path)
    response = client.request(method, path, headers=headers)
    assert response.status_code == (403 if attack == "visitor" else 401)
    assert not any(
        value in response.text for value in [manager.email, "hashed_password", "csrf_token"]
    )
    db_mock.commit.assert_not_awaited()


def test_anonymous_public_access_does_not_open_database():
    from unittest.mock import patch

    from fastapi.testclient import TestClient

    with patch("app.api.deps.SessionLocal") as session_factory:
        with TestClient(app) as client:
            assert client.get("/api/v1/health").status_code == 200
            assert client.get("/api/v1/auth/csrf").status_code == 200
        session_factory.assert_not_called()
