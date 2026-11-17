"""Image safety and capability validation without a database or object store."""

import io
import random
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from PIL import Image, PngImagePlugin
from PIL.TiffImagePlugin import IFDRational

from app.core.config import settings
from app.core.errors import APIError, HiddenResourceError
from app.models.user import User
from app.services.photos import issue_photo_token, sanitize_photo, verify_photo_token


def image_bytes(fmt="PNG", **options):
    output = io.BytesIO()
    Image.new("RGB", (12, 8), "green").save(output, format=fmt, **options)
    return output.getvalue()


def test_strip_exif_gps_and_preserve_orientation():
    exif = Image.Exif()
    exif[274] = 6
    exif[271] = "PRIVATE CAMERA"
    exif[34853] = {
        1: "N",
        2: (IFDRational(7), IFDRational(20), IFDRational(0)),
        3: "E",
        4: (IFDRational(112), IFDRational(40), IFDRational(0)),
    }
    original = image_bytes("JPEG", exif=exif)
    with Image.open(io.BytesIO(original)) as image:
        assert image.getexif().get_ifd(34853)
    clean, mime = sanitize_photo(original, "image/jpeg")
    assert mime == "image/png"
    with Image.open(io.BytesIO(clean)) as image:
        assert image.size == (8, 12)
        assert not image.getexif()
        assert not image.info
    assert b"PRIVATE CAMERA" not in clean


def test_strip_png_text_and_xmp():
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("GPS", "private coordinates")
    metadata.add_text("XML:com.adobe.xmp", "private metadata")
    clean, _ = sanitize_photo(image_bytes(pnginfo=metadata), "image/png")
    with Image.open(io.BytesIO(clean)) as image:
        assert not image.info
    assert b"private" not in clean


@pytest.mark.parametrize(
    "fmt,mime", [("PNG", "image/png"), ("JPEG", "image/jpeg"), ("WEBP", "image/webp")]
)
def test_supported_formats_are_reencoded(fmt, mime):
    clean, result_mime = sanitize_photo(image_bytes(fmt), mime)
    assert clean.startswith(b"\x89PNG\r\n\x1a\n") and result_mime == "image/png"


@pytest.mark.parametrize(
    "data,mime,status",
    [
        (b"<svg onload='alert(1)'/>", "image/svg+xml", 415),
        (b"<svg/>", "image/png", 422),
        (b"not a photo", "image/jpeg", 422),
        (image_bytes(), "image/jpeg", 422),
        (image_bytes("JPEG")[:100], "image/jpeg", 422),
        (b"", "image/png", 422),
    ],
)
def test_invalid_photo_rejected(data, mime, status):
    with pytest.raises(APIError) as error:
        sanitize_photo(data, mime)
    assert error.value.status_code == status
    assert error.value.details[0].field == "body.file"


def test_file_and_pixel_limits(monkeypatch):
    monkeypatch.setattr(settings, "photo_max_bytes", 1024)
    with pytest.raises(APIError) as error:
        sanitize_photo(b"x" * 1025, "image/png")
    assert error.value.status_code == 413
    monkeypatch.setattr(settings, "photo_max_pixels", 10)
    with pytest.raises(APIError, match="pixel limit"):
        sanitize_photo(image_bytes(), "image/png")


def test_reencoded_size_is_bounded(monkeypatch):
    image = Image.frombytes("RGB", (64, 64), random.Random(5).randbytes(64 * 64 * 3))
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=40)
    monkeypatch.setattr(settings, "photo_max_bytes", 5000)
    assert len(output.getvalue()) < 5000
    with pytest.raises(APIError) as error:
        sanitize_photo(output.getvalue(), "image/jpeg")
    assert error.value.status_code == 413


def test_animated_photo_rejected():
    output = io.BytesIO()
    first = Image.new("RGB", (4, 4), "green")
    first.save(output, format="PNG", save_all=True, append_images=[Image.new("RGB", (4, 4), "red")])
    with pytest.raises(APIError, match="Animated"):
        sanitize_photo(output.getvalue(), "image/png")


def test_tokens_are_bound_to_user_photo_session_and_expiry():
    user = User(id=str(uuid4()), session_version=0)
    photo_id = str(uuid4())
    token, expires = issue_photo_token(photo_id, user)
    assert 0 < (expires - datetime.now(UTC)).total_seconds() <= settings.photo_url_ttl_seconds
    verify_photo_token(token, photo_id, user)
    with pytest.raises(HiddenResourceError):
        verify_photo_token(token, str(uuid4()), user)
    with pytest.raises(HiddenResourceError):
        verify_photo_token(token, photo_id, User(id=str(uuid4()), session_version=0))
    user.session_version = 1
    with pytest.raises(HiddenResourceError):
        verify_photo_token(token, photo_id, user)
    user.session_version = 0
    claims = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"], audience="mangrove-photo")
    claims["exp"] = datetime.now(UTC) - timedelta(seconds=1)
    expired = jwt.encode(claims, settings.jwt_secret, algorithm="HS256")
    with pytest.raises(HiddenResourceError):
        verify_photo_token(expired, photo_id, user)
    forged = jwt.encode(claims, "different-test-key-at-least-32-bytes", algorithm="HS256")
    with pytest.raises(HiddenResourceError):
        verify_photo_token(forged, photo_id, user)
