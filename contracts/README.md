# Frontend API contract

`openapi.json` is the reviewed OpenAPI 3.1 document for all 19 P0 operations in PRD
section 9.4, plus implemented auth/health operations. Import this file into the frontend
API client generator, Postman or another OpenAPI-compatible client. The same document
is served at `/openapi.json` and rendered at `/docs`.

Operations with `x-implementation-status: planned` validate access and inputs, then
return **501**, without writing data or returning fabricated inventory. Their 2xx DTOs
define the future feature contract; they are not operational features yet. Implement
the actual feature in its backlog task and remove the planned marker at that time.

Every error has exactly `code`, `message`, `details`, `request_id`. Validation details
contain `field`, `message`, `type`; raw input/passwords and exception context are omitted.
`X-Request-ID` is returned on every response and exposed through CORS. Clients should
read `message`/`details` instead of FastAPI's former `detail` property.

Collections use `{items, page, page_size, total}`. Defaults: page 1, size 25, max 100.
`sort=-code` means descending. Repeat `filter=field:value` for filters. Unsupported query
parameters, sort fields, filter fields and duplicate filters return controlled 422s.
Allowlisted fields appear in the collection endpoint's parameter descriptions and the
API guide. A feature must additionally validate filter value types before querying its
database. Timestamps require timezone offsets and serialize as ISO 8601; missing carbon
measurements are null. Public plot DTOs omit manager/reviewer identities and private fields.

Manager endpoints accept a session cookie or signed Bearer token. Cookie-authenticated
mutations also require `X-CSRF-Token`; login requires CSRF even before a session exists.
Get an initial/fresh token through `/api/v1/auth/csrf`. Role and scope flags are never
accepted as trusted client input. Swagger's Authorize dialog exposes the auth schemes.

To review a deliberate contract change:

```powershell
uv run python -m scripts.export_openapi
git diff -- contracts/openapi.json
uv run pytest tests/test_contract.py -q
```

Share the committed JSON/diff with the frontend team before merging incompatible changes.
CI compares the generated schema with this document and uploads `openapi-contract` as an
artifact. Regenerating the document without reviewing the diff defeats the check.
