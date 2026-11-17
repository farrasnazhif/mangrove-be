"""Bound multipart bodies before Starlette parses/spools uploaded files."""

import re

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import settings
from app.core.errors import error_response
from app.schemas.common import FieldError


class PhotoUploadLimitMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or not re.fullmatch(r"/api/v1/plots/[^/]+/photos/?", scope["path"])
        ):
            await self.app(scope, receive, send)
            return
        # Allow small multipart framing overhead; file bytes have their own strict limit.
        limit = settings.photo_max_bytes + 64 * 1024
        data = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(data) + len(chunk) > limit:
                response = error_response(
                    scope["state"]["request_id"],
                    413,
                    "photo_too_large",
                    "Photo upload exceeds the request size limit",
                    [FieldError(field="body.file", message="Upload too large", type="too_large")],
                )
                await response(scope, receive, send)
                return
            data.extend(chunk)
            if not message.get("more_body", False):
                break
        consumed = False

        async def bounded_receive() -> Message:
            nonlocal consumed
            if consumed:
                return await receive()
            consumed = True
            return {"type": "http.request", "body": bytes(data), "more_body": False}

        await self.app(scope, bounded_receive, send)
