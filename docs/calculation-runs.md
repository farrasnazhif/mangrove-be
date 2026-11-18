# Calculation runs and publication (Task 06)

The Task 06 implementation uses the existing Task 03 authorization/scope helpers
and Task 04 calculation engine. On 18 November 2026 the user authorized consolidating
Task 03/04/06 readiness fixes on this branch, excluding Task 01. Technical benchmark
acceptance now uses the supplied workbook and an independent Decimal baseline.
No scientific approvals or official boundaries are created by this implementation.

## API workflow

All endpoints below require Manager authentication. Cookie-authenticated writes
also require the existing session-bound CSRF token.

1. Fetch `GET /api/v1/plots/{plot_id}` and note its current `row_version`.
2. POST `/api/v1/plots/{plot_id}/calculation-runs` with:

   ```json
   {
     "method_version_id": "UUID-OF-AN-EXISTING-METHOD",
     "input_revision": 2,
     "expected_bottom_cm": 20
   }
   ```

   Replace the example revision and depth with the current plot revision and the
   sampling protocol's target depth. Depth is optional; omitting it prevents a
   complete sediment claim. It must not be inferred from the deepest measured layer.
   A stale revision returns 409. Unknown methods and invalid depth return 422.
3. Inspect the draft through GET
   `/api/v1/plots/{plot_id}/calculation-runs/{run_id}`. The detail includes the
   input snapshot, full-precision results, per-tree/layer intermediates and QA flags.
4. After reviewing the data, POST
   `/api/v1/plots/{plot_id}/calculation-runs/{run_id}/approve` with
   `{"row_version": 2}` using the actual current revision. This returns a **new
   approved run ID** (201); the source draft remains immutable. An audit event links
   the approved run to its source draft and the reviewing Manager.
5. POST `/api/v1/plots/{plot_id}/publish` with:

   ```json
   {
     "calculation_run_id": "UUID-OF-THE-APPROVED-COPY",
     "row_version": 2
   }
   ```

   Publication replaces the plot's current pointer atomically with its audit event.
   It increments the plot's `row_version`; fetch the plot again before another write.
   The response identifies the published run and method, timestamp and whether it
   is incomplete. It does not change the plot's spatial draft/quarantine status.

Creating a run does not approve it. Approval and publication require an approved,
effective **field** method, a non-synthetic approved study boundary, in-scope field
inputs, and the current input revision. Pending methods and synthetic seed data
remain usable for draft demonstrations, with explicit flags, but cannot be approved
or published. Scope and boundary revision are checked again at publication.

## Snapshots, revisions and replay

The input snapshot records plot revision, survey metadata, active trees, species
metadata, active cores/layers, density provenance, original method coefficients,
target depth, photo IDs/visibility, and boundary geometry/source/revision. Its SHA-256 uses canonical JSON
(sorted keys, compact separators, non-finite numbers rejected). Repeated calculation
with the same snapshot yields the same hash and numerical results.

Field writes and calculations serialize on the same plot row lock. Shared boundary
and species locks stabilize their metadata while the snapshot is captured. Archived
trees, cores and layers are excluded. Layers from archived cores are also excluded.
No species default density is substituted for a missing recorded tree density.

Results retain the engine's full float precision; there is no invented rounding rule.
Replay uses the snapshot's own method and inputs, never the latest method/data.
Approval copies the snapshot/results without updating any immutable row.

Editing inputs after publication leaves the published run untouched. New drafts
can coexist with that publication. Publishing a stale run is rejected, while the
existing published snapshot remains readable. The shared service helper
`published_run(session, plot_id)` resolves **only** `publications.published_run_id`.
Public consumers should use `published_inventory(session, plot_id)` in
`app/services/published_inventory.py`: it applies scope/archival/publication checks
and returns an allowlisted snapshot projection. `published_candidates()` supplies
the same base eligibility query for public lists/legends/counts. Public photo IDs
require both captured and current public visibility; this does not make private
MinIO objects publicly readable. Task 07 must implement authorized public photo
delivery separately. See [Task 07 handoff](task-07-handoff.md).

## Quality notices and incomplete publication

GET `/api/v1/plots/{plot_id}/notices` lists durable Manager notices. Pagination
defaults to 25, caps at 100, allows sorting by `created_at`/`flag`, and supports
`filter=flag:missing-density`. Each notice records its originating run, plot code,
flag and suggested action. A run, its notices and its audit event commit or roll
back together. Notices are historical evidence for their originating run; creating
a corrected run does not delete old notices.

Missing density, missing/incomplete sediment, absent target depth, synthetic inputs,
pending methods and out-of-scope plots produce flags. Multiple active cores produce
`multi-core-policy-required`; their layers are not combined or summed as plot SOC.
No missing stock is replaced by zero.

D5 permits biomass-only publication when the plot has **no active sediment cores**
and its tree inventory is calculable. Such runs retain sediment flags, are explicitly
`incomplete=true`, and keep SOC, ecosystem total and ecosystem CO2e null. A partially
measured core or unresolved multi-core dataset cannot be published as complete or
silently reduced to biomass-only. Other quality flags block approval/publication.

## Verification and remaining acceptance

Run with an explicit PostGIS test URL:

```powershell
uv run pytest tests/test_calculation_runs.py tests/test_calculation_concurrency.py tests/test_calculation_access.py -q
```

Tests use isolated schemas/fixtures, not application data. Test-only field labels
and approvals exercise policy branches; they are not real scientific acceptance.
Coverage includes deterministic hashes/replay, complete and biomass-only publication,
immutable reviewed copies, stale/foreign runs, rollback of notices/audit, boundary
changes, archived inputs and real concurrent calculation versus input editing.
The existing route audit tests cover every new endpoint's Manager access policy.

Remaining acceptance:

- Independent scientific sign-off remains separate from development acceptance.
  User-authorized technical golden fixtures and tolerances are now committed; see
  [Calculation guide](calculations.md). They do not approve real methods/inventory.
- Task 03 integration into chatbot and the full review/publish/report workflow.
- Required core count, multi-core aggregation, protocol target depth and project
  display-rounding decisions. No defaults are invented for these research inputs.
- Dashboard/map/export/chatbot integration with the shared published pointer in
  their later tasks. Those endpoints are not implemented by Task 06.
- Export-completion notices when Task 08 supplies an actual export-completion event.

Migration `0004_manager_notices` adds the notice table. Tests exercise upgrades and
downgrades in isolated schemas; applying migrations to the application's database
is a separate operational step.
