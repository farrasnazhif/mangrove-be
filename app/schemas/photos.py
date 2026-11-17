from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field

from app.schemas.common import ContractModel


class PhotoResponse(ContractModel):
    id: UUID
    entity_id: UUID
    entity_type: Literal["plots"]
    mime_type: Literal["image/png"]
    size_bytes: int = Field(gt=0)
    visibility: Literal["private", "public"]
    created_at: AwareDatetime


class PhotoDownloadResponse(ContractModel):
    # Relative URL prevents untrusted Host headers from becoming download links.
    download_url: str
    expires_at: AwareDatetime
