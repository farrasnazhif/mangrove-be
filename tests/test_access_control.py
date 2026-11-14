import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.api.deps import optional_user, require_manager
from app.core.config import settings
from app.core.security import create_session_token
from app.main import app

# Set of allowed explicit access dependencies
EXPLICIT_ACCESS_DEPENDENCIES = {require_manager, optional_user}

# Endpoints that are explicitly public or documentation (exempt from require_manager)
EXEMPT_DOCS_PATHS = {"/docs", "/redoc", "/openapi.json"}


def get_all_api_routes() -> list[APIRoute]:
    """Retrieve all defined APIRoutes in the application."""
    routes: list[APIRoute] = []
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path not in EXEMPT_DOCS_PATHS:
            routes.append(route)
    return routes


def test_no_route_without_explicit_access_dependency():
    """Verify that EVERY API route in the application declares an explicit access dependency.

    This ensures no route is accidentally made public or left unguarded.
    Allowed dependencies: `require_manager` or `optional_user`.
    """
    routes = get_all_api_routes()
    missing_dependency_routes: list[str] = []

    for route in routes:
        # Collect dependencies from route.dependencies and endpoint parameter default Depends
        all_deps = set()

        for dep in route.dependencies:
            all_deps.add(dep.dependency)

        # Also inspect endpoint parameter dependencies
        if hasattr(route, "dependant"):
            for sub_dep in route.dependant.dependencies:
                all_deps.add(sub_dep.call)

        # Check if any explicit access dependency is declared
        if not (all_deps & EXPLICIT_ACCESS_DEPENDENCIES) and route.path not in {
            "/api/v1/auth/login",
            "/api/v1/auth/logout",
            "/api/v1/auth/csrf",
        }:
            missing_dependency_routes.append(f"{route.methods} {route.path}")

    assert not missing_dependency_routes, (
        f"The following routes lack an explicit access dependency ({EXPLICIT_ACCESS_DEPENDENCIES}): "
        f"{missing_dependency_routes}"
    )


@pytest.mark.parametrize(
    "path,method",
    [
        ("/api/v1/me", "GET"),
        ("/api/v1/auth/me", "GET"),
    ],
)
def test_manager_routes_deny_anonymous(path: str, method: str):
    """Anonymous requests to manager routes must return 401 with no private fields leaked."""
    client = TestClient(app)
    response = client.request(method, path)
    assert response.status_code == 401
    body = response.json()
    # Ensure standard error structure without sensitive internal leaks
    assert "detail" in body
    assert not any(key in body for key in ["password", "hashed_password", "token", "secret"])


@pytest.mark.parametrize(
    "path,method",
    [
        ("/api/v1/me", "GET"),
        ("/api/v1/auth/me", "GET"),
    ],
)
def test_manager_routes_deny_visitor_role(path: str, method: str):
    """Authenticated visitor requests to manager routes must return 403."""
    client = TestClient(app)
    visitor_token = create_session_token("visitor-id", "visitor")
    client.cookies.set(settings.session_cookie_name, visitor_token)

    response = client.request(method, path)
    assert response.status_code == 403
    body = response.json()
    assert "detail" in body
    assert "Manager access required" in body["detail"]
