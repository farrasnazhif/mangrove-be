"""Task 06 acceptance on isolated PostGIS; these are not scientific golden fixtures."""

import os
from dataclasses import asdict
from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update

from app.calc.engine import LayerInput, TreeInput, calculate_plot
from app.calc.methods import Method
from app.db.seed import seed_id
from app.models import AuditEvent, CalculationRun, ManagerNotice, Publication, Species, Zone
from app.services.calculation_runs import input_hash, published_run
from app.services.method_registry import register_method
from app.services.spatial import BoundingBox
from tests.test_field_data import api  # noqa: F401
from tests.test_task02_database import database  # noqa: F401

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="Set TEST_DATABASE_URL"),
]


@pytest.fixture
def field(api):  # noqa: F811
    request, run, connection = api

    async def setup():
        from sqlalchemy.ext.asyncio import AsyncSession

        async with AsyncSession(
            bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        ) as session:
            zone = Zone(
                id=str(uuid4()),
                name="Task 06 isolated test boundary",
                boundary_geom=BoundingBox(112.6, -7.4, 112.85, -7.15).polygon(),
                boundary_source="test fixture only, not a real approved study area",
                boundary_revision="test-v1",
                boundary_is_synthetic=False,
                approved_scope=True,
                data_label="field",
            )
            session.add(zone)
            species = Species(
                id=str(uuid4()), scientific_name="Task 06 fixture species", data_label="field"
            )
            session.add(species)
            method = await register_method(
                session,
                Method(
                    version="test-06-" + uuid4().hex,
                    references=("isolated API fixture; not scientific approval",),
                    approval_status="approved",
                    effective_date=date(2020, 1, 1),
                ),
                data_label="field",
            )
            await session.flush()
            await session.commit()
            return zone.id, method.id, species.id

    zone_id, method_id, species_id = run(setup())
    result = request(
        "POST",
        "/plots",
        json={
            "zone_id": zone_id,
            "code": "VAK-606",
            "area_m2": 100,
            "latitude": -7.3,
            "longitude": 112.7,
            "survey_date": "2026-11-17",
        },
    )
    assert result.status_code == 201, result.text
    plot_id = result.json()["id"]
    tree = request(
        "POST",
        f"/plots/{plot_id}/trees",
        json={
            "species_id": species_id,
            "dbh_cm": 10,
            "wood_density_g_cm3": 0.6,
            "density_source": "test measurement",
        },
    )
    assert tree.status_code == 201, tree.text
    return request, run, connection, plot_id, method_id, zone_id, tree.json()["id"]


def revision(request, plot_id):
    return request("GET", f"/plots/{plot_id}").json()["row_version"]


def calculate(field, **changes):
    request, _, _, plot_id, method_id, _, _ = field
    result = request(
        "POST",
        f"/plots/{plot_id}/calculation-runs",
        json={
            "method_version_id": method_id,
            "input_revision": revision(request, plot_id),
            **changes,
        },
    )
    assert result.status_code == 201, result.text
    return result.json()


def approve(field, draft):
    request, _, _, plot_id, _, _, _ = field
    result = request(
        "POST",
        f"/plots/{plot_id}/calculation-runs/{draft['id']}/approve",
        json={
            "row_version": revision(request, plot_id),
        },
    )
    assert result.status_code == 201, result.text
    return result.json()


def publish(field, approved):
    request, _, _, plot_id, _, _, _ = field
    return request(
        "POST",
        f"/plots/{plot_id}/publish",
        json={
            "calculation_run_id": approved["id"],
            "row_version": revision(request, plot_id),
        },
    )


def sediment(field, *, top=0, bottom=10, code="C1"):
    request, _, _, plot_id, _, _, _ = field
    core = request(
        "POST",
        f"/plots/{plot_id}/cores",
        json={
            "sample_code": code,
            "sample_date": "2026-11-17",
        },
    )
    assert core.status_code == 201, core.text
    result = request(
        "POST",
        f"/cores/{core.json()['id']}/layers",
        json={
            "depth_top_cm": top,
            "depth_bottom_cm": bottom,
            "dry_mass_g": 25,
            "volume_cm3": 50,
            "loi_pct": 17.24,
        },
    )
    assert result.status_code == 201, result.text
    return core.json()["id"], result.json()["id"]


def test_complete_run_review_publish_and_replay(field):
    request, run, connection, plot_id, _, _, _ = field
    sediment(field)
    draft = calculate(field, expected_bottom_cm=10)
    assert draft["qa_flags"] == [] and draft["qa_status"] == "draft"
    assert publish(field, draft).status_code == 409
    detail = request("GET", f"/plots/{plot_id}/calculation-runs/{draft['id']}").json()
    snapshot = detail["input_snapshot"]
    assert input_hash(snapshot) == draft["input_hash"]
    replay = calculate_plot(
        [
            TreeInput(t["dbh_cm"], t["wood_density_g_cm3"], t["species_id"])
            for t in snapshot["trees"]
        ],
        [
            LayerInput(
                l["depth_top_cm"],
                l["depth_bottom_cm"],
                l["dry_mass_g"],
                l["volume_cm3"],
                l["loi_pct"],
            )
            for l in snapshot["layers"]
        ],
        snapshot["plot"]["area_m2"],
        Method.from_dict(snapshot["method"]),
        expected_bottom_cm=snapshot["expected_bottom_cm"],
    )
    import json

    assert json.loads(json.dumps(asdict(replay))) == detail["result_json"]
    repeated = calculate(field, expected_bottom_cm=10)
    assert repeated["input_hash"] == draft["input_hash"]
    assert repeated["carbon_stock"] == draft["carbon_stock"]
    approved = approve(field, draft)
    assert approved["id"] != draft["id"] and approved["qa_status"] == "approved"
    assert request("GET", f"/plots/{plot_id}/calculation-runs/{draft['id']}").json() == detail
    result = publish(field, approved)
    assert result.status_code == 200, result.text
    assert result.json()["incomplete"] is False
    assert run(connection.scalar(select(Publication.published_run_id))) == approved["id"]
    assert (
        run(
            connection.scalar(
                select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "approve")
            )
        )
        == 1
    )


def test_biomass_publication_stays_visible_after_edit_new_draft_and_replacement(field):
    request, run, connection, plot_id, _, _, tree_id = field
    draft = calculate(field)
    assert "missing-sediment" in draft["qa_flags"]
    assert draft["carbon_stock"]["soc_mg_c_ha"] is None
    approved = approve(field, draft)
    result = publish(field, approved)
    assert result.status_code == 200 and result.json()["incomplete"] is True
    tree = request(
        "PATCH", f"/plots/{plot_id}/trees/{tree_id}", json={"row_version": 1, "dbh_cm": 20}
    )
    assert tree.status_code == 200, tree.text
    assert publish(field, approved).status_code == 409
    new_draft = calculate(field)
    assert new_draft["input_hash"] != draft["input_hash"]
    assert new_draft["carbon_stock"] != draft["carbon_stock"]

    async def resolve():
        from sqlalchemy.ext.asyncio import AsyncSession

        async with AsyncSession(
            bind=connection, join_transaction_mode="create_savepoint"
        ) as session:
            return (await published_run(session, plot_id)).id

    assert run(resolve()) == approved["id"]
    replacement = approve(field, new_draft)
    assert publish(field, replacement).status_code == 200
    assert run(resolve()) == replacement["id"]
    assert (
        request("GET", f"/plots/{plot_id}/calculation-runs/{approved['id']}").json()["carbon_stock"]
        == draft["carbon_stock"]
    )


def test_missing_density_notices_stale_revision_and_wrong_plot(field):
    request, run, connection, plot_id, method_id, _, tree_id = field
    assert (
        request(
            "PATCH",
            f"/plots/{plot_id}/trees/{tree_id}",
            json={
                "row_version": 1,
                "wood_density_g_cm3": None,
            },
        ).status_code
        == 200
    )
    draft = calculate(field)
    assert draft["carbon_stock"]["agc_mg_c_ha"] is None
    notices = request("GET", f"/plots/{plot_id}/notices?filter=flag:missing-density").json()
    assert notices["total"] == 1
    assert notices["items"][0]["plot_code"] == "VAK-606"
    assert notices["items"][0]["suggested_action"]
    assert (
        request(
            "POST",
            f"/plots/{plot_id}/calculation-runs/{draft['id']}/approve",
            json={
                "row_version": revision(request, plot_id),
            },
        ).status_code
        == 409
    )
    count = run(connection.scalar(select(func.count()).select_from(CalculationRun)))
    stale = request(
        "POST",
        f"/plots/{plot_id}/calculation-runs",
        json={
            "method_version_id": method_id,
            "input_revision": 1,
        },
    )
    assert stale.status_code == 409
    assert run(connection.scalar(select(func.count()).select_from(CalculationRun))) == count
    assert (
        request("GET", f"/plots/{seed_id('plot-1')}/calculation-runs/{draft['id']}").status_code
        == 404
    )
    assert (
        request(
            "POST",
            f"/plots/{plot_id}/publish",
            json={
                "calculation_run_id": str(uuid4()),
                "row_version": revision(request, plot_id),
            },
        ).status_code
        == 404
    )


@pytest.mark.parametrize("mode", ["gap", "unknown-depth", "multi-core"])
def test_incomplete_sediment_and_multiple_cores_cannot_publish_as_biomass(field, mode):
    request, _, _, plot_id, _, _, _ = field
    sediment(field, top=5 if mode == "gap" else 0)
    if mode == "multi-core":
        sediment(field, code="C2")
    draft = calculate(field, **({} if mode == "unknown-depth" else {"expected_bottom_cm": 10}))
    flag = {
        "gap": "missing-sediment-layer",
        "unknown-depth": "unknown-profile-depth",
        "multi-core": "multi-core-policy-required",
    }[mode]
    assert flag in draft["qa_flags"]
    assert draft["carbon_stock"]["total_mg_c_ha"] is None
    assert (
        request(
            "POST",
            f"/plots/{plot_id}/calculation-runs/{draft['id']}/approve",
            json={
                "row_version": revision(request, plot_id),
            },
        ).status_code
        == 409
    )


def test_seed_pending_method_and_synthetic_scope_cannot_approve(api):  # noqa: F811
    request, _, _ = api
    plot_id = seed_id("plot-1")
    draft = request(
        "POST",
        f"/plots/{plot_id}/calculation-runs",
        json={
            "method_version_id": seed_id("method"),
            "input_revision": 1,
            "expected_bottom_cm": 100,
        },
    )
    assert draft.status_code == 201, draft.text
    assert {"synthetic-input", "method-not-approved", "outside-approved-scope"} <= set(
        draft.json()["qa_flags"]
    )
    assert (
        request(
            "POST",
            f"/plots/{plot_id}/calculation-runs/{draft.json()['id']}/approve",
            json={"row_version": 1},
        ).status_code
        == 409
    )


def test_publication_rechecks_boundary_and_rolls_back_audit(field):
    _, run, connection, _, _, zone_id, _ = field
    approved = approve(field, calculate(field))
    run(connection.execute(update(Zone).where(Zone.id == zone_id).values(approved_scope=False)))
    count = run(connection.scalar(select(func.count()).select_from(AuditEvent)))
    result = publish(field, approved)
    assert result.status_code == 409 and result.json()["code"] == "scope_not_publishable"
    assert run(connection.scalar(select(func.count()).select_from(Publication))) == 0
    assert run(connection.scalar(select(func.count()).select_from(AuditEvent))) == count


def test_run_notices_and_audit_rollback_together(field):
    _, run, connection, plot_id, method_id, _, _ = field

    async def check():
        from sqlalchemy.ext.asyncio import AsyncSession

        from app.schemas.inventory import CalculationRequest
        from app.services.calculation_runs import create_run

        before = [
            await connection.scalar(select(func.count()).select_from(model))
            for model in (CalculationRun, ManagerNotice, AuditEvent)
        ]
        async with AsyncSession(
            bind=connection, join_transaction_mode="create_savepoint"
        ) as session:
            await create_run(
                session,
                plot_id,
                CalculationRequest(method_version_id=method_id, input_revision=2),
                seed_id("manager"),
            )
            await session.rollback()
        after = [
            await connection.scalar(select(func.count()).select_from(model))
            for model in (CalculationRun, ManagerNotice, AuditEvent)
        ]
        assert before == after

    run(check())


def test_boundary_revision_change_requires_new_calculation(field):
    _, run, connection, _, _, zone_id, _ = field
    approved = approve(field, calculate(field))
    run(
        connection.execute(
            update(Zone).where(Zone.id == zone_id).values(boundary_revision="test-v2")
        )
    )
    result = publish(field, approved)
    assert result.status_code == 409
    assert result.json()["code"] == "scope_revision_changed"


def test_unknown_method_and_invalid_target_depth_are_controlled(field):
    request, run, connection, plot_id, _, _, _ = field
    for changes in ({"method_version_id": str(uuid4())}, {"expected_bottom_cm": 0}):
        result = request(
            "POST",
            f"/plots/{plot_id}/calculation-runs",
            json={
                "method_version_id": field[4],
                "input_revision": revision(request, plot_id),
                **changes,
            },
        )
        assert result.status_code == 422, result.text
    sediment(field, bottom=20)
    result = request(
        "POST",
        f"/plots/{plot_id}/calculation-runs",
        json={
            "method_version_id": field[4],
            "input_revision": revision(request, plot_id),
            "expected_bottom_cm": 10,
        },
    )
    assert result.status_code == 422
    assert run(connection.scalar(select(func.count()).select_from(CalculationRun))) == 0


def test_archived_tree_and_core_are_excluded_from_new_snapshot(field):
    request, _, _, plot_id, _, _, tree_id = field
    core_id, _ = sediment(field)
    assert (
        request(
            "DELETE", f"/plots/{plot_id}/cores/{core_id}?row_version=1&confirm=true"
        ).status_code
        == 200
    )
    assert (
        request(
            "DELETE", f"/plots/{plot_id}/trees/{tree_id}?row_version=1&confirm=true"
        ).status_code
        == 200
    )
    draft = calculate(field)
    detail = request("GET", f"/plots/{plot_id}/calculation-runs/{draft['id']}").json()
    assert detail["input_snapshot"]["trees"] == []
    assert detail["input_snapshot"]["cores"] == []
    assert detail["input_snapshot"]["layers"] == []
    assert "missing-tree-inventory" in draft["qa_flags"]
