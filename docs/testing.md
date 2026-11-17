# Testing

Run commands from the repository root after installing dependencies with `uv sync`.
The examples use PowerShell. They cover the foundation, database model, authentication,
and spatial boundary checks implemented in Tasks 01–03.

## Automated checks

Run checks that do not require a database:

```powershell
uv run pytest -q -m "not integration"
uv run ruff check .
uv run mypy app
uv run python -m scripts.check_migrations
uv run python -m scripts.export_openapi --check
```

All commands should succeed. The migration graph must have exactly one head, and
the generated OpenAPI document must match the reviewed contract. When changing an
API contract intentionally, regenerate it with `uv run python -m scripts.export_openapi`
and review the resulting diff with the frontend team.

## PostGIS integration tests

Start Docker Desktop and the database:

```powershell
docker compose up -d db
docker compose ps
```

Create a dedicated test database once; skip this command if it already exists:

```powershell
docker compose exec db createdb -U mangrove mangrove_test
```

Set the test URL explicitly and run the full suite:

```powershell
$env:TEST_DATABASE_URL = 'postgresql+asyncpg://mangrove:mangrove@127.0.0.1:5432/mangrove_test'
uv run pytest -q
Remove-Item Env:TEST_DATABASE_URL
```

Compose defaults to host port 5432. If your `.env` sets `POSTGRES_PORT=5433`, use
5433 in the URL above. The PostgreSQL port inside the container remains 5432.

To run database checks separately, set `TEST_DATABASE_URL` and use:

```powershell
uv run pytest -q -m integration
uv run pytest tests/test_task02_database.py -v
```

Integration tests never fall back to the application's `DATABASE_URL`. Without
`TEST_DATABASE_URL`, they are skipped. A complete verification run should include
the integration tests without skips.

Tests create temporary schemas inside transactions and roll them back. The audit
permission test also creates a temporary NOLOGIN role, then rolls it back. Use a
test database user with permission to create schemas, CREATE ROLE, and SET ROLE;
the Compose/CI PostgreSQL user supports this. Required extensions are PostGIS and
btree_gist; the migration enables them if permitted. The runtime application user
does not need schema/role administration privileges or permission to disable triggers.

### Coverage

| Area | Checks |
| --- | --- |
| Migrations | Upgrade from the previous migration with an existing user, clean upgrade, downgrade to base, single migration head, ORM/schema consistency. |
| Plots and trees | Unique and well-formed plot codes, positive area/DBH/height/version, coordinate and density bounds, foreign keys, nullable photo links. |
| Sediment | Valid depth ranges, positive mass/volume, LOI bounds, rejection of overlapping layers in one core, acceptance of adjacent intervals and independent cores. |
| Attachments and imports | Private visibility by default, valid photo references, unique file/revision and batch/row provenance, protection against deleting referenced attachments/import batches. |
| Methods and runs | Rejection of UPDATE/DELETE/TRUNCATE; approved runs require approved methods. |
| Publications | One current pointer per plot; only an approved run belonging to the same plot is accepted; input edits and pointer replacement preserve old runs. |
| Audit | Append-only history, including under an application role with DML permissions; rejection of nested credential keys, including within arrays. |
| Authentication | Server-derived roles, CSRF, invalid/expired sessions, logout and session revocation, explicit route access dependencies. |
| Seed and scope | Idempotent seed, preserved passwords, synthetic labels, ST_Covers inside/outside/edge checks, quarantine, exclusion of synthetic data from official inventory. |

Scientific golden results and the complete input → calculation → review/publish →
report workflow require the corresponding feature implementations. Schema tests do
not establish the correctness of carbon equations or implement those API routes.

Task 05 tests in `tests/test_field_data.py` cover audited CRUD, rollback, scope,
pagination, stale versions, sediment overlap, archival and published snapshots.
`tests/test_field_concurrency.py` uses two independent database transactions: the
first edit commits and the stale writer returns 409. It commits fixtures in a
UUID-named test schema and removes that schema afterward; use a dedicated test
database. Authorization tests include all new endpoints. Image safety tests in
`tests/test_photos.py` verify metadata stripping, MIME/content checks, animation,
size/pixel limits and signed link expiry/user/session binding. Photo API tests in
`tests/test_photo_api.py` cover transactional cleanup, CSRF, tree links, authenticated
downloads and real MinIO anonymous denial. See [Field data](field-data.md) and
[Photo setup/testing](photos.md). CI starts MinIO and supplies the explicit test
storage variables so the real storage round trip runs alongside PostGIS.

Task 04 now has local equation and replay checks in `tests/test_calc.py`; see the
[calculation guide](calculations.md). These checks do not replace the missing
reviewer-signed golden fixture or exercise Task 06 calculation-run/publication APIs.

## Development migrations and seed

Configure the local application's `DATABASE_URL` in `.env`, then run:

```powershell
uv run python -m scripts.check_migrations
uv run alembic upgrade head
uv run alembic current
uv run python -m app.db.seed
uv run python -m app.db.seed
```

The current revision should be `0003_active_layer_intervals (head)`. Existing user IDs
must be valid UUID strings before this migration converts their database type.
Invalid legacy IDs cause a transactional migration failure rather than identity replacement.
Downgrades remove tables/columns and their data; exercise them only on test databases.

Seeding is allowed only in development/test with an unapproved synthetic boundary.
The default manager email is `manager.synthetic@example.test`; change it through
`SEED_MANAGER_EMAIL`. Enter a password containing 12–72 UTF-8 bytes at the hidden
prompt, or supply `SEED_MANAGER_PASSWORD` for automation. Rerunning the seed preserves
the original password, sessions, and existing records. Changes to the stored boundary
source, revision, or geometry are rejected rather than silently overwritten.

On a fresh development database, both seed runs should leave one zone, one manager,
one species, three plots, six trees, three cores, six layers, and one method, all
labelled synthetic. Existing unrelated data is preserved.

```powershell
docker compose exec db psql -U mangrove -d mangrove -c "SELECT code, status, scope_reason, data_label FROM plots ORDER BY code;"
docker compose exec db psql -U mangrove -d mangrove -c "SELECT name, approved_scope, boundary_is_synthetic, boundary_source, boundary_revision, ST_SRID(boundary_geom) AS srid FROM zones;"
docker compose exec db psql -U mangrove -d mangrove -c "SELECT version, approval_status, data_label FROM method_versions;"
```

| Seed plot | Location | Status | Scope reason |
| --- | --- | --- | --- |
| VAK-9001 | Inside the box | draft | null |
| VAK-9002 | On the edge | draft | null |
| VAK-9003 | Outside the box | quarantine | outside-study-area |

The zone is unapproved and synthetic, with SRID 4326. The method remains
`pending-scientific-approval`. Seed measurements and dates are synthetic examples;
no publication or official carbon stock claim is created.

## Manual API checks

Start the development API in one terminal:

```powershell
uv run uvicorn app.main:app --reload --port 8080 --no-access-log --log-config logging.json
```

In another terminal, run:

```powershell
uv run python scripts/verify_task01.py
uv run python scripts/verify_task03.py
```

Keep both scripts for checks against a running server. Automated unit tests use
an in-process client; these scripts also verify the locally running API.

The foundation script performs GET requests without database writes or credentials.
It checks request IDs, error envelopes, access rejection, pagination limits,
sort/filter allowlists, documentation, and the OpenAPI snapshot. Planned routes
currently return 501 after access/input validation.

The authentication script prompts for the seed manager password. Use `--email`
if you changed the email. It checks anonymous access, forged roles, CSRF rejection,
successful login, HttpOnly cookies, both `/me` routes, logout, cookie removal, and
rejection of an old session token. Logout revokes all sessions for that manager,
including sessions in other browser tabs. Expect every check to report PASS.

For frontend login, fetch `GET /api/v1/auth/csrf` with cookies and send the returned
token in the `X-CSRF-Token` header on login. Login returns a new session-bound CSRF
token for subsequent mutations. Fetch a new token when it expires; requests must
include cookies. In Swagger, set CSRFToken through the Authorize dialog and update
it with the new token returned by login.

API errors use `{code, message, details, request_id}`. The response `X-Request-ID`
must match the body and JSON request log. Logs should not expose credentials,
cookies, authorization headers, query strings, or request bodies.

## Database rules for feature development

- Methods and calculation runs are immutable from insertion, including pending/draft
  records. Approval changes create new method versions or runs. Preserve coefficients,
  references, effective dates, rounding rules, input revisions, snapshots, and QA flags.
- Run hashes must be lowercase SHA-256 strings of 64 characters. The calculation
  service must compute and verify the hash against the input snapshot; the database
  validates its format only. Store full-precision results before output rounding.
- Publication pointers enforce matching plot ownership and approved run status.
  Publication services must additionally enforce scope and completeness requirements,
  including the approved policy for incomplete biomass-only results.
- Attachment `entity_type/entity_id` references are polymorphic and require service
  validation. The tree's optional `photo_id` has a database foreign key. Upload
  services must validate file content/MIME/size and control public access.
- Audit JSON rejects credential keys at every nesting level. Audit services must
  still allowlist changed fields and exclude credentials from values and free text.
- Use `ST_Covers(zone.boundary_geom, plot.geom)` for scope; edge/corner points are
  inside. Coordinate order is longitude, latitude (EPSG:4326). Creation/import must
  use `assign_plot_scope`, publication must use `require_publishable_scope`, and
  inventory retrieval must use `inventory_scope_predicate` plus access/publication checks.
- Every new route needs explicit access dependencies and authorization tests.
  Replace planned handlers without registering duplicate method/path pairs; maintain
  public DTOs, error envelopes, and validated pagination allowlists.

## Production image smoke test

```powershell
docker build -t mangrove-be:local .
uv run python scripts/smoke_image.py mangrove-be:local
```

The smoke script runs the same image in staging and production modes using different
environment settings. It creates temporary containers on random localhost ports and
removes them afterward. It checks health, error envelopes, CORS rejection, pagination,
request IDs, JSON logs, and non-root execution with a read-only filesystem and no
capabilities. It does not require a live database or production credentials. Real
database authentication and migrations are checked by the PostGIS tests above.

Use `config/staging.env.example` and `config/production.env.example` as templates.
Staging/production require secure cookies, HTTPS deployment, and a strong JWT secret
of at least 32 bytes. Run migrations as a separate release step; the web process
does not create/reset tables at startup. Hosting, TLS, and external deployment checks
must be verified on the actual infrastructure.

## CI and merge checks

[Backend CI](../.github/workflows/backend-ci.yml) runs lint, types, a migration round
trip on an isolated CI database, PostGIS tests, the OpenAPI check, and production image
build/smoke checks. Require the **Backend required** status check for merges into main.
Verify the actual repository ruleset/branch protection separately: a workflow file
alone does not prevent a merge. [branch-protection.json](branch-protection.json) is a
proposed minimal configuration; preserve any existing repository policies when applying it.
