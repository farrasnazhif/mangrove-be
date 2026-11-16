"""Shared study-area policy: ST_Covers includes polygon edges and corners.

Creation, publishing and inventory tools must use the stored Zone geometry,
never a city-wide approximation or an untrusted request flag. Config supplies
the initial seed polygon only; changing env does not silently rewrite a zone.
"""

import math
from dataclasses import dataclass

from geoalchemy2 import WKTElement
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, settings
from app.models.inventory import Plot, Zone


@dataclass(frozen=True)
class BoundingBox:
    lon_min: float
    lat_min: float
    lon_max: float
    lat_max: float

    def __post_init__(self) -> None:
        if not (
            -180 <= self.lon_min < self.lon_max <= 180 and -90 <= self.lat_min < self.lat_max <= 90
        ):
            raise ValueError("Invalid WGS84 bounding box")

    def covers(self, longitude: float, latitude: float) -> bool:
        validate_coordinates(longitude, latitude)
        return (
            self.lon_min <= longitude <= self.lon_max and self.lat_min <= latitude <= self.lat_max
        )

    def polygon(self) -> WKTElement:
        a, b, c, d = self.lon_min, self.lat_min, self.lon_max, self.lat_max
        return WKTElement(f"POLYGON(({a} {b},{c} {b},{c} {d},{a} {d},{a} {b}))", srid=4326)

    @classmethod
    def from_settings(cls, config: Settings = settings) -> "BoundingBox":
        return cls(
            config.boundary_lon_min,
            config.boundary_lat_min,
            config.boundary_lon_max,
            config.boundary_lat_max,
        )


def validate_coordinates(longitude: float, latitude: float) -> None:
    if not (
        math.isfinite(longitude)
        and math.isfinite(latitude)
        and -180 <= longitude <= 180
        and -90 <= latitude <= 90
    ):
        raise ValueError("Coordinates must be finite WGS84 longitude/latitude")


def point(longitude: float, latitude: float) -> WKTElement:
    validate_coordinates(longitude, latitude)
    return WKTElement(f"POINT({longitude} {latitude})", srid=4326)


async def classify_plot_scope(
    session: AsyncSession,
    zone: Zone,
    longitude: float,
    latitude: float,
    *,
    data_label: str,
) -> tuple[str, str | None]:
    """Creation/import hook: retain invalid-scope rows as quarantine for correction."""
    inside = await session.scalar(
        select(func.ST_Covers(zone.boundary_geom, point(longitude, latitude)))
    )
    if not inside:
        return "quarantine", "outside-study-area"
    if data_label != "synthetic" and (
        zone.boundary_is_synthetic or not zone.approved_scope or zone.data_label == "synthetic"
    ):
        return "quarantine", "study-area-not-approved"
    return "draft", None


async def assign_plot_scope(session: AsyncSession, plot: Plot, zone: Zone) -> None:
    """Always derive geometry and quarantine state from trusted zone data."""
    if plot.zone_id != zone.id:
        raise ValueError("Scope must be checked against the plot's own zone")
    plot.geom = point(plot.longitude, plot.latitude)
    plot.status, plot.scope_reason = await classify_plot_scope(
        session,
        zone,
        plot.longitude,
        plot.latitude,
        data_label=plot.data_label,
    )


def inventory_scope_predicate():
    """SQL filter for publication/chatbot inventory; caller must join Plot to Zone.

    Publication and role filters remain mandatory in the consuming feature.
    Synthetic records are excluded even if someone marks their zone approved.
    """
    return and_(
        Plot.zone_id == Zone.id,
        Plot.status != "quarantine",
        Plot.data_label != "synthetic",
        Zone.data_label != "synthetic",
        Zone.approved_scope.is_(True),
        Zone.boundary_is_synthetic.is_(False),
        func.ST_Covers(Zone.boundary_geom, Plot.geom),
    )


async def require_publishable_scope(session: AsyncSession, plot: Plot, zone: Zone) -> None:
    """Publishing hook: fail closed until an official study boundary is approved."""
    if (
        plot.zone_id != zone.id
        or plot.data_label == "synthetic"
        or zone.data_label == "synthetic"
        or zone.boundary_is_synthetic
        or not zone.approved_scope
        or plot.status == "quarantine"
    ):
        raise ValueError(
            "Plot cannot be published: study area is synthetic, unapproved or quarantined"
        )
    if not await session.scalar(select(func.ST_Covers(zone.boundary_geom, plot.geom))):
        raise ValueError("Plot cannot be published: outside approved study area")
