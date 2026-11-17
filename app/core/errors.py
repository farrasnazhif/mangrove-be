from collections.abc import Mapping
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.schemas.common import ErrorResponse, FieldError


class APIError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: list[FieldError] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or []


class HiddenResourceError(APIError):
    """Use for both nonexistent and inaccessible records; never include record IDs."""

    def __init__(self) -> None:
        super().__init__(404, "not_found", "Resource not found")


def error_response(
    request_id: str,
    status_code: int,
    code: str,
    message: str,
    details: list[FieldError] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(
            code=code,
            message=message,
            details=details or [],
            request_id=request_id,
        ).model_dump(mode="json"),
        headers={**(headers or {}), "X-Request-ID": request_id, "Cache-Control": "no-store"},
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(APIError)
    async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
        return error_response(
            request.state.request_id,
            exc.status_code,
            exc.code,
            exc.message,
            exc.details,
        )

    @app.exception_handler(HTTPException)
    async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
        status = HTTPStatus(exc.status_code)
        code = status.name.lower()
        message = exc.detail if isinstance(exc.detail, str) else status.phrase
        if exc.status_code == 404:
            message = "Resource not found"
        if exc.status_code >= 500:
            message = "Internal server error"
        return error_response(
            request.state.request_id, exc.status_code, code, message, headers=exc.headers
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Never return pydantic's `input`/`ctx`: these can contain passwords or tokens.
        details = [
            FieldError(
                field=".".join(str(part) for part in error["loc"]),
                message=("Invalid value" if error["type"] == "value_error" else error["msg"]),
                type=error["type"],
            )
            for error in exc.errors()
        ]
        return error_response(
            request.state.request_id,
            422,
            "validation_error",
            "Request validation failed",
            details,
        )
