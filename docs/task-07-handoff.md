# Handoff Task 06 → Task 07

Status as of 18 November 2026: the backend foundation needed for **Task 07
development** is implemented and covered by local integration tests. Task 01 was
explicitly excluded from this consolidation. This document does not assert that
Task 07 endpoints, production deployment or independent scientific review exist.

## Setup and verification

Start from the merged Task 06 commit on `main`, or the exact Task 06 branch commit
if integration has not happened yet. Do not start from the old Task 05 baseline.

```powershell
uv sync
docker compose up -d db minio
uv run alembic upgrade head
uv run python -m scripts.check_migrations
uv run python -m scripts.export_openapi --check
```

The migration head is `0004_manager_notices`. The application's migration is an
explicit local setup step; automated tests run migrations in isolated test schemas.
Use a dedicated database and set `TEST_DATABASE_URL` before integration testing.
Set the `TEST_S3_*` variables described in [photos.md](photos.md) for real MinIO tests.

```powershell
uv run pytest -q
uv run ruff check .
uv run mypy app
```

## Contracts the next team can use

| Need | Existing component | Required use |
| --- | --- | --- |
| Manager authentication and CSRF | `require_manager` in `app/api/deps.py` | Use explicitly on every private route. |
| Visitor/Manager public access | `optional_user` | Use explicitly on public routes; never trust a request role. |
| Current field CRUD and version conflicts | Task 05 routers/service | Writes require row versions; coordinate/geometry synchronization is fixed. |
| Calculation, review and publication | `app/api/v1/calculation_runs.py` | Create draft, inspect it, approve to a new ID, then publish the approved ID. |
| Public plot and tree metadata | `published_inventory(session, plot_id)` | Returns an allowlisted published snapshot; never use live draft measurements as fallback. |
| List/legend/count eligibility | `published_candidates()` | Reuse the same candidate query and applied filters across these outputs. |
| Manager/internal pointer resolution | `published_run(session, plot_id)` | Apply the consuming feature's authorization; raw snapshots contain private metadata. |
| Scientific numerical baseline | `tests/fixtures/calculation_benchmarks.json` | CI needs no raw workbook. Exact CO2e ratio remains 44/12. |

`published_inventory` returns a `PublishedInventory` with:

- `plot`: existing `PublicPlot` DTO with code, scope, coordinates, survey date,
  publication metadata, carbon stock and quality status.
- `zone_id`: zone identifier for filtering/grouping.
- `trees`: snapshot tree ID, scientific name, DBH and an allowlisted photo ID or null.

The lookup returns the same hidden-resource 404 for unpublished, nonexistent,
archived and out-of-scope plots. It rechecks both current plot scope and published
snapshot coordinates against the current approved boundary. Old schema-only run
fixtures without a valid snapshot are not public data.

Publication increments plot `row_version`. Fetch the plot again before another
write. Editing a draft does not replace the publication pointer. A changed draft
code, species measurement or coordinate is not automatically public; public values
come from the published snapshot while current scope remains eligible.

## Reusable development fixtures

`tests/test_calculation_runs.py` provides the `field` fixture and helpers
`calculate`, `approve`, `publish`, and `sediment`. These create test-only records
in the rollback-isolated PostGIS schema supplied by
`tests/test_task02_database.py`. The `api` fixture in `tests/test_field_data.py`
provides an authenticated Manager test client. Import the dependent fixtures as
shown in `tests/test_published_inventory.py` when extending integration tests.

Use these scenarios for new Task 07 endpoints:

1. Complete single-core plot: `sediment(field)`, calculate with depth 10, approve,
   publish. Expect all carbon components and `quality_status=complete`.
2. Biomass-only: calculate/approve/publish without sediment. Expect incomplete,
   with SOC, ecosystem total and ecosystem CO2e null.
3. Unpublished plot: create the field fixture without publishing. Public response
   must match a nonexistent plot's 404.
4. Edit tree/plot after publication: public values remain from the old snapshot.
5. Archive plot or revoke boundary approval: public access is hidden.
6. Public versus private photo: IDs are allowlisted only when both snapshot and
   current attachment visibility are public. Missing/private photo returns null.

These fixtures are test-only; do not copy their field/approval labels into the
application database as a shortcut to a real approved inventory.

## Task 07 work and decisions

Implement `/public/plots`, `/public/plots/{id}`, `/public/map/plots`, `/map/layers`
and dashboard contracts according to BACKLOG. Existing planned HTTP handlers still
return 501 until replaced by Task 07; this is expected.

For summaries, use eligible complete published records with the same method version
and area-weighted aggregation. Biomass-only is explicitly incomplete and must not
be included as a complete ecosystem stock or silently contribute zero SOC. Expose
the valid/target coverage denominator; an unknown target remains unavailable.
Do not invent required core counts or official sampling depths.

Public photo delivery is Task 07 work: resolve only an allowlisted snapshot photo
ID through the publication/scope policy, then deliver a short-lived authorized
response. Manager download URLs require Manager authentication and cannot be reused
as visitor URLs. Never return an object key or raw private MinIO URL.

D7 imagery provider remains unconfigured. Show an unavailable/fallback state with
attribution rather than claiming a live Sentinel-2 layer. Provider choice is Task 07
configuration, not a missing Task 06 endpoint.

## Acceptance ownership and external data

- Task 03's full input/review/publish/report/chatbot acceptance is a cross-task
  integration check. Auth/boundary components and the publish hook are tested;
  report/chatbot checks belong to their implementing tasks.
- Task 04 numerical benchmark acceptance now follows the user's 18 November
  instruction: independent Decimal baseline plus supplied workbook tree samples.
  Independent scientific sign-off remains a separate assertion, never fabricated.
- Task 06 core calculation/review/publish and public projection are available.
  Remaining consumer acceptance is verified when Task 07/08/09/10 implement their
  outputs. Export-completion notices require the actual Task 08 export event.
- `realdata/Data/zona_vak.csv` contains candidate VAK polygons, but availability is
  not official study-area approval. Raw local files are not automatically imported
  or uploaded. The committed numerical fixture includes minimal source samples
  and SHA-256 for reproducibility without the full source workbook.
- The supplied workbook has no sediment benchmark or authoritative plot-area
  assignment for these tests. Benchmark areas/layers remain explicitly synthetic.

After the user merges this branch, Task 07 can proceed with these supported
contracts and fixtures. Real public inventory still requires approved field data,
method records and a study boundary supplied through the project's review process.
