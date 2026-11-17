"""Request-scoped JSON events without request bodies, queries, headers or tokens."""

import json
import logging
import sys
import time
from contextvars import ContextVar
from datetime import UTC, datetime
from uuid import UUID, uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import error_response

request_id_context: ContextVar[str | None] = ContextVar("request_id", default=None)
logger = logging.getLogger("mangrove")


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
            "request_id": getattr(record, "request_id", None) or request_id_context.get(),
        }
        for field in ("method", "route", "status_code", "duration_ms", "exception_type"):
            if hasattr(record, field):
                data[field] = getattr(record, field)
        # Deliberately omit exception text, stack locals and arbitrary extra fields.
        return json.dumps(data, ensure_ascii=True)


def configure_app_logging() -> None:
    if not any(getattr(handler, "_mangrove_json", False) for handler in logger.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter())
        handler._mangrove_json = True  # type: ignore[attr-defined]
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        supplied = next(
            (value for key, value in scope["headers"] if key.lower() == b"x-request-id"), b""
        )
        try:
            request_id = str(UUID(supplied.decode("ascii")))
        except (ValueError, UnicodeError):
            request_id = str(uuid4())
        scope.setdefault("state", {})["request_id"] = request_id
        context_token = request_id_context.set(request_id)
        started = time.perf_counter()
        response_started = False
        status_code = 500

        async def with_request_id(message: Message) -> None:
            nonlocal response_started, status_code
            if message["type"] == "http.response.start":
                response_started = True
                status_code = message["status"]
                headers = [
                    (key, value)
                    for key, value in message.get("headers", [])
                    if key.lower() != b"x-request-id"
                ]
                message["headers"] = [*headers, (b"x-request-id", request_id.encode("ascii"))]
            await send(message)

        try:
            await self.app(scope, receive, with_request_id)
        except Exception as exc:
            logger.error("http.error", extra={"exception_type": type(exc).__name__})
            if response_started:
                raise
            response = error_response(
                request_id, 500, "internal_server_error", "Internal server error"
            )
            await response(scope, receive, with_request_id)
        finally:
            route = scope.get("route")
            logger.info(
                "http.request",
                extra={
                    "method": scope["method"],
                    "route": getattr(route, "path", "unmatched"),
                    "status_code": status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                },
            )
            request_id_context.reset(context_token)
