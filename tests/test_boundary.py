import asyncio
from unittest.mock import AsyncMock

import pytest

from app.models import Zone
from app.services.spatial import BoundingBox, classify_plot_scope, validate_coordinates


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
