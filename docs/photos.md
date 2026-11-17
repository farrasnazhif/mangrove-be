# Photo storage and manual testing (Task 05)

Task 05 uses MinIO locally and a private S3-compatible bucket in production.
The API accepts a single JPEG, PNG or WebP (maximum 5 MiB and 20 million pixels).
It rejects corrupt, mismatched or animated content, applies EXIF orientation and
re-encodes pixel data as PNG without EXIF/GPS, XMP, ICC, comments or PNG text.
The sanitized output must also fit the size limit. SVG is not supported.

## Local setup

Install the locked dependencies and start the services:

```powershell
uv sync --frozen
docker compose up -d --build db minio
uv run alembic upgrade head
```

The MinIO image is built from the official pinned source release
[RELEASE.2025-10-15T17-29-55Z](https://github.com/minio/minio/releases/tag/RELEASE.2025-10-15T17-29-55Z).
The first build downloads the Go toolchain/dependencies and can take several minutes.
It uses a non-root runtime and binds its API/console only to localhost. The MinIO
repository is archived; this build is for local development, while production uses
the configured S3-compatible provider.

Add these development settings to `.env` (already added in this working session):

```dotenv
S3_ENABLED=true
S3_ENDPOINT_URL=http://127.0.0.1:9000
S3_REGION=us-east-1
S3_BUCKET=mangrove-photos
S3_ACCESS_KEY_ID=mangrove-local
S3_SECRET_ACCESS_KEY=local-development-only-change-me
PHOTO_MAX_BYTES=5242880
PHOTO_MAX_PIXELS=20000000
PHOTO_URL_TTL_SECONDS=300
```

These MinIO credentials are development defaults, separate from the Manager login.
Keep application credentials in ignored environment files or a secret manager.
Create/check the private bucket, then start or restart the API:

```powershell
uv run python -m scripts.setup_photo_storage
uv run uvicorn app.main:app --reload --port 8080 --no-access-log --log-config logging.json
```

Provisioning happens explicitly, never during application startup or user requests.
The setup script refuses public bucket ACLs and existing bucket policies, so an
unreviewed bucket policy cannot silently enable anonymous access. AWS S3 setup also
enables Block Public Access. A disabled/unreachable store returns a controlled 503.

## API contract

All routes require Manager access. Cookie-authenticated POSTs require CSRF.

| Operation | Path | Request / result |
| --- | --- | --- |
| Upload | `POST /api/v1/plots/{plot_id}/photos` | Multipart `file`, optional `visibility` (`private` by default); returns 201 with attachment ID and sanitized metadata. |
| Issue link | `POST /api/v1/photos/{photo_id}/download-url` | Returns a relative `download_url` and `expires_at`. |
| Read photo | `GET /api/v1/photos/{photo_id}/content?token=...` | Returns PNG bytes after checking login, signed token and parent plot. |

Upload records an `attachments` row and audit rows in the same database transaction,
and advances the plot revision. A storage failure rolls back metadata, audit and
revision changes; a database commit failure triggers removal of the newly uploaded
object. Only new UUID object keys are used, never client filenames or paths.
As with any database plus object store, process crashes can leave an orphan object;
operators must reconcile such objects against attachment rows. A cleanup failure
logs `photo.cleanup_failed` with the attachment ID without credentials or signed URLs.

The returned photo ID can be persisted on a tree in the same plot using its PATCH
route with `row_version` and `photo_id`. A photo from another plot is rejected.
Source images are never stored. Object keys are excluded from public API responses.

Signed API links expire after 300 seconds (configurable from 1 to 900) and are bound
to the user, photo and user's session version. A copied link still requires Manager
authentication. Another user, a changed session version, a forged token or an expired
link cannot use it. Photo tokens cannot be used as login/session tokens. Invalid
links return the same 404 as a missing photo; unauthenticated requests return 401.
Responses use `private, no-store`, `nosniff` and a generated PNG filename.

The bucket remains private even for rows marked `visibility=public`. That flag
expresses eligibility for future published-photo use; it does not bypass Manager
authorization here. Public map/publication delivery belongs to the later feature
tasks and must enforce their publication/scope rules.

## Manual test through localhost Swagger

1. Open `http://localhost:8080/docs`.
2. Execute `GET /api/v1/auth/csrf`, copy `csrf_token`, and set **CSRFToken** in
   **Authorize**. Execute login with your Manager email/password, then update
   **CSRFToken** with the new token returned from login. The browser stores the
   session cookie. Seed only creates the initial password; rerunning it preserves
   an existing account's password.
3. Execute `GET /api/v1/plots` and copy a plot ID. Expand the upload endpoint under
   **photos**, click **Try it out**, fill `plot_id`, choose an image with the file
   picker and execute. Expect **201**, `mime_type=image/png`, and a photo `id`.
4. To link it to a tree, obtain the tree's ID/current `row_version` from its list
   endpoint and PATCH the tree with `{"row_version": 1, "photo_id": "PHOTO_ID"}`,
   replacing the sample version with the actual current version. GET the tree list
   again and check that `photo_id` is saved.
5. Execute the issue-link endpoint with the photo ID. Open
   `http://localhost:8080` plus the returned relative `download_url` in the same
   browser to view the image. Use the same hostname as the login page so cookies
   are sent. Bearer-only clients must supply their Authorization header on download.
6. Open that URL in a logged-out/incognito browser: expect **401**. After the
   configured five-minute expiry, the logged-in browser gets **404** for the old
   URL. Request a new link to download again.
7. Try a non-image file or a mismatched MIME (**415/422**), and an oversized image
   (**413**). Check that failed uploads created no attachment/audit/revision change.

The MinIO console is at `http://127.0.0.1:9001` with the development storage
credentials. Database rows can be inspected with:

```powershell
docker compose exec db psql -U mangrove -d mangrove -c "SELECT id, entity_id, mime_type, size_bytes, visibility FROM attachments ORDER BY created_at DESC;"
```

## Automated verification

Use a dedicated PostGIS test database and explicit local test storage credentials:

```powershell
$env:TEST_DATABASE_URL = 'postgresql+asyncpg://mangrove:mangrove@127.0.0.1:5433/mangrove_test'
$env:TEST_S3_ENDPOINT_URL = 'http://127.0.0.1:9000'
$env:TEST_S3_ACCESS_KEY_ID = 'mangrove-local'
$env:TEST_S3_SECRET_ACCESS_KEY = 'local-development-only-change-me'
uv run pytest -q
```

Use the actual PostgreSQL host port (Compose defaults to 5432; this workspace uses
5433). Photo integration tests use isolated schemas and a UUID-named MinIO bucket,
then remove only the generated test bucket/objects. No production credentials or
application data are used. Without the explicit test variables, the corresponding
integration tests are skipped. CI supplies both PostGIS and MinIO settings.

## Production configuration

Set `S3_ENABLED=true`, the private bucket and region. On AWS, omit the endpoint and
explicit keys to use the SDK IAM role chain. With another provider, set its HTTPS
endpoint and both credential values through the secret manager. Grant the runtime
identity only the required GetObject/PutObject/DeleteObject permissions for the
photo prefix; use a separate provisioning identity for bucket administration.
Never enable an anonymous bucket policy/ACL. Production deployment, provider
credentials, monitoring and backups remain Task 11.

Keep access logs from recording query strings containing download tokens; the
documented startup command disables Uvicorn's raw access log and uses the existing
request-ID JSON logger. Configure reverse-proxy logs the same way.

Implementation references: [Pillow image validation](https://pillow.readthedocs.io/en/stable/reference/Image.html),
[S3 PutObject](https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/put_object.html)
and [S3 GetObject](https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/get_object.html).
