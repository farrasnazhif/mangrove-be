"""Provision/check a private photo bucket. Runtime requests never create buckets."""

from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from app.core.config import settings
from app.services.photo_storage import get_photo_storage


def main() -> None:
    storage = get_photo_storage()
    client, bucket = storage.client, storage.bucket
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError as exc:
        if exc.response["Error"]["Code"] not in {"404", "NoSuchBucket", "NotFound"}:
            raise RuntimeError("Cannot access the configured photo bucket") from None
        options = {"Bucket": bucket}
        if settings.s3_region != "us-east-1":
            options["CreateBucketConfiguration"] = {"LocationConstraint": settings.s3_region}
        client.create_bucket(**options)
    # No bucket policy is needed for owner credentials / IAM identity permissions.
    # Do not silently reuse a bucket whose policy may grant anonymous access.
    try:
        client.get_bucket_policy(Bucket=bucket)
    except ClientError as exc:
        if exc.response["Error"]["Code"] not in {"NoSuchBucketPolicy", "404"}:
            raise RuntimeError("Cannot verify photo bucket privacy") from None
    else:
        raise RuntimeError("Photo bucket has a policy; verify/remove it before provisioning")
    acl = client.get_bucket_acl(Bucket=bucket)
    if any(
        grant["Grantee"].get("URI", "").endswith(("/AllUsers", "/AuthenticatedUsers"))
        for grant in acl.get("Grants", [])
    ):
        raise RuntimeError("Photo bucket grants public access; use a private bucket")
    if settings.s3_endpoint_url is None:
        client.put_public_access_block(
            Bucket=bucket,
            PublicAccessBlockConfiguration={
                "BlockPublicAcls": True,
                "IgnorePublicAcls": True,
                "BlockPublicPolicy": True,
                "RestrictPublicBuckets": True,
            },
        )
    print("Private photo bucket is ready. No anonymous policy/ACL is enabled.")


if __name__ == "__main__":
    main()
