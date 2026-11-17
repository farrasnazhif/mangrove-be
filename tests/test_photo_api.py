"""Photo transactions and API access; optional real MinIO round trip."""

import io
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import jwt
import pytest
from PIL import Image
from sqlalchemy import event, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, settings
from app.core.security import create_session_token, generate_csrf_token
from app.db.seed import seed_id
from app.db.session import get_session
from app.main import app
from app.models import Attachment, AuditEvent, Plot, User
from app.services.photo_storage import S3PhotoStorage, get_photo_storage, storage_unavailable
from tests.test_field_data import api as field_api  # noqa: F401
from tests.test_photos import image_bytes
from tests.test_task02_database import database  # noqa: F401

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="Set TEST_DATABASE_URL"),
]


class MemoryStorage:
    def __init__(self):
        self.objects = {}
        self.fail_put = False

    def put(self, key, data, mime_type):
        self.objects[key] = data
        if self.fail_put:
            raise storage_unavailable()

    def get(self, key, max_bytes):
        return self.objects[key]

    def delete(self, key):
        self.objects.pop(key, None)


@pytest.fixture
def storage():
    store = MemoryStorage()
    app.dependency_overrides[get_photo_storage] = lambda: store
    yield store
    app.dependency_overrides.pop(get_photo_storage, None)


def upload(request, **kwargs):
    return request(
        "POST",
        f"/plots/{seed_id('plot-1')}/photos",
        files={"file": ("test.jpg", image_bytes("JPEG"), "image/jpeg")},
        **kwargs,
    )


def test_upload_link_to_tree_download_and_expiry(field_api, storage):  # noqa: F811
    request, run, connection = field_api
    result = upload(request, data={"visibility": "public"})
    assert result.status_code == 201, result.text
    photo = result.json()
    assert photo["mime_type"] == "image/png" and photo["visibility"] == "public"
    assert "object_key" not in photo
    photo_id = photo["id"]
    assert run(connection.scalar(select(Plot.row_version).where(Plot.id == seed_id("plot-1")))) == 2
    assert run(connection.scalar(select(func.count()).select_from(AuditEvent))) == 2
    linked = request(
        "PATCH",
        f"/plots/{seed_id('plot-1')}/trees/{seed_id('plot-1/tree-1')}",
        json={"row_version": 1, "photo_id": photo_id},
    )
    assert linked.status_code == 200, linked.text
    assert linked.json()["photo_id"] == photo_id
    issued = request("POST", f"/photos/{photo_id}/download-url")
    assert issued.status_code == 200, issued.text
    assert issued.headers["cache-control"] == "private, no-store"
    url = issued.json()["download_url"].removeprefix("/api/v1")
    image = request("GET", url)
    assert image.status_code == 200, image.text
    assert image.headers["content-type"] == "image/png"
    assert image.headers["x-content-type-options"] == "nosniff"
    assert image.headers["cache-control"] == "private, no-store"
    with Image.open(io.BytesIO(image.content)) as decoded:
        assert not decoded.getexif()
    assert request("GET", url, headers={"Authorization": ""}).status_code == 401
    token = url.split("token=", 1)[1]
    assert request("GET", url, headers={"Authorization": "Bearer " + token}).status_code == 401
    claims = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"], audience="mangrove-photo")
    claims["exp"] = datetime.now(UTC) - timedelta(seconds=1)
    expired = jwt.encode(claims, settings.jwt_secret, algorithm="HS256")
    assert request("GET", f"/photos/{photo_id}/content?token={expired}").status_code == 404
    assert request("GET", f"/photos/{uuid4()}/content?token={token}").status_code == 404
    other_user = str(uuid4())
    run(
        connection.execute(
            insert(User).values(
                id=other_user,
                email="photo-other@example.test",
                role="manager",
                is_active=True,
                session_version=0,
                data_label="synthetic",
            )
        )
    )
    assert (
        request(
            "GET",
            url,
            headers={"Authorization": "Bearer " + create_session_token(other_user, "manager")},
        ).status_code
        == 404
    )
    wrong_plot = request(
        "PATCH",
        f"/plots/{seed_id('plot-2')}/trees/{seed_id('plot-2/tree-1')}",
        json={"row_version": 1, "photo_id": photo_id},
    )
    assert wrong_plot.status_code == 422


def test_failed_storage_rolls_back_metadata_audit_revision_and_object(field_api, storage):  # noqa: F811
    request, run, connection = field_api
    storage.fail_put = True
    assert upload(request).status_code == 503
    assert not storage.objects
    assert run(connection.scalar(select(func.count()).select_from(Attachment))) == 0
    assert run(connection.scalar(select(func.count()).select_from(AuditEvent))) == 0
    assert run(connection.scalar(select(Plot.row_version).where(Plot.id == seed_id("plot-1")))) == 1


def test_cookie_upload_requires_session_bound_csrf(field_api, storage):  # noqa: F811
    request, _, _ = field_api
    session_token = create_session_token(seed_id("manager"), "manager")
    csrf = generate_csrf_token(session_token)
    cookie = f"{settings.session_cookie_name}={session_token}; {settings.csrf_cookie_name}={csrf}"
    assert upload(request, headers={"Cookie": cookie}).status_code == 403
    assert not storage.objects
    result = upload(request, headers={"Cookie": cookie, "X-CSRF-Token": csrf})
    assert result.status_code == 201, result.text
    assert result.json()["visibility"] == "private"


def test_failed_database_commit_cleans_uploaded_object(field_api, storage):  # noqa: F811
    request, run, connection = field_api

    def reject_commit(session):
        raise RuntimeError("simulated database commit failure")

    async def failing_session():
        async with AsyncSession(
            bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        ) as session:
            event.listen(session.sync_session, "before_commit", reject_commit)
            yield session

    original = app.dependency_overrides[get_session]
    app.dependency_overrides[get_session] = failing_session
    try:
        assert upload(request).status_code == 500
        assert not storage.objects
        assert run(connection.scalar(select(func.count()).select_from(Attachment))) == 0
        assert run(connection.scalar(select(func.count()).select_from(AuditEvent))) == 0
    finally:
        app.dependency_overrides[get_session] = original


def test_invalid_file_or_missing_parent_writes_nothing(field_api, storage, monkeypatch):  # noqa: F811
    request, run, connection = field_api
    path = f"/plots/{seed_id('plot-1')}/photos"
    bad = request("POST", path, files={"file": ("bad.png", b"not a photo", "image/png")})
    assert bad.status_code == 422
    missing = request(
        "POST",
        f"/plots/{uuid4()}/photos",
        files={"file": ("photo.png", image_bytes(), "image/png")},
    )
    assert missing.status_code == 404
    monkeypatch.setattr(settings, "photo_max_bytes", 1024)
    large = request("POST", path, files={"file": ("large.png", b"x" * 1025, "image/png")})
    assert large.status_code == 413

    async def chunks():
        for _ in range(70):
            yield b"x" * 1024

    # Chunked upload has no Content-Length; reject before multipart parsing/spooling.
    chunked = request(
        "POST",
        path,
        content=chunks(),
        headers={"Content-Type": "multipart/form-data; boundary=test"},
    )
    assert chunked.status_code == 413
    assert not storage.objects
    assert run(connection.scalar(select(func.count()).select_from(Attachment))) == 0
    assert run(connection.scalar(select(func.count()).select_from(AuditEvent))) == 0


@pytest.mark.skipif(
    not os.environ.get("TEST_S3_ENDPOINT_URL"), reason="Set TEST_S3_ENDPOINT_URL for real MinIO"
)
def test_real_minio_private_round_trip(field_api):  # noqa: F811
    request, _, _ = field_api
    config = Settings(
        s3_enabled=True,
        s3_endpoint_url=os.environ["TEST_S3_ENDPOINT_URL"],
        s3_bucket="mangrove-test-" + uuid4().hex,
        s3_access_key_id=os.environ["TEST_S3_ACCESS_KEY_ID"],
        s3_secret_access_key=os.environ["TEST_S3_SECRET_ACCESS_KEY"],
    )
    store = S3PhotoStorage(config)
    store.client.create_bucket(Bucket=store.bucket)
    app.dependency_overrides[get_photo_storage] = lambda: store
    try:
        result = upload(request)
        assert result.status_code == 201, result.text
        photo_id = result.json()["id"]
        key = f"plots/{seed_id('plot-1')}/{photo_id}.png"
        direct = httpx.get(f"{config.s3_endpoint_url}/{store.bucket}/{key}")
        assert direct.status_code == 403
        issued = request("POST", f"/photos/{photo_id}/download-url")
        assert issued.status_code == 200, issued.text
        content = request("GET", issued.json()["download_url"].removeprefix("/api/v1"))
        assert content.status_code == 200
        assert content.content == store.get(key, settings.photo_max_bytes)
        assert (
            request(
                "GET",
                issued.json()["download_url"].removeprefix("/api/v1"),
                headers={"Authorization": ""},
            ).status_code
            == 401
        )
    finally:
        # Only this test's UUID-named bucket and its generated objects are removed.
        for item in store.client.list_objects_v2(Bucket=store.bucket).get("Contents", []):
            store.delete(item["Key"])
        store.client.delete_bucket(Bucket=store.bucket)
        app.dependency_overrides.pop(get_photo_storage, None)
