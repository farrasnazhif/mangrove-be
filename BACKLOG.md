# Backend Backlog (work order)

Source: [PRD.md](PRD.md) v1.4. `Refs` are PRD IDs (FR = functional, TR = technical, AT/TT = acceptance/technical tests).
Priority `P0` / `P1` follows the PRD. The starter scaffold is already done (FastAPI app, config, DB session, health route, compose with PostGIS).

12 issues, numbered in work order. Titles use the format `[Topic] Title`; the topic only labels the area.
`depends:` lists issue numbers that must be closed first. Issues in the same step can be done in parallel.

## Working rules

- **One task = one issue = one branch.** An issue holds several pieces of work: they are the **Tasks** checklist inside it, all done on the same branch and PR.
- **Branch from `main`**, named as the issue's `branch:` line. Open a draft PR early; the PR description starts with `Closes #<issue number>`. The PR is done when every Task and every Done-when box is ticked. Rebase on `main` often; delete the branch after merge.
- **Take any issue whose dependencies are all closed.** Anything else is off limits, even if it looks easy.
- **Assign yourself before starting.** One person per issue.
- **Migrations:** merge one migration PR at a time; CI fails if Alembic has more than one head.
- **Small commits.** `router.py`, `main.py` and `models/__init__.py` are shared; keep edits there minimal.
- **`needs decision:`** means a decision marked open in the table above must be answered first. The note says which Tasks wait; do the others meanwhile and do not work around the blocked ones with a stand-in.

## Decisions

Answered ones are recorded so the team does not ask again. Open ones unblock the most work; answer them early.

| ID  | Decision | Status | Needed by issues |
| --- | -------- | ------ | ---------------- |
| D1  | Scientific method (equations, coefficients, %C = LOI ÷ 1.724) | **Answered: approved as written in PRD §6.** Still open: the reviewer's benchmark fixture (expected results) for golden tests. | 4 |
| D2  | Boundary of the study area; VAK plot count | **Answered: no boundary file and no coordinates available.** The study-area box (min/max latitude and longitude) is a config value stored in `zones.boundary_geom`. Until a real box is set, seed and tests use a clearly labelled synthetic box and publishing real plots is blocked with a clear error. Plot count unknown, not needed. | 3 |
| D3  | Auth provider and roles | **Answered: build login ourselves.** Roles assumed Manager only (PRD allows Admin to be merged with Manager for MVP). | 3 |
| D4  | Hosting, object storage, backups | **Open.** Not configured yet. | 5, 11 |
| D5  | Area-weighted multi-plot average; publish a plot without sediment (biomass-only) | **Answered: area-weighted average; a plot without sediment data may be published biomass-only**, labelled as incomplete (no SOC, no ecosystem total). Still open, small: cores per plot, rounding, "valid plot" definition. | 6, 7 |
| D6  | LLM provider; approved general-reference sources | **Answered: OpenAI.** Still open: approved public sources and freshness, out-of-Surabaya wording, cost limit. | 9, 10 |
| D7  | Map imagery provider; public coordinates and photos | **Answered: public may see coordinates and photos.** Still open: imagery provider (not configured yet). | 7 |
| D8  | Visitor export | **Answered: no visitor export (manager-only).** Retention and link expiry: our default (short-lived signed links). | 8 |

## Step 1 (start here, no dependencies)

### 01. [Foundation] Alembic, CI, Docker image, API conventions and OpenAPI contract

labels: P0, area:ops, type:chore
depends: none
Refs: TR-02, TR-05, TR-16, TR-17, TR-20, §9.4, §9.7, §9.9 "required before coding"

**Tasks**

- Init Alembic, wire it to `Base.metadata` and `DATABASE_URL`; first migration enables `postgis` and `btree_gist`.
- GitHub Actions with a PostGIS service: ruff, mypy, pytest, `alembic upgrade head` on an empty DB; fail when Alembic has more than one head.
- Production Dockerfile; separate dev/staging/prod settings; secrets only from env or a secret manager; keep `.env.example` current.
- Middleware adds `request_id`; all errors return `{code, message, details, request_id}`; JSON logs with the request ID and no secrets; private resources never reveal that a hidden record exists.
- Shared pagination dependency (P1): default page size 25, hard max 100, explicit allowlist of sort/filter fields, ISO 8601 timestamps.
- Typed request/response schemas for every P0 route in §9.4 before they are implemented, plus contract tests that fail on schema drift; share with the frontend team.

**Done when**

- `alembic upgrade head` works on a clean DB and `alembic downgrade base` reverses it.
- PRs are blocked on a red pipeline, including a second Alembic head.
- The same image runs in staging with only env differences.
- 404/403 for a hidden record are indistinguishable; 422s return field-level details; requests above pagination limits return a controlled 4xx.
- `/docs` lists every P0 route with schemas; the contract test runs in CI.

## Step 2

### 02. [Data Model] Database schema: all migrations

labels: P0, area:db, type:feature
depends: 01
Refs: FR-09, FR-10, FR-11, FR-12, FR-18, FR-36, TR-05, TR-06, TR-07, TR-09, TR-10, TR-16, TR-23, TR-26, §9.3

**Tasks**

- Zones, plots, species: `plots.code` CHECK `^VAK-[0-9]+$` and UNIQUE; `area_m2 > 0`; lat/lon range; `geom` SRID 4326 with GiST index; `row_version`; `zones.boundary_geom` and `approved_scope`; UUID primary keys.
- Trees and attachments: `dbh_cm > 0`, density range check, `qa_status`, `source_import_id` / `source_row_id`, `row_version`; `attachments` with `object_key`, `mime_type`, `visibility` (private by default).
- Sediment cores and layers: `depth_bottom_cm > depth_top_cm >= 0`, mass and volume > 0, exclusion constraint (`btree_gist` + `numrange`) so intervals cannot overlap within a core.
- `method_versions` and `calculation_runs`, immutable (trigger or revoked UPDATE/DELETE); `publications` with exactly one `published_run_id` per plot, the run must belong to that plot and be approved.
- `users`; append-only `audit_events` with no passwords or tokens; `dbh_import_batches` recording Drive file ID, revision, importer, status.

**Done when**

- Duplicate or malformed plot codes, orphan plots and orphan trees are rejected by the DB; the nullable photo link works.
- Overlapping layers in one core fail at the DB level.
- Updating a run or pointing a plot at another plot's run fails.
- Audit rows cannot be updated or deleted by the app role.

## Step 3

### 03. [Authentication and access] Seed data, boundary check, manager login and auth tests

labels: P0, area:auth, type:feature
depends: 01, 02
needs decision: the study-area box coordinates are not available; build with a synthetic box and a config value (see D2)
Refs: FR-01, FR-29, FR-33, FR-34, TR-03, TR-04, TR-06, TR-21, TT-01, TT-09, AT-01, AT-14, AT-17, §9.3, §9.6, §9.9, §12

**Tasks**

- Seed script: one zone with a placeholder polygon, one manager, a few `VAK-xx` plots with trees and sediment layers, one method version marked `pending-scientific-approval`. Everything labelled synthetic; do not copy mockup numbers as facts.
- Define the study area as a configurable bounding box (no official boundary file exists) stored in `zones.boundary_geom` with its source noted, and add a documented spatial predicate used by plot creation, publication and chatbot tools; out-of-scope plots go to quarantine and are never returned as Surabaya inventory.
- Login with hashed credentials, HttpOnly + Secure + SameSite session cookie, CSRF protection for state-changing calls, logout, `GET /api/v1/me` returning the server-derived role.
- Reusable dependencies `require_manager` (401/403) and `optional_user` (anonymous = visitor); every router uses one of them explicitly.
- Parametrized authorization tests: anonymous and modified-request attempts against every manager route return 401/403 with no private fields; re-run on every new route.

**Done when**

- The seed dataset can be entered, reviewed, published and reported end to end.
- Tests cover boundary points inside, outside and on the edge.
- Expired sessions cannot write; role never comes from the request body.
- No route exists without an explicit access dependency (checked by a test); the suite fails if a manager route becomes public.

### 04. [Scientific Calculation] Calculation module, method registry and golden tests

labels: P0, area:calc, type:feature
depends: 02 (the pure functions can start any time after step 1)
needs decision: D1 (golden tests need the reviewer's expected results; the method itself is approved)
branch: feat/calc-module
Refs: FR-13, FR-14, FR-15, FR-17, FR-18, TR-08, TR-09, TT-03, AT-02, AT-03, AT-06, §6, §6.1, §9.5

**Tasks**

- Pure functions in `app/calc/`, no DB or FastAPI imports. Tree: AGB `0.251·ρ·DBH^2.46`, BGB `0.199·ρ^0.899·DBH^2.22`, AGC `AGB·0.47`, BGC `BGB·0.39`, plot Mg C/ha from actual plot area.
- Sediment: BD = dry_mass / volume; %C = LOI / 1.724 (rule comes from the method version); layer SOC; profile total over non-overlapping layers; a missing layer flags the profile incomplete.
- Total = AGC + BGC + SOC counted exactly once; CO₂e = total × 44/12. Incomplete records are flagged and excluded from official totals; never substitute 0 for missing. The multi-plot summary rule is decision D5 and must be labelled in output.
- Method registry: methods stored as data (`coefficients_json`, references, approval status, effective date, rounding rule); changing a coefficient creates a new version.
- Golden tests from the reviewer's fixture: a 10×10 m plot with multiple trees and sediment layers; edge cases for zero/negative inputs, bounds, missing density, overlapping depths, varying plot size, kg C vs Mg C/ha.

**Done when**

- Identical inputs and method give identical full-precision output; rounding only at output; units are g/cm³, %, Mg C/ha as in the PRD.
- A plot with missing density or sediment returns a flag, not a zero.
- Recalculating an old run with its original method version reproduces its stored result.
- Each intermediate value matches the reviewer's fixture within the approved tolerance.

## Step 4

### 05. [Field Data CRUD] Audit service, plots, trees, sediment and photo upload APIs

labels: P0, area:api, type:feature
depends: 01, 02, 03
needs decision: D4 (photo upload Task)
branch: feat/field-data-api
Refs: FR-09, FR-10, FR-11, FR-12, FR-38, TR-07, TR-12, TR-16, AT-04, §9.3 mutation rules, §9.4, §9.6

**Tasks**

- Audit service: writes an `audit_events` row inside the same transaction as the change (actor, entity, action, changed fields); used by every write endpoint.
- Plots: `GET/POST /plots`, `PATCH /plots/{id}` (requires `row_version`; stale version returns 409); validate required fields, unique code, coordinates and scope flag.
- Trees: list (paginated, filterable), create, edit, delete under a plot; saving invalidates or recalculates affected draft results.
- Sediment: `POST /plots/{id}/cores`, `POST /cores/{id}/layers`, plus list/edit/delete; depth as top/bottom in cm; mass and volume validated.
- Safe deletion: referenced records are archived (soft delete); destructive actions need an explicit confirm parameter and write an audit event; published revisions and provenance are never deleted.
- Photo upload: MinIO locally, S3-compatible in prod; validate MIME and size; strip EXIF/GPS for public photos; serve through time-limited signed URLs after authorization.

**Done when**

- A rolled-back write leaves no audit row; a committed write always has one.
- Field-specific validation errors; two simultaneous edits cannot silently overwrite each other.
- Species, DBH, density, optional height and photo link persist against the selected plot; overlapping or non-positive sediment values return field-level errors.
- Deleting a tree in a published plot leaves the last published snapshot intact.
- An unauthenticated request to an object URL is blocked and URLs expire.

## Step 5

### 06. [Scientific Calculation] Calculation runs, quality flags and publish endpoint

labels: P0, area:api, type:feature
depends: 03, 04, 05
needs decision: none blocking (D5 answered; cores per plot and rounding still open)
branch: feat/calc-runs-publish
Refs: FR-04, TR-09, TR-10, AT-06, AT-10, §3.2, §9.4

**Tasks**

- `POST /api/v1/plots/{plot_id}/calculation-runs` runs a given method version on an identified input revision and stores an immutable run with `input_hash`, full-precision `result_json`, QA flags and timestamp.
- P1: emit manager notices for missing density, incomplete sediment profile, out-of-scope coordinates and export completion, each naming the plot and the issue.
- `POST /plots/{id}/publish` publishes an approved `calculation_run_id` (complete, or biomass-only and labelled as incomplete) in one transaction and writes an audit event.

**Done when**

- Editing inputs does not alter an existing run; a new draft run can exist while the published run stays visible.
- A notice is created for each flag type with plot code and action.
- Dashboard, map, export and chatbot all read the same `published_run_id`; a revision after publication does not overwrite the published snapshot.

## Step 6

### 07. [Publication and Public API] Public plot, map and dashboard endpoints

labels: P0, area:api, type:feature
depends: 06
needs decision: D7 (imagery provider; map Task)
branch: feat/public-api
Refs: FR-05, FR-06, FR-07, FR-20, FR-21, FR-22, FR-33, FR-37, FR-38, TR-11, TR-22, TR-24, TR-25, AT-20, AT-21, §6 (coverage), §9.4

**Tasks**

- `GET /public/plots` and `/public/plots/{id}` return published data only through a dedicated public schema; missing values return null or an explicit unavailable state, never 0.
- `GET /public/map/plots` (VAK, coordinates, species, DBH, allowlisted photo link, last survey date) and `GET /map/layers` (available basemaps, imagery date, attribution, fallback status); do not promise a live Sentinel-2 layer until a provider is confirmed.
- P1: filter markers by zone, status and carbon range.
- Dashboard summary: average stock (Mg C/ha), CO₂e (Mg CO₂e/ha), plot coverage as valid/target with the denominator exposed, dominant species, selected-plot breakdown (AGC/BGC/SOC, ~100% after rounding); manager and public variants.

**Done when**

- No draft values, researcher names or reviewer metadata appear; an unpublished plot returns the same response as a nonexistent one.
- Marker-to-tree joins are tested including missing DBH and missing photo; marker list and legend data return the same filtered subset.
- Dashboard values derive from eligible records only and match the plot detail; empty state returned when there is no data.

### 08. [Reports and DBH Import] XLSX export and Drive DBH import

labels: P0, area:reports, type:feature
depends: 03, 05, 06
needs decision: verified Drive file, access and row schema (DBH import Task)
branch: feat/reports-import
Refs: FR-08, FR-16, FR-19, FR-26, FR-27, FR-39, TR-12, TR-13, TR-19, TR-26, AT-07, AT-22, TT-11, §4.9, §7.2, §7.3, §9.7

**Tasks**

- `POST /reports/exports`: sheets 00_Petunjuk through 07_Rekap_DBH built with openpyxl from one consistent DB snapshot; numeric cells stay numeric; frozen headers and filters; units, method version, data revision and timestamp recorded; drafts only if "include drafts" is set.
- `GET /reports/exports/{id}` returns status and a time-limited download link; start synchronous (target ≤ 30 s for 10,000 tree rows) and queue only if measurements require it.
- P1: filtered and per-page exports keep the applied filters and include the formula version; no visitor export (D8: manager-only).
- `POST /dbh-imports`: manager supplies the exact Drive file ID; rows are validated and reviewed before any field data is updated; idempotent against original rows; out-of-scope or invalid rows are quarantined. The Drive file is an import source, not a live dependency.
- `GET /plots/{id}/dbh-recap`: per tree DBH → AGB/BGB (kg) → AGC/BGC (kg C), coefficients, wood-density source, method version, exception flags, unrounded intermediates; per-VAK totals; fill sheet `07_Rekap_DBH`.

**Done when**

- All sheets reconcile to the same source revision and totals; an exported subset equals the filtered view.
- Expired links stop working; a larger-than-threshold job does not block the request.
- Re-running the same import creates no duplicates; source file/revision/row IDs are stored.
- Recap totals reconcile with the calculation page and sheet `07_Rekap_DBH`.

## Step 7

### 09. [Langflow Chatbot] Langflow in compose, read-only inventory tools and reference source

labels: P0, area:chat, type:feature
depends: 01, 03, 06
needs decision: D6 (approved reference sources; reference source Task)
branch: feat/chat-infra
Refs: FR-24, FR-29, FR-30, FR-32, TR-31, TR-32, TR-35, AT-08, AT-11, AT-14, AT-15, AT-26, §8.4

**Tasks**

- Add Langflow to compose: pinned release, authentication on, no published port (internal network only), secrets via env.
- Narrow read-only endpoints (for example plot summary by VAK code) that enforce role, publication state and Surabaya scope before returning minimal facts with source IDs, method version and date. No SQL, no writes, no Langflow DB credentials.
- General reference source and index: approved public sources with provenance and freshness rules, isolated from internal inventory; if no reliable source exists, say so and never invent a citation.

**Done when**

- A request to Langflow from outside the Docker network is refused.
- A visitor-role call for an unpublished or out-of-scope VAK returns a denial with no details.
- A general answer cites an approved source and its retrieval trace shows no internal records.

## Step 8

### 10. [Langflow Chatbot] Chat endpoint, Langflow client, flow design and evaluation

labels: P0, area:chat, type:feature
depends: 01, 03, 09
needs decision: D6 (out-of-Surabaya wording and cost limit; flow design Task)
branch: feat/chat-flow
Refs: FR-25, FR-30, FR-31, FR-41, FR-42, TR-15, TR-29, TR-30, TR-31, TR-33, TR-34, TT-13, TT-14, AT-08, AT-09, AT-11 to AT-16, AT-24 to AT-28, §8.4

**Tasks**

- `POST /chat/messages` for anonymous or manager: derive role from the real session, validate input and size, rate limit, scoped `session_id`; histories and caches isolated by role and cleared on logout or role change.
- Server-to-server Langflow run API client (route depends on the pinned version) with configurable timeout, token/cost budget and a controlled message when Langflow, the model or the reference source is down.
- Treat output as untrusted: check source IDs exist and are visible to the caller, units, publication state and policy status; reject forged IDs and cross-region substitution with a safe response. Output fields: `answer, intent, source_type, source_ids, plot_code, method_version, policy_status`.
- Flow for `local_inventory`, `general_education`, `out_of_scope_inventory`, `mixed`, `ambiguous`, exported as JSON into `langflow/flows/` and reviewed in PRs; mixed questions use two labelled paths; Bali-style questions return the coverage limit.
- P1: conversation history and plot-ID clarification.
- Evaluation and adversarial tests from the PRD: published VAK-04, general question, Bali plot, unpublished plot, manager-only data, prompt injection, mixed, no matching plot, empty reference index, expired session, Langflow downtime. Record latency and cost.

**Done when**

- The browser only ever calls this endpoint; no Langflow URL or key reaches the client.
- Simulated downtime returns a clear message with no fabricated source; forged or unsupported measurements never reach the client.
- The flow can be redeployed from the repo with identical routing.
- Zero unauthorized retrievals and zero cross-region substitutions across the evaluation set; follow-ups keep context and manager history is never visible to visitors.

## Step 9

### 11. [Hardening & Release] Rate limiting, observability, backups and staging deploy

labels: P0, area:ops, type:feature
depends: 01, 07, 10
needs decision: D4 (backups and staging Tasks)
branch: chore/ops-hardening
Refs: TR-16, TR-17, TR-18, TR-20, TR-29, TT-08, TT-09, §9.7

**Tasks**

- Throttle anonymous chat and map endpoints; request-size limits; privacy-safe logs.
- Health and readiness checks, calculation/export/publication error logging, AI policy-denial events, alert drill.
- Daily encrypted backups and a documented restore rehearsal on a non-production environment (proposed RPO ≤ 24 h, RTO ≤ 8 h pending approval).
- Versioned images, migration and rollback notes, staging smoke test.

**Done when**

- Excess anonymous traffic gets a controlled 429 while normal visitors are unaffected.
- A denied chat request and a failed export both appear in logs with a request ID.
- A restore rehearsal report exists.
- A clean deploy and a rollback to the previous version are demonstrated.

## Step 10

### 12. [Hardening & Release] Performance review and release documentation

labels: P0, area:ops, type:docs
depends: 03, 04, 07, 08, 10, 11
branch: docs/perf-release
Refs: §9.7, NFR, §9.9 "required for MVP release", Definition of done

**Tasks**

- Indexes on `plot_id`, zone, status, date and geometry; query plans; load test dashboard p95 ≤ 3 s, map ≤ 5 s, export ≤ 30 s for 10,000 tree rows.
- Release package: README, `.env.example`, migration scripts, API docs, test report, calculation benchmark evidence, role/security test evidence, deployment guide, restore runbook, monitoring config, synthetic demo dataset.

**Done when**

- Performance results are recorded against the targets.
- Every item in the §9.9 release list exists in the repo or wiki.
