"""Decode photos, strip metadata and issue user-bound, short-lived download links."""

import io
import secrets
import warnings
from datetime import UTC, datetime, timedelta

import jwt
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import settings
from app.core.errors import APIError, HiddenResourceError
from app.models.user import User
from app.schemas.common import FieldError

MIME_FORMATS = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}


def photo_error(message: str, status: int = 422) -> APIError:
    return APIError(
        status,
        "invalid_photo" if status != 413 else "photo_too_large",
        message,
        [FieldError(field="body.file", message=message, type="invalid_photo")],
    )


def sanitize_photo(data: bytes, mime_type: str) -> tuple[bytes, str]:
    if len(data) > settings.photo_max_bytes:
        raise photo_error("Photo exceeds the maximum upload size", 413)
    if mime_type not in MIME_FORMATS:
        raise photo_error("Only JPEG, PNG and WebP photos are supported", 415)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data), formats=list(MIME_FORMATS.values())) as image:
                if image.format != MIME_FORMATS[mime_type]:
                    raise photo_error("Photo content does not match its MIME type")
                if image.width * image.height > settings.photo_max_pixels:
                    raise photo_error("Photo dimensions exceed the pixel limit")
                if getattr(image, "n_frames", 1) != 1:
                    raise photo_error("Animated photos are not supported")
                image.load()
                oriented = ImageOps.exif_transpose(image)
                # A new pixel-only image drops EXIF/GPS, ICC, XMP, comments and PNG text.
                pixels = oriented.convert("RGBA")
                clean = Image.new("RGBA", pixels.size)
                clean.paste(pixels)
                output = io.BytesIO()
                clean.save(output, format="PNG")
                result = output.getvalue()
                if len(result) > settings.photo_max_bytes:
                    raise photo_error("Sanitized photo exceeds the storage size limit", 413)
                return result, "image/png"
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        SyntaxError,
        Image.DecompressionBombWarning,
        Image.DecompressionBombError,
    ) as exc:
        raise photo_error("Photo content is corrupt or unsupported") from exc


def issue_photo_token(attachment_id: str, user: User) -> tuple[str, datetime]:
    now = datetime.now(UTC)
    expires = now + timedelta(seconds=settings.photo_url_ttl_seconds)
    token = jwt.encode(
        {
            "sub": user.id,
            "attachment_id": attachment_id,
            "ver": user.session_version or 0,
            "type": "photo-download",
            "aud": "mangrove-photo",
            "iat": now,
            "exp": expires,
            "jti": secrets.token_hex(16),
        },
        settings.jwt_secret,
        algorithm="HS256",
    )
    return token, expires


def verify_photo_token(token: str, attachment_id: str, user: User) -> None:
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            audience="mangrove-photo",
            options={"require": ["sub", "attachment_id", "ver", "type", "exp", "iat", "jti"]},
        )
        if (
            claims["sub"] != user.id
            or claims["attachment_id"] != attachment_id
            or claims["ver"] != (user.session_version or 0)
            or claims["type"] != "photo-download"
        ):
            raise jwt.InvalidTokenError()
    except jwt.InvalidTokenError as exc:
        # Do not distinguish an expired link, a forged link or a hidden photo.
        raise HiddenResourceError() from exc
