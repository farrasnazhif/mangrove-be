from uuid import uuid4

from starlette.datastructures import Headers
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import Response

from app.core.errors import error_response
from app.core.observability import request_id_context


class APICORSMiddleware(CORSMiddleware):
    """Keep browser preflight denials inside the API's error contract too."""

    def preflight_response(self, request_headers: Headers) -> Response:
        response = super().preflight_response(request_headers)
        if response.status_code < 400:
            return response
        headers = {
            key: value
            for key, value in response.headers.items()
            if key not in {"content-type", "content-length"}
        }
        return error_response(
            request_id_context.get() or str(uuid4()),
            response.status_code,
            "cors_denied",
            "Cross-origin request not allowed",
            headers=headers,
        )
