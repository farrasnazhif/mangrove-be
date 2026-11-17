"""Photo objects stay private; signed API URLs additionally require Manager auth."""

import logging
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.api.deps import require_manager
from app.api.v1.field_data import transaction
from app.core.config import settings
from app.core.errors import APIError, HiddenResourceError
from app.db.session import get_session
from app.models.inventory import Plot, new_id
from app.models.provenance import Attachment
from app.models.user import User
from app.schemas.photos import PhotoDownloadResponse, PhotoResponse
from app.services.audit import record_change
from app.services.field_data import active, touch_plot
from app.services.photo_storage import S3PhotoStorage, get_photo_storage
from app.services.photos import issue_photo_token, photo_error, sanitize_photo, verify_photo_token

router = APIRouter(tags=["photos"])
logger = logging.getLogger("mangrove")


@router.post("/plots/{plot_id}/photos", response_model=PhotoResponse, status_code=201)
async def upload_photo(
    plot_id: UUID,
    file: UploadFile = File(),
    visibility: Literal["private", "public"] = Form(default="private"),
    user: User = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
    storage: S3PhotoStorage = Depends(get_photo_storage),
):
    attachment_id = new_id()
    key = f"plots/{plot_id}/{attachment_id}.png"
    uploaded = False
    try:
        data = await file.read(settings.photo_max_bytes + 1)
        clean, mime_type = await run_in_threadpool(sanitize_photo, data, file.content_type or "")
        async with session.begin():
            plot = await active(session, Plot, str(plot_id), lock=True)
            attachment = Attachment(
                id=attachment_id,
                entity_type="plots",
                entity_id=plot.id,
                object_key=key,
                mime_type=mime_type,
                size_bytes=len(clean),
                visibility=visibility,
                uploaded_by=user.id,
            )
            session.add(attachment)
            record_change(session, actor_id=user.id, record=attachment, action="create", before={})
            await touch_plot(session, plot, user.id)
            await session.flush()
            await session.refresh(attachment)
            # Validate the response before creating an external object or committing.
            result = PhotoResponse.model_validate(attachment)
            # A timeout can occur after the object reached storage, so cleanup is
            # attempted even if put() does not return successfully.
            uploaded = True
            await run_in_threadpool(storage.put, key, clean, mime_type)
        return result
    except BaseException:
        if uploaded:
            try:
                await run_in_threadpool(storage.delete, key)
            except APIError:
                # No object key, credentials or signed URL enters the log.
                logger.error("photo.cleanup_failed", extra={"attachment_id": attachment_id})
        raise
    finally:
        await file.close()


async def authorized_photo(session: AsyncSession, photo_id: str) -> Attachment:
    photo = await session.get(Attachment, photo_id)
    if photo is None or photo.entity_type != "plots" or photo.mime_type != "image/png":
        raise HiddenResourceError()
    await active(session, Plot, photo.entity_id)
    return photo


@router.post("/photos/{photo_id}/download-url", response_model=PhotoDownloadResponse)
async def photo_download_url(
    photo_id: UUID,
    response: Response,
    user: User = Depends(require_manager),
    session: AsyncSession = Depends(transaction, scope="function"),
):
    await authorized_photo(session, str(photo_id))
    token, expires = issue_photo_token(str(photo_id), user)
    response.headers["Cache-Control"] = "private, no-store"
    return PhotoDownloadResponse(
        download_url=f"/api/v1/photos/{photo_id}/content?token={token}",
        expires_at=expires,
    )


@router.get(
    "/photos/{photo_id}/content",
    response_class=Response,
    responses={200: {"content": {"image/png": {"schema": {"type": "string", "format": "binary"}}}}},
)
async def photo_content(
    photo_id: UUID,
    token: str = Query(min_length=1, max_length=4096),
    user: User = Depends(require_manager),
    session: AsyncSession = Depends(transaction, scope="function"),
    storage: S3PhotoStorage = Depends(get_photo_storage),
):
    verify_photo_token(token, str(photo_id), user)
    photo = await authorized_photo(session, str(photo_id))
    data = await run_in_threadpool(storage.get, photo.object_key, settings.photo_max_bytes)
    if len(data) != photo.size_bytes:
        raise photo_error("Stored photo is incomplete", 503)
    return Response(
        data,
        media_type="image/png",
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": f'inline; filename="{photo.id}.png"',
            "Referrer-Policy": "no-referrer",
        },
    )
