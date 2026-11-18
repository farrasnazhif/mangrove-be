import asyncio
from unittest.mock import AsyncMock

import pytest

from app.models import Plot, Zone
from app.services.spatial import (
    BoundingBox,
    classify_plot_scope,
    inventory_scope_predicate,
    require_publishable_scope,
    validate_coordinates,
)


@pytest.mark.parametrize(
    "longitude,latitude,inside",
    [
        (112.7, -7.3, True),
        (112.59, -7.3, False),
        (112.86, -7.3, False),
        (112.7, -7.41, False),
        (112.7, -7.14, False),
        (112.60, -7.3, True),
        (112.85, -7.3, True),
        (112.7, -7.40, True),
        (112.7, -7.15, True),
        (112.60, -7.40, True),
        (112.85, -7.15, True),
    ],
)
def test_box_inside_outside_edges(longitude, latitude, inside):
    assert BoundingBox(112.60, -7.40, 112.85, -7.15).covers(longitude, latitude) is inside


@pytest.mark.parametrize(
    "longitude,latitude", [(181, 0), (0, 91), (float("nan"), 0), (0, float("inf"))]
)
def test_invalid_coordinates(longitude, latitude):
    with pytest.raises(ValueError):
        validate_coordinates(longitude, latitude)


@pytest.mark.parametrize(
    "inside,synthetic,approved,label,expected",
    [
        (False, False, True, "field", ("quarantine", "outside-study-area")),
        (True, True, False, "field", ("quarantine", "study-area-not-approved")),
        (True, False, False, "field", ("quarantine", "study-area-not-approved")),
        (True, True, False, "synthetic", ("draft", None)),
        (True, False, True, "field", ("draft", None)),
    ],
)
def test_scope_policy(inside, synthetic, approved, label, expected):
    session = AsyncMock()
    session.scalar.return_value = inside
    zone = Zone(boundary_is_synthetic=synthetic, approved_scope=approved)
    assert (
        asyncio.run(classify_plot_scope(session, zone, 112.7, -7.3, data_label=label)) == expected
    )


@pytest.mark.parametrize(
    "reason", ["archived", "unknown-plot-label", "unknown-zone-label", "outside", "quarantine"]
)
def test_publication_scope_fails_closed(reason):
    from datetime import UTC, datetime

    session = AsyncMock()
    session.scalar.return_value = reason != "outside"
    zone = Zone(id="zone", data_label="field", boundary_is_synthetic=False, approved_scope=True)
    plot = Plot(zone_id="zone", data_label="field", status="draft", archived_at=None)
    if reason == "archived":
        plot.archived_at = datetime.now(UTC)
    elif reason == "unknown-plot-label":
        plot.data_label = "unverified"
    elif reason == "unknown-zone-label":
        zone.data_label = "unverified"
    elif reason == "quarantine":
        plot.status = "quarantine"
    with pytest.raises(ValueError, match="cannot be published"):
        asyncio.run(require_publishable_scope(session, plot, zone))


def test_inventory_scope_excludes_archived_and_unknown_labels():
    sql = str(inventory_scope_predicate().compile(compile_kwargs={"literal_binds": True}))
    assert "plots.archived_at IS NULL" in sql
    assert "plots.data_label = 'field'" in sql
    assert "zones.data_label = 'field'" in sql
