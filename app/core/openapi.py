from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from app.api.policy import PUBLIC_OPERATIONS
from app.core.config import settings


def install_openapi(app: FastAPI) -> None:
    def schema() -> dict:
        if app.openapi_schema:
            return app.openapi_schema
        result = get_openapi(
            title=app.title, version=app.version, description=app.description, routes=app.routes
        )
        schemes = result.setdefault("components", {}).setdefault("securitySchemes", {})
        schemes.update(
            {
                "SessionCookie": {
                    "type": "apiKey",
                    "in": "cookie",
                    "name": settings.session_cookie_name,
                },
                "BearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"},
                "CSRFToken": {"type": "apiKey", "in": "header", "name": "X-CSRF-Token"},
            }
        )
        for path, operations in result["paths"].items():
            for method, operation in operations.items():
                if method not in {"get", "post", "put", "patch", "delete", "head", "options"}:
                    continue
                public = (method.upper(), path) in PUBLIC_OPERATIONS
                operation["x-access-role"] = "visitor-or-manager" if public else "manager"
                if path == "/api/v1/auth/login":
                    operation["security"] = [{"CSRFToken": []}]
                elif public:
                    operation["security"] = [{}, {"SessionCookie": []}, {"BearerAuth": []}]
                else:
                    cookie: dict[str, list[str]] = {"SessionCookie": []}
                    if method in {"post", "put", "patch", "delete"}:
                        cookie["CSRFToken"] = []
                    operation["security"] = [cookie, {"BearerAuth": []}]
                if public and path == "/api/v1/chat/messages":
                    operation["description"] += (
                        " Cookie-authenticated requests also require X-CSRF-Token."
                    )
                for response in operation.get("responses", {}).values():
                    response.setdefault("headers", {})["X-Request-ID"] = {
                        "description": "Correlation ID for this request",
                        "schema": {"type": "string", "format": "uuid"},
                    }
        app.openapi_schema = result
        return result

    app.openapi = schema  # type: ignore[method-assign]
