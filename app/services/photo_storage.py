"""Private S3 adapter. Downloads go through an authenticated API, never public ACLs."""

from functools import lru_cache

import boto3  # type: ignore[import-untyped]
from botocore.config import Config  # type: ignore[import-untyped]
from botocore.exceptions import BotoCoreError, ClientError  # type: ignore[import-untyped]

from app.core.config import Settings, settings
from app.core.errors import APIError


def storage_unavailable() -> APIError:
    return APIError(503, "storage_unavailable", "Photo storage is unavailable; try again later")


class S3PhotoStorage:
    def __init__(self, config: Settings):
        if not config.s3_enabled:
            raise storage_unavailable()
        self.bucket = config.s3_bucket
        credentials = {}
        if config.s3_access_key_id and config.s3_secret_access_key:
            credentials = {
                "aws_access_key_id": config.s3_access_key_id.get_secret_value(),
                "aws_secret_access_key": config.s3_secret_access_key.get_secret_value(),
            }
        elif config.s3_endpoint_url:
            raise storage_unavailable()
        # With AWS, no explicit keys means the standard SDK IAM role chain.
        try:
            self.client = boto3.client(
                "s3",
                endpoint_url=config.s3_endpoint_url,
                region_name=config.s3_region,
                config=Config(
                    signature_version="s3v4",
                    connect_timeout=3,
                    read_timeout=10,
                    retries={"max_attempts": 2},
                    s3={"addressing_style": "path"},
                ),
                **credentials,
            )
        except BotoCoreError as exc:
            raise storage_unavailable() from exc

    def put(self, key: str, data: bytes, mime_type: str) -> None:
        try:
            # No filename/EXIF/user-controlled metadata or public ACL is persisted.
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=data,
                ContentType=mime_type,
                CacheControl="private, no-store",
            )
        except (BotoCoreError, ClientError) as exc:
            raise storage_unavailable() from exc

    def delete(self, key: str) -> None:
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except (BotoCoreError, ClientError) as exc:
            raise storage_unavailable() from exc

    def get(self, key: str, max_bytes: int) -> bytes:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            body = response["Body"]
            try:
                data = body.read(max_bytes + 1)
                if len(data) > max_bytes:
                    raise storage_unavailable()
                return data
            finally:
                body.close()
        except (BotoCoreError, ClientError) as exc:
            raise storage_unavailable() from exc


@lru_cache(maxsize=1)
def get_photo_storage() -> S3PhotoStorage:
    return S3PhotoStorage(settings)
