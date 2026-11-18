"""Task 07 handoff: public projections never use live draft values."""

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import insert, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import HiddenResourceError
from app.db.seed import seed_id
from app.models import Attachment, Plot, Zone
from app.services.published_inventory import published_candidates, published_inventory
from app.services.spatial import BoundingBox
from tests.test_calculation_runs import approve, calculate, field, publish, sediment  # noqa: F401
from tests.test_field_data import api  # noqa: F401
from tests.test_task02_database import database  # noqa: F401

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="Set TEST_DATABASE_URL"),
]


def read(context):
    _, run, connection, plot_id, _, _, _ = context

    async def get():
        async with AsyncSession(
            bind=connection, join_transaction_mode="create_savepoint"
        ) as session:
            return await published_inventory(session, plot_id)

    return run(get())


def test_snapshot_projection_survives_live_tree_and_plot_changes(field):  # noqa: F811
    request, run, connection, plot_id, _, _, tree_id = field
    sediment(field)
    approved = approve(field, calculate(field, expected_bottom_cm=10))
    assert publish(field, approved).status_code == 200
    original = read(field)
    assert original.plot.quality_status == "complete"
    assert original.trees[0].dbh_cm == 10
    assert original.trees[0].photo_id is None
    assert (
        request(
            "PATCH", f"/plots/{plot_id}/trees/{tree_id}", json={"row_version": 1, "dbh_cm": 30}
        ).status_code
        == 200
    )
    assert (
        request(
            "PATCH",
            f"/plots/{plot_id}",
            json={
                "row_version": request("GET", f"/plots/{plot_id}").json()["row_version"],
                "code": "VAK-999",
                "longitude": 112.75,
            },
        ).status_code
        == 200
    )
    calculate(field, expected_bottom_cm=10)
    assert read(field) == original
    public = original.model_dump(mode="json")
    assert "input_snapshot" not in str(public)
    assert "density_source" not in str(public)
    assert "approved_by" not in str(public)
    assert "object_key" not in str(public)

    async def count():
        async with AsyncSession(
            bind=connection, join_transaction_mode="create_savepoint"
        ) as session:
            return len((await session.execute(published_candidates())).all())

    assert run(count()) == 1  # Draft runs cannot multiply published records/legend counts.


@pytest.mark.parametrize(
    "mode", ["unpublished", "archived", "revoked-boundary", "snapshot-outside"]
)
def test_public_lookup_hides_ineligible_records(field, mode):  # noqa: F811
    request, run, connection, plot_id, _, zone_id, _ = field
    if mode != "unpublished":
        assert publish(field, approve(field, calculate(field))).status_code == 200
    if mode == "archived":
        run(
            connection.execute(
                update(Plot).where(Plot.id == plot_id).values(archived_at=datetime.now(UTC))
            )
        )
    elif mode == "revoked-boundary":
        run(connection.execute(update(Zone).where(Zone.id == zone_id).values(approved_scope=False)))
    elif mode == "snapshot-outside":
        version = request("GET", f"/plots/{plot_id}").json()["row_version"]
        assert (
            request(
                "PATCH", f"/plots/{plot_id}", json={"row_version": version, "longitude": 112.78}
            ).status_code
            == 200
        )
        run(
            connection.execute(
                update(Zone)
                .where(Zone.id == zone_id)
                .values(
                    boundary_geom=BoundingBox(112.76, -7.4, 112.8, -7.15).polygon(),
                )
            )
        )
    with pytest.raises(HiddenResourceError) as error:
        read(field)
    assert error.value.status_code == 404
    assert str(error.value) == "Resource not found"


@pytest.mark.parametrize("visibility", ["public", "private"])
def test_photo_allowlist_checks_snapshot_and_current_visibility(field, visibility):  # noqa: F811
    request, run, connection, plot_id, _, _, tree_id = field
    photo_id = str(uuid4())
    run(
        connection.execute(
            insert(Attachment).values(
                id=photo_id,
                entity_type="plots",
                entity_id=plot_id,
                object_key="test/" + photo_id,
                mime_type="image/png",
                size_bytes=10,
                visibility=visibility,
                uploaded_by=seed_id("manager"),
            )
        )
    )
    assert (
        request(
            "PATCH",
            f"/plots/{plot_id}/trees/{tree_id}",
            json={"row_version": 1, "photo_id": photo_id},
        ).status_code
        == 200
    )
    assert publish(field, approve(field, calculate(field))).status_code == 200
    initial = read(field)
    assert initial.plot.quality_status == "incomplete"
    assert (
        str(initial.trees[0].photo_id) == photo_id
        if visibility == "public"
        else initial.trees[0].photo_id is None
    )
    run(
        connection.execute(
            update(Attachment).where(Attachment.id == photo_id).values(visibility="private")
        )
    )
    assert read(field).trees[0].photo_id is None
    run(
        connection.execute(
            update(Attachment).where(Attachment.id == photo_id).values(visibility="public")
        )
    )
    # A captured private photo is never promoted by a live metadata change.
    if visibility == "private":
        assert read(field).trees[0].photo_id is None
