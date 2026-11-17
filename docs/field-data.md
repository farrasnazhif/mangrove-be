# Field data APIs (Task 05)

Implemented on 17 November 2026. All routes below require Manager access; cookie
mutations also require session-bound CSRF. All paths start with `/api/v1`.

| Resource | Collection | Operations |
| --- | --- | --- |
| Plots | `/plots` | GET list, POST create; GET/PATCH `/plots/{plot_id}` |
| Trees | `/plots/{plot_id}/trees` | GET list, POST create; PATCH/DELETE `/{tree_id}` |
| Cores | `/plots/{plot_id}/cores` | GET list, POST create; PATCH/DELETE `/{core_id}` |
| Layers | `/cores/{core_id}/layers` | GET list, POST create; PATCH/DELETE `/{layer_id}` |

Lists use `{items, page, page_size, total}` and exclude archived records. A missing
or archived parent/child, including a child under the wrong parent, returns 404.
Plot lists support `code`, `zone_id`, `status` filters and `code`, `survey_date`,
`area_m2` sorting. Tree lists support `species_id`, `qa_status` filters and `id`,
`dbh_cm` sorting. Core/layer lists sort by `id`. All collections use a stable ID
tie-breaker. UUID filters are validated before database queries.

PATCH bodies require the current `row_version` plus at least one changed field.
Core/layer responses now include `row_version`. Tree density, source, optional
height and photo can be cleared with null; required fields cannot be cleared.
A supplied density requires a source (maximum 200 characters). An unrecorded
density stays null; its non-null database source is explicitly `not-recorded`.
No scientific measurements are filled from defaults. Tree species must exist.
Existing photo links are restricted to image attachments belonging to the selected
plot. The [photo guide](photos.md) describes uploading and linking a new photo.

DELETE requires `?row_version=<current>&confirm=true`. It sets `archived_at`,
increments the version and records an audit event. Archived cores hide their layers
from APIs. No physical deletion occurs, and imports, calculation runs and published
snapshots remain intact. Migration `0003_active_layer_intervals` limits the sediment
overlap constraint to active layers, allowing an archived interval to be replaced.
Downgrade fails transactionally if archived replacements overlap; it never removes
history to satisfy the previous constraint.

Mutations lock the plot before locking cores/children, then check versions. Stale
edits/deletes return 409 `version_conflict`. Every child write/archive advances the
plot's `row_version`, including audit entries for the child and plot revision.
An existing calculation run is stale when its `input_revision` differs from the
plot version. Task 06 must enforce that comparison before using a draft for a new
publication. This module never mutates historical runs or existing publication
pointers; public consumers continue to use the saved publication snapshot.

Each mutation and its audit rows share one transaction, committed before the
response is sent. Any failure rolls both back. Audit events record actor, entity,
action and allowlisted changed fields with before/after values; credentials and
unrelated attributes are excluded. Duplicate plot/sample codes return 409 with
field details; overlapping active sediment intervals return 422 with depth details.
Partial layer edits are validated against the complete merged interval.

Plot geometry and quarantine are derived from the stored zone using `ST_Covers`.
New plots are labelled `field`; clients cannot supply trusted scope/status flags.
Real measurements in an unapproved/synthetic zone remain quarantined, including
when coordinates lie inside it. Plots outside the zone are also quarantined.

Photo upload, EXIF/GPS stripping, private object access and short-lived signed API
URLs are implemented. See [photo guide](photos.md) for storage setup and Swagger
testing. Photo upload also advances the plot revision and writes an audit event.

Run `uv run alembic upgrade head` before using these routes. Set the dedicated
`TEST_DATABASE_URL`, then run `uv run pytest -q` to include PostGIS/API/concurrency
acceptance. The tests do not apply migrations to the application's database.
