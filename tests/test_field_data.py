"""Task 05 API acceptance against real PostGIS in rollback-only schemas."""

import os
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_optional_session
from app.core.security import create_session_token
from app.db.seed import seed_id
from app.db.session import get_session
from app.main import app
from app.models import AuditEvent, CalculationRun, Plot, Publication, Tree
from app.services.audit import record_change
from tests.test_task02_database import database  # noqa: F401

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="Set TEST_DATABASE_URL"),
]


@pytest.fixture
def api(database):  # noqa: F811
    run, auth_session, connection = database
    savepoint = run(connection.begin_nested())

    async def session_override():
        async with AsyncSession(
            bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        ) as session:
            yield session

    async def auth_override():
        yield auth_session

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_optional_session] = auth_override
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    client.headers["Authorization"] = "Bearer " + create_session_token(
        seed_id("manager"), "manager"
    )

    def request(method, path, **kwargs):
        return run(client.request(method, "/api/v1" + path, **kwargs))

    try:
        yield request, run, connection
    finally:
        run(client.aclose())
        app.dependency_overrides.clear()
        run(savepoint.rollback())


def plot_payload(**changes):
    return {
        "zone_id": seed_id("zone"),
        "code": "VAK-105",
        "area_m2": 100,
        "latitude": -7.3,
        "longitude": 112.7,
        "survey_date": "2026-11-17",
        **changes,
    }


def new_plot(request):
    response = request("POST", "/plots", json=plot_payload())
    assert response.status_code == 201, response.text
    return response.json()


def test_plot_scope_pagination_version_conflict_and_atomic_audit(api):
    request, run, connection = api
    plot = new_plot(request)
    assert plot["data_label"] == "field"
    assert plot["status"] == "quarantine"
    assert plot["scope_reason"] == "study-area-not-approved"
    plot_id = plot["id"]
    audit_count = run(connection.scalar(select(func.count()).select_from(AuditEvent)))
    assert audit_count == 1
    duplicate = request("POST", "/plots", json=plot_payload())
    assert duplicate.status_code == 409, duplicate.text
    assert duplicate.json()["details"][0]["field"] == "body.code"
    assert run(connection.scalar(select(func.count()).select_from(AuditEvent))) == audit_count
    response = request("PATCH", f"/plots/{plot_id}", json={"row_version": 1, "area_m2": 120})
    assert response.status_code == 200, response.text
    assert response.json()["row_version"] == 2
    stale = request("PATCH", f"/plots/{plot_id}", json={"row_version": 1, "area_m2": 999})
    assert stale.status_code == 409
    assert request("GET", f"/plots/{plot_id}").json()["area_m2"] == 120
    page = request("GET", "/plots?filter=code:VAK-105&page_size=1").json()
    assert page["total"] == 1 and page["items"][0]["id"] == plot_id
    assert request("GET", "/plots?filter=zone_id:invalid").status_code == 422
    assert (
        request("PATCH", f"/plots/{plot_id}", json={"row_version": 2, "area_m2": None}).status_code
        == 422
    )


def test_tree_crud_revision_and_safe_archive(api):
    request, run, connection = api
    plot = new_plot(request)
    path = f"/plots/{plot['id']}/trees"
    payload = {
        "species_id": seed_id("species"),
        "dbh_cm": 12,
        "wood_density_g_cm3": 0.6,
        "density_source": "field measurement",
        "height_m": 3,
    }
    bad = request("POST", path, json={**payload, "species_id": str(uuid4())})
    assert bad.status_code == 422
    tree_response = request("POST", path, json=payload)
    assert tree_response.status_code == 201, tree_response.text
    tree = tree_response.json()
    assert tree["height_m"] == 3 and tree["wood_density_g_cm3"] == 0.6
    assert request("GET", f"/plots/{plot['id']}").json()["row_version"] == 2
    assert request("GET", path + "?filter=species_id:" + seed_id("species")).json()["total"] == 1
    item_path = path + "/" + tree["id"]
    update = request("PATCH", item_path, json={"row_version": 1, "dbh_cm": 15, "height_m": None})
    assert update.status_code == 200, update.text
    assert update.json()["height_m"] is None and update.json()["row_version"] == 2
    assert request("PATCH", item_path, json={"row_version": 1, "dbh_cm": 30}).status_code == 409
    assert request("DELETE", item_path + "?row_version=2").status_code == 422
    archived = request("DELETE", item_path + "?row_version=2&confirm=true")
    assert archived.status_code == 200, archived.text
    assert archived.json()["archived_at"]
    assert request("GET", path).json()["total"] == 0
    assert run(connection.scalar(select(Tree.archived_at).where(Tree.id == tree["id"])))
    assert request("PATCH", item_path, json={"row_version": 3, "dbh_cm": 17}).status_code == 404
    assert request("POST", path, json={**payload, "photo_id": str(uuid4())}).status_code == 422
    unknown = request("POST", path, json={"species_id": seed_id("species"), "dbh_cm": 12})
    assert unknown.status_code == 201, unknown.text
    assert unknown.json()["wood_density_g_cm3"] is None
    unknown_path = path + "/" + unknown.json()["id"]
    missing_source = request(
        "PATCH",
        unknown_path,
        json={
            "row_version": 1,
            "wood_density_g_cm3": 0.6,
        },
    )
    assert missing_source.status_code == 422
    assert missing_source.json()["details"][0]["field"] == "body.density_source"


def test_sediment_overlap_merged_validation_and_archived_replacement(api):
    request, _, _ = api
    plot = new_plot(request)
    cores_path = f"/plots/{plot['id']}/cores"
    core_response = request(
        "POST", cores_path, json={"sample_code": "TEST-C1", "sample_date": "2026-11-17"}
    )
    assert core_response.status_code == 201, core_response.text
    core = core_response.json()
    path = f"/cores/{core['id']}/layers"
    payload = {
        "depth_top_cm": 0,
        "depth_bottom_cm": 10,
        "dry_mass_g": 20,
        "volume_cm3": 50,
        "loi_pct": 10,
    }
    layer_response = request("POST", path, json=payload)
    assert layer_response.status_code == 201, layer_response.text
    layer = layer_response.json()
    overlap = request("POST", path, json={**payload, "depth_top_cm": 5})
    assert overlap.status_code == 422, overlap.text
    assert overlap.json()["details"][0]["field"] == "body.depth_top_cm"
    assert (
        request(
            "POST", path, json={**payload, "depth_top_cm": 10, "depth_bottom_cm": 20}
        ).status_code
        == 201
    )
    item = path + "/" + layer["id"]
    assert request("PATCH", item, json={"row_version": 1, "depth_top_cm": 12}).status_code == 422
    assert request("PATCH", item, json={"row_version": 1, "dry_mass_g": -1}).status_code == 422
    assert request("PATCH", item, json={"row_version": 1, "loi_pct": 0}).status_code == 200
    assert request("DELETE", item + "?row_version=2&confirm=true").status_code == 200
    assert request("POST", path, json=payload).status_code == 201
    assert request("GET", path).json()["total"] == 2
    other = seed_id("plot-2")
    wrong_parent = f"/plots/{other}/cores/{core['id']}"
    assert (
        request("PATCH", wrong_parent, json={"row_version": 1, "sample_code": "NO"}).status_code
        == 404
    )
    assert (
        request(
            "PATCH",
            cores_path + "/" + core["id"],
            json={"row_version": 1, "sample_code": "TEST-C2"},
        ).status_code
        == 200
    )
    assert (
        request("DELETE", cores_path + "/" + core["id"] + "?row_version=2&confirm=true").status_code
        == 200
    )
    assert request("GET", path).status_code == 404


def test_audit_rollback_preserves_data_and_no_credentials(api):
    _, run, connection = api

    async def rollback():
        before = await connection.scalar(select(func.count()).select_from(AuditEvent))
        async with (
            AsyncSession(bind=connection, join_transaction_mode="create_savepoint") as session,
            session.begin(),
        ):
            tree = await session.get(Tree, seed_id("plot-1/tree-1"))
            tree.dbh_cm = 99
            record_change(
                session,
                actor_id=seed_id("manager"),
                record=tree,
                action="update",
                before={"dbh_cm": 11},
            )
            await session.flush()
            await session.rollback()
        assert await connection.scalar(select(func.count()).select_from(AuditEvent)) == before
        assert (
            await connection.scalar(select(Tree.dbh_cm).where(Tree.id == seed_id("plot-1/tree-1")))
            == 11
        )

    run(rollback())


def test_archive_does_not_change_published_snapshot(api):
    request, run, connection = api
    # Use schema-level fixtures for an approved historical snapshot.
    from sqlalchemy import insert

    from app.models import MethodVersion
    from tests.test_task02_database import calculation, method

    m = method()
    run(connection.execute(insert(MethodVersion).values(m)))
    r = calculation(m["id"])
    run(connection.execute(insert(CalculationRun).values(r)))
    p = {"plot_id": r["plot_id"], "published_run_id": r["id"], "approved_by": seed_id("manager")}
    run(connection.execute(insert(Publication).values(p)))
    before = (
        run(connection.execute(select(CalculationRun).where(CalculationRun.id == r["id"])))
        .mappings()
        .one()
    )
    response = request(
        "DELETE",
        f"/plots/{seed_id('plot-1')}/trees/{seed_id('plot-1/tree-1')}?row_version=1&confirm=true",
    )
    assert response.status_code == 200, response.text
    after = (
        run(connection.execute(select(CalculationRun).where(CalculationRun.id == r["id"])))
        .mappings()
        .one()
    )
    assert dict(before) == dict(after)
    assert run(connection.scalar(select(Publication.published_run_id))) == r["id"]
    assert (
        run(connection.scalar(select(Plot.row_version).where(Plot.id == seed_id("plot-1"))))
        > r["input_revision"]
    )
